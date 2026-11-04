"""Baseline scanners must use passive policy and external executable identities."""
import json
import os
from pathlib import Path
import subprocess

import pytest
import yaml

from .baseline_helpers import scanner_stub
from .test_setup_baseline_hardening import ROOT, clean_env, powershell, ps_string


@pytest.fixture
def baseline_case(tmp_path):
    repo = tmp_path / 'consumer'
    repo.mkdir()
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    baseline = repo / '.scan-baseline/baseline.json'
    baseline.parent.mkdir()
    baseline.write_text('reviewed baseline', encoding='utf-8')
    env = clean_env()
    trusted = tmp_path / 'trusted.hcl'
    trusted.write_text('config {}', encoding='utf-8')
    env.update(SCAN_TFLINT_CONFIG=str(trusted), SCAN_TFLINT_PLUGIN_DIR=str(tmp_path / 'plugins'))
    return repo, baseline, env


def invoke(repo, env, tool='checkov', extra=''):
    return powershell(
        f'& {ps_string(ROOT / "scripts/create-baseline.ps1")} '
        f'-Tool {tool} -CloudProvider aws -Force {extra}', repo, env=env)


@pytest.mark.parametrize('location', ['.scanning/configs/.checkov.yaml', '.checkov.yaml', 'custom/.checkov.yaml'])
def test_baseline_never_forwards_executable_checkov_policy(tmp_path, baseline_case, location):
    repo, baseline, env = baseline_case
    config = repo / location
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text('external-checks-dir:\n- executable-checks\n', encoding='utf-8')
    if location.startswith('custom/'):
        env['SCAN_CONFIG_DIR'] = str(config.parent)
    scanner_stub(tmp_path / 'tools', 'checkov', env)
    result = invoke(repo, env)
    trace = Path(env['BASELINE_TRACE'])
    if result.returncode:
        assert 'Checkov policy rejected' in result.stderr
        assert not trace.exists()
        assert baseline.read_text(encoding='utf-8') == 'reviewed baseline'
    else:
        call, = [json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()]
        assert '--config-file' in call['args']
        assert 'external-checks-dir' not in yaml.safe_load(call['policy'])


@pytest.mark.parametrize('policy', [None, 'skip-check:\n- CKV_AWS_1\noutput: sarif\n'])
@pytest.mark.parametrize('scanner_code', [0, 1, 2])
def test_baseline_passive_policy_and_cleanup(tmp_path, baseline_case, policy, scanner_code):
    repo, baseline, env = baseline_case
    if policy:
        config = repo / '.scanning/configs/.checkov.yaml'
        config.parent.mkdir(parents=True)
        config.write_text(policy, encoding='utf-8')
    scanner_stub(tmp_path / 'tools', 'checkov', env, code=scanner_code)
    result = invoke(repo, env)
    call, = [json.loads(line) for line in Path(env['BASELINE_TRACE']).read_text(encoding='utf-8').splitlines()]
    assert '--config-file' in call['args']
    effective = yaml.safe_load(call['policy'])
    assert effective == dict({'download-external-modules': False, 'skip-download': True},
                             **({'skip-check': ['CKV_AWS_1']} if policy else {}))
    assert not Path(call['policy_path']).exists()
    assert (result.returncode == 0) == (scanner_code in (0, 1)), result.stdout + result.stderr
    if scanner_code == 2:
        assert baseline.read_text(encoding='utf-8') == 'reviewed baseline'


@pytest.mark.parametrize('tool', ['checkov', 'trivy', 'tflint'])
@pytest.mark.parametrize('boundary', ['repository', 'scanned', 'scanned-subdir', 'consumer', 'link'])
def test_baseline_refuses_repository_scanners(tmp_path, baseline_case, tool, boundary):
    repo, baseline, env = baseline_case
    extra = ''
    folder = repo / 'bin'
    if boundary in ('scanned', 'scanned-subdir', 'consumer'):
        other = tmp_path / 'other checkout'
        other.mkdir()
        folder = other / 'bin'
        if boundary == 'scanned-subdir':
            subprocess.run(['git', 'init', '-q', str(other)], check=True)
            module = other / 'infra'
            module.mkdir()
            extra = f'-TerraformDir {ps_string(module)}'
        elif boundary == 'scanned':
            extra = f'-TerraformDir {ps_string(other)}'
        else:
            env.update(SCAN_INDEX_SNAPSHOT='1', SCAN_CONSUMER_ROOT=str(other))
    scanner_stub(folder, tool, env)
    if boundary == 'link':
        link = tmp_path / 'linked-bin'
        if os.name == 'nt':
            subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(folder)], check=True, capture_output=True)
        else:
            link.symlink_to(folder, target_is_directory=True)
        env['PATH'] = str(link) + os.pathsep + env['PATH']
    result = invoke(repo, env, tool, extra)
    assert result.returncode != 0, result.stdout + result.stderr
    assert 'must resolve outside' in result.stderr
    assert not Path(env['BASELINE_TRACE']).exists()
    assert baseline.read_text(encoding='utf-8') == 'reviewed baseline'


@pytest.mark.parametrize('tool', ['checkov', 'trivy', 'tflint'])
def test_baseline_uses_external_application_despite_function_shadow(tmp_path, baseline_case, tool):
    repo, baseline, env = baseline_case
    scanner_stub(tmp_path / 'external tools', tool, env)
    result = powershell(
        f'function {tool} {{ throw "function shadow executed" }}; '
        f'& {ps_string(ROOT / "scripts/create-baseline.ps1")} -Tool {tool} -CloudProvider aws -Force', repo, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert Path(env['BASELINE_TRACE']).exists()
    assert json.loads(baseline.read_text(encoding='utf-8'))['schema_version'] == '2.0'


@pytest.mark.parametrize('tool', ['checkov', 'trivy', 'tflint'])
def test_baseline_relative_scan_path_uses_powershell_location(tmp_path, baseline_case, tool):
    repo, baseline, env = baseline_case
    scanner_stub(tmp_path / 'external tools', tool, env)
    result = powershell(
        f'Set-Location {ps_string(repo)}; '
        f'& {ps_string(ROOT / "scripts/create-baseline.ps1")} -Tool {tool} -CloudProvider aws -Force',
        tmp_path, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert Path(env['BASELINE_TRACE']).exists()
    assert json.loads(baseline.read_text(encoding='utf-8'))['schema_version'] == '2.0'
