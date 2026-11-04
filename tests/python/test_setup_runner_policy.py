"""Verify selected hook runners and baseline policy boundaries."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

import setup_scan_fix

ROOT = Path(__file__).resolve().parents[2]


def ps_string(value):
    return "'" + str(value).replace("'", "''") + "'"


def clean_env():
    return {key: value for key, value in os.environ.items()
            if not key.startswith(('GIT_', 'SCAN_', 'TFLINT_', 'CC_SKIP_'))}


def powershell(command, cwd, *, env):
    shell = shutil.which('pwsh')
    if not shell:
        pytest.skip('PowerShell unavailable')
    return subprocess.run([shell, '-NoProfile', '-Command', "$ErrorActionPreference='Stop'; " + command + '; exit $LASTEXITCODE'],
                          cwd=cwd, env=env, text=True, capture_output=True, timeout=90)


@pytest.mark.parametrize('runner', ['lefthook', 'pre-commit'])
def test_python_setup_forwards_selected_runner(tmp_path, monkeypatch, runner):
    repo = tmp_path / 'repo'
    repo.mkdir()
    calls = []
    monkeypatch.setattr(setup_scan_fix, 'resolve_tool', lambda name, repo: str(tmp_path / name))

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout='', stderr='')

    monkeypatch.setattr(subprocess, 'run', run)
    assert setup_scan_fix.main(['setup', '--repo-path', str(repo), '--hooks-runner', runner]) == 0
    verification = next(command for command in calls if 'scan' in ' '.join(command)
                        and str(ROOT / 'scripts/verify-scanning.ps1') in command)
    assert verification[-2:] == ['-HooksRunner', runner]


@pytest.mark.parametrize('runner', ['lefthook', 'pre-commit'])
def test_shell_setup_forwards_selected_runner(tmp_path, runner):
    platform = tmp_path / 'platform'
    for folder in ('scripts', 'hooks', 'schemas', 'templates'):
        shutil.copytree(ROOT / folder, platform / folder, ignore=shutil.ignore_patterns('__pycache__'))
    repo = tmp_path / 'repo'
    repo.mkdir()
    trace = tmp_path / 'verify.json'
    (platform / 'scripts/verify-scanning.ps1').write_text(
        'ConvertTo-Json -InputObject @($args) -Compress | Set-Content $env:VERIFY_TRACE\nexit 0\n', encoding='utf-8')
    env = clean_env()
    env['VERIFY_TRACE'] = str(trace)
    command = ('function Get-Command { param($Name, $CommandType, $ErrorAction) '
               'if ($Name -notin @("lefthook", "pre-commit", "gh")) { '
               'Microsoft.PowerShell.Core\\Get-Command @PSBoundParameters } }; '
               f'& {ps_string(platform / "scripts/setup-scan-fix.ps1")} -RepoPath {ps_string(repo)} '
               f'-HooksRunner {runner}')
    result = powershell(command, tmp_path, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(trace.read_text(encoding='utf-8')) == ['-HooksRunner', runner]


@pytest.mark.parametrize('runner', ['lefthook', 'pre-commit'])
@pytest.mark.parametrize('missing', [None, 'config', 'hook', 'security-hook'])
def test_verifier_checks_selected_runner(tmp_path, runner, missing):
    repo = tmp_path / 'repo'
    repo.mkdir()
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    config = 'lefthook.yml' if runner == 'lefthook' else '.pre-commit-config.yaml'
    content = ((ROOT / 'templates/lefthook/lefthook.yml').read_text(encoding='utf-8')
               if runner == 'lefthook' else
               'terraform_trivy terraform_checkov terraform_tflint trivy-secrets detect-private-key')
    if missing != 'config':
        (repo / config).write_text(content.replace('trivy-secrets', 'removed')
                                   if missing == 'security-hook' else content, encoding='utf-8')
    for hook in ('pre-commit', 'pre-push'):
        if missing != 'hook' or hook != 'pre-commit':
            (repo / '.git/hooks' / hook).write_text(f'#!/bin/sh\n# {runner}\n', encoding='utf-8')
    (repo / '.checkov.yaml').write_text('{}', encoding='utf-8')
    trusted = tmp_path / 'trusted.hcl'
    trusted.write_text('config {}', encoding='utf-8')
    env = clean_env()
    env.update(SCAN_TFLINT_CONFIG=str(trusted), SCAN_TFLINT_PLUGIN_DIR=str(tmp_path / 'plugins'),
               SELECTED_RUNNER=runner)
    # The unselected runner must never be probed or executed, including -Full.
    command = ('function trivy { $global:LASTEXITCODE=0; "1.0" }; '
               'function checkov { "1.0" }; function terraform { "1.0" }; '
               'function tflint { $global:LASTEXITCODE=0 }; '
               'function lefthook { if ($env:SELECTED_RUNNER -ne "lefthook") { throw "wrong runner" }; '
               '$global:LASTEXITCODE=0; "1.0" }; '
               'function pre-commit { if ($env:SELECTED_RUNNER -ne "pre-commit") { throw "wrong runner" }; '
               '$global:LASTEXITCODE=0; "1.0" }; '
               f'& {ps_string(ROOT / "scripts/verify-scanning.ps1")} -HooksRunner {runner} -Full')
    result = powershell(command, repo, env=env)
    assert result.returncode == int(missing is not None), result.stdout + result.stderr
    assert 'wrong runner' not in result.stdout + result.stderr


@pytest.mark.parametrize('location', ['root', 'nested', 'alias'])
def test_baseline_rejects_internal_policy_before_scanning(tmp_path, location):
    repo = tmp_path / 'repo'
    (repo / 'infra').mkdir(parents=True)
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    policy = repo if location == 'root' else repo / 'infra'
    if location == 'alias':
        policy = tmp_path / 'policy-link'
        if os.name == 'nt':
            result = powershell(f'New-Item -ItemType Junction -Path {ps_string(policy)} '
                                f'-Target {ps_string(repo)} | Out-Null', tmp_path, env=clean_env())
            assert result.returncode == 0, result.stderr
        else:
            policy.symlink_to(repo, target_is_directory=True)
    output = repo / '.scan-baseline'
    command = ('function checkov { throw "scanner must not run" }; '
               f'& {ps_string(ROOT / "scripts/create-baseline.ps1")} -Tool checkov -CloudProvider aws -Force '
               f'-PolicyRoot {ps_string(policy)}')
    result = powershell(command, repo / 'infra', env=clean_env())
    assert result.returncode != 0, result.stdout + result.stderr
    assert 'outside the scanned' in result.stderr
    assert 'scanner must not run' not in result.stderr
    assert not output.exists()
