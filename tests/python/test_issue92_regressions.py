"""Commit snapshots retain module inputs without widening reported findings."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

import check_fix_allowlist as gate
from .test_content_boundaries import link_or_skip
from .test_local_scanner_trust import consumer, git, load_runner
from .test_validation_targets import package, hook


@pytest.mark.parametrize('hook_name,setting', [
    ('semgrep-csharp', 'SEMGREP_RULESET_CSHARP'),
    ('semgrep-typescript', 'SEMGREP_RULESET_TYPESCRIPT'),
])
@pytest.mark.parametrize('staged', [False, True])
def test_external_rule_alias_binds_to_index(consumer, tmp_path, monkeypatch, hook_name, setting, staged):
    rules = consumer / 'rules'
    rules.mkdir()
    rule = rules / 'custom.yml'
    rule.write_text('staged rule\n', encoding='utf-8')
    if staged:
        git(consumer, 'add', 'rules')
    alias = tmp_path / 'external-alias'
    link_or_skip(rules, alias, True)
    monkeypatch.setenv(setting, str(alias / 'custom.yml'))
    rule.write_text('unstaged rule\n', encoding='utf-8')
    runner = load_runner('alias_commit', 'pre-commit.py')
    tree = runner.index_tree()
    if staged:
        inputs, environment = runner.rule_inputs(consumer.resolve(), tree, hook_name)
        assert inputs == {'rules/custom.yml'}
        assert environment == {setting: 'rules/custom.yml'}
    else:
        with pytest.raises(ValueError, match='not staged'):
            runner.rule_inputs(consumer.resolve(), tree, hook_name)


@pytest.mark.parametrize('path,allowed', [
    (' terraform/main.tf', 'terraform/'),
    ('\tterraform/main.tf', 'terraform/'),
    ('terraform/main.tf ', 'terraform/main.tf'),
    ('terraform/main.tf\t', 'terraform/main.tf'),
    ('terraform/main.tf', ' terraform/'),
    ('terraform/main.tf', 'terraform/main.tf '),
])
def test_allowlist_preserves_path_whitespace(path, allowed):
    ok, reason = gate.check([path], [allowed], [])
    assert not ok, reason


@pytest.mark.parametrize('path', [' terraform/main.tf', 'terraform/main.tf ', ' '])
def test_allowlist_can_match_exact_whitespace_path(path):
    assert gate.check([path], [path], [])[0]


def test_allowlist_stdin_preserves_whitespace_only_path(tmp_path):
    config = tmp_path / 'config.yaml'
    config.write_text('fix_loop:\n  allowlist_paths: [terraform/]\n', encoding='utf-8')
    result = subprocess.run([sys.executable, str(Path(gate.__file__)), '--config', str(config)],
                            input=' \n', capture_output=True, text=True)
    assert result.returncode == 1, result.stdout


def test_index_capture_diagnostic_reaches_cli(consumer, package):
    blob = subprocess.check_output(['git', 'hash-object', '-w', '--stdin'], cwd=consumer, input=b'conflict\n').strip()
    entries = b''.join(b'100644 ' + blob + b' ' + str(stage).encode() + b'\tconflict.tf\n'
                       for stage in (1, 2, 3))
    subprocess.run(['git', 'update-index', '--index-info'], cwd=consumer, input=entries, check=True)
    result = subprocess.run([sys.executable, str(package / 'hooks/pre-commit.py'), 'trivy-iac-critical'],
                            cwd=consumer, capture_output=True, text=True)
    assert result.returncode == 1
    assert 'scan incomplete' in result.stderr
    assert 'conflict.tf: unmerged' in result.stderr


def prepare_module(consumer):
    module = consumer / 'module space'
    module.mkdir()
    (module / 'variables.tf').write_text('variable "cidrs" {\n  default = ["0.0.0.0/0"]\n}\n', encoding='utf-8')
    (module / 'old.tf').write_text('resource "aws_security_group" "old" {\n'
        '  egress {\n    from_port = 0\n    to_port = 0\n    protocol = "-1"\n'
        '    cidr_blocks = ["0.0.0.0/0"]\n  }\n}\n', encoding='utf-8')
    git(consumer, 'add', '.')
    git(consumer, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test',
        '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'fixture')
    return module


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('insecure', [False, True])
def test_real_commit_scan_keeps_context_and_selected_reporting(consumer, package, shell, insecure):
    if not shutil.which('trivy'):
        pytest.skip('Trivy unavailable')
    module = prepare_module(consumer)
    source = ('resource "aws_security_group" "selected" {\n'
              '  egress {\n    from_port = 0\n    to_port = 0\n    protocol = "-1"\n'
              '    cidr_blocks = var.cidrs\n  }\n}\n') if insecure else '# selected clean file\n'
    (module / 'main.tf').write_text(source, encoding='utf-8')
    git(consumer, 'add', 'module space/main.tf')
    # Neither changed resources nor their context may borrow working-tree bytes.
    (module / 'main.tf').write_text('# unstaged clean file\n', encoding='utf-8')
    (module / 'variables.tf').write_text('variable "cidrs" {\n  default = ["10.0.0.0/8"]\n}\n', encoding='utf-8')
    result = subprocess.run(hook(package, shell, 'trivy-iac-critical'), cwd=consumer,
                            capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == int(insecure), result.stdout + result.stderr
    report = json.loads((consumer / '.scanning/last-scan.json').read_text(encoding='utf-8-sig'))
    assert report['summary']['total_findings'] == int(insecure)
    assert 'old.tf' not in result.stdout


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('selected_finding', [False, True])
def test_commit_filters_scanner_results_to_manifest(consumer, package, tmp_path, shell, selected_finding):
    module = prepare_module(consumer)
    (module / 'main.tf').write_text('# selected\n', encoding='utf-8')
    git(consumer, 'add', 'module space/main.tf')
    tools = tmp_path / 'tools'
    tools.mkdir()
    finding = {'ID': 'fixture', 'Severity': 'CRITICAL', 'Title': 'fixture'}
    targets = ['old.tf', 'main.tf'] if selected_finding else ['old.tf']
    data = {'Results': [{'Target': name, 'Misconfigurations': [finding]} for name in targets]}
    scanner = tools / 'scanner.py'
    scanner.write_text('import sys\nprint(' + repr(json.dumps(data)) + ')\nsys.exit(1)\n', encoding='utf-8')
    (tools / 'trivy').write_text(f'#!/usr/bin/env bash\nexec "{Path(sys.executable).as_posix()}" "{scanner.as_posix()}"\n', newline='\n')
    (tools / 'trivy').chmod(0o755)
    (tools / 'trivy.cmd').write_text(f'@"{sys.executable}" "{scanner}"\n')
    result = subprocess.run(hook(package, shell, 'trivy-iac-critical'), cwd=consumer,
                            env=dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH']),
                            capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == int(selected_finding), result.stdout + result.stderr
    report = json.loads((consumer / '.scanning/last-scan.json').read_text(encoding='utf-8-sig'))
    assert report['summary']['total_findings'] == int(selected_finding)


@pytest.mark.parametrize('report', [{}, {'Results': None}, {'Results': [None]}, {'Results': []},
    {'Results': [{'Target': 'old.tf', 'Misconfigurations': []}]},
    {'Results': [{'Target': 'old.tf', 'Misconfigurations': [None]}]},
    {'Results': [{'Target': 'old.tf', 'Misconfigurations': [{}]}]},
    {'Results': [{'Misconfigurations': {}}]},
    {'Results': [{'Misconfigurations': [{'Severity': 'CRITICAL'}]}]},
    {'Results': [{'Target': '../../outside.tf', 'Misconfigurations': [{'Severity': 'CRITICAL'}]}]}])
def test_selection_filter_rejects_incomplete_report(tmp_path, report):
    manifest = tmp_path / 'paths'
    manifest.write_bytes(b'module/main.tf\0')
    helper = Path(__file__).resolve().parents[2] / 'hooks/lib/trivy_selected.py'
    result = subprocess.run([sys.executable, '-I', str(helper), 'module', str(manifest)],
                            cwd=tmp_path, input=json.dumps(report), capture_output=True, text=True)
    assert result.returncode == 2
    assert 'scan incomplete' in result.stderr


def test_selection_filter_reads_scanner_json_as_utf8(tmp_path):
    manifest = tmp_path / 'paths'
    manifest.write_bytes('module/caf\u00e9.tf\0'.encode('utf-8'))
    helper = Path(__file__).resolve().parents[2] / 'hooks/lib/trivy_selected.py'
    report = {'Results': [{'Target': 'caf\u00e9.tf', 'Misconfigurations': [{'Severity': 'CRITICAL'}]}]}
    # Native scanner output is UTF-8, even with a legacy Windows stdin codec.
    command = ('import runpy,sys; sys.stdin.reconfigure(encoding="cp1252"); '
               'sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0],run_name="__main__")')
    result = subprocess.run([sys.executable, '-I', '-c', command, str(helper), 'module', str(manifest)],
                            cwd=tmp_path, input=json.dumps(report, ensure_ascii=False).encode('utf-8'), capture_output=True)
    assert result.returncode == 1, result.stderr
    assert json.loads(result.stdout) == report

