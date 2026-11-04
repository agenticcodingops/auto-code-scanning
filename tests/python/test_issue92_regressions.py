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


@pytest.mark.parametrize('absolute', [False, True])
def test_local_rules_cannot_be_redirected_by_unstaged_link(consumer, tmp_path, monkeypatch, absolute):
    rules = consumer / 'rules'
    rules.mkdir()
    (rules / 'custom.yml').write_text('staged rules\n', encoding='utf-8')
    (consumer / 'App.cs').write_text('// selected\n', encoding='utf-8')
    git(consumer, 'add', '.')
    saved = consumer / 'saved-rules'
    assert rules.parent == saved.parent == consumer
    rules.rename(saved)
    outside = tmp_path / 'outside-rules'
    outside.mkdir()
    (outside / 'custom.yml').write_text('external worktree rules\n', encoding='utf-8')
    link_or_skip(outside, rules, True)
    monkeypatch.setenv('SEMGREP_RULESET_CSHARP', str(rules / 'custom.yml') if absolute else 'rules/custom.yml')
    runner = load_runner('redirected_commit_rules', 'pre-commit.py')
    monkeypatch.setattr(runner.push, 'select_shell', lambda _: ('sh', 'scanner-shell'))
    original = subprocess.run
    def run(command, **kwargs):
        if command[0] != 'scanner-shell':
            return original(command, **kwargs)
        assert (kwargs['cwd'] / 'rules/custom.yml').read_text(encoding='utf-8') == 'staged rules\n'
        assert kwargs['env']['SEMGREP_RULESET_CSHARP'] == 'rules/custom.yml'
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(runner.subprocess, 'run', run)
    assert runner.scan('semgrep-csharp', [], 'sh') == 0


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
@pytest.mark.parametrize('filename', ['terraform.tfvars', 'override.auto.tfvars'])
def test_real_commit_scan_uses_staged_variable_overrides(consumer, package, shell, filename):
    if not shutil.which('trivy'):
        pytest.skip('Trivy unavailable')
    module = prepare_module(consumer)
    (module / 'variables.tf').write_text('variable "cidrs" {\n  default = ["10.0.0.0/8"]\n}\n', encoding='utf-8')
    (module / filename).write_text('cidrs = ["0.0.0.0/0"]\n', encoding='utf-8')
    git(consumer, 'add', '-f', 'module space/variables.tf', 'module space/' + filename)
    git(consumer, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test',
        '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'fixture overrides')
    (module / 'main.tf').write_text('resource "aws_security_group" "selected" {\n'
        '  egress {\n    from_port = 0\n    to_port = 0\n    protocol = "-1"\n'
        '    cidr_blocks = var.cidrs\n  }\n}\n', encoding='utf-8')
    git(consumer, 'add', 'module space/main.tf')
    (module / filename).write_text('cidrs = ["10.0.0.0/8"]\n', encoding='utf-8')
    result = subprocess.run(hook(package, shell, 'trivy-iac-critical'), cwd=consumer,
                            capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 1, result.stdout + result.stderr
    report_path = consumer / '.scanning/last-scan.json'
    assert report_path.exists(), result.stdout + result.stderr
    report = json.loads(report_path.read_text(encoding='utf-8-sig'))
    assert report['summary']['total_findings'] == 1


@pytest.mark.parametrize('shell', ['powershell', 'pwsh'])
def test_powershell_commit_filter_preserves_unicode_pipeline(consumer, package, tmp_path, shell):
    executable = shutil.which(shell)
    if not executable:
        pytest.skip(shell + ' unavailable')
    name = 'caf\u00e9.tf'
    (consumer / name).write_text('# selected\n', encoding='utf-8')
    manifest = tmp_path / 'paths'
    manifest.write_bytes((name + '\0').encode('utf-8'))
    data = {'Results': [{'Target': name, 'Misconfigurations': [{'ID': 'fixture', 'Severity': 'CRITICAL'}]}]}
    report_file = tmp_path / 'scanner.json'
    report_file.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    script = (package / 'hooks/trivy-iac-critical.ps1').as_posix()
    # Model the legacy native-pipeline encoding even on a modern host.
    command = ("$env:PSModulePath = (Join-Path $PSHOME 'Modules') + [IO.Path]::PathSeparator + $env:PSModulePath; "
               "$OutputEncoding = [Text.Encoding]::ASCII; function trivy { "
               "$global:LASTEXITCODE=1; [IO.File]::ReadAllText($env:FIXTURE_REPORT) }; "
               f"& '{script}'; exit $LASTEXITCODE")
    result = subprocess.run([executable, '-NoProfile', '-Command', command], cwd=consumer,
                            env=dict(os.environ, SCAN_INDEX_SNAPSHOT='1', SCAN_PUSH_FILES=str(manifest),
                                     FIXTURE_REPORT=str(report_file)), capture_output=True)
    assert result.returncode == 1, result.stdout + result.stderr
    report_path = consumer / '.scanning/last-scan.json'
    assert report_path.exists(), result.stdout + result.stderr
    report = json.loads(report_path.read_text(encoding='utf-8-sig'))
    assert report['summary']['total_findings'] == 1


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('selected_finding', [False, True])
@pytest.mark.parametrize('prefixed', [False, True])
def test_commit_filters_scanner_results_to_manifest(consumer, package, tmp_path, shell, selected_finding, prefixed):
    module = prepare_module(consumer)
    (module / 'main.tf').write_text('# selected\n', encoding='utf-8')
    git(consumer, 'add', 'module space/main.tf')
    tools = tmp_path / 'tools'
    tools.mkdir()
    finding = {'ID': 'fixture', 'Severity': 'CRITICAL', 'Title': 'fixture'}
    targets = ['old.tf', 'main.tf'] if selected_finding else ['old.tf']
    if prefixed:
        targets = ['module space/' + name for name in targets]
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
    (tmp_path / 'module').mkdir()
    (tmp_path / 'module/caf\u00e9.tf').write_text('# selected\n', encoding='utf-8')
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


def test_selection_filter_rejects_ambiguous_directory_prefix(tmp_path):
    (tmp_path / 'module/module').mkdir(parents=True)
    (tmp_path / 'module/main.tf').write_text('# outer context\n', encoding='utf-8')
    (tmp_path / 'module/module/main.tf').write_text('# nested selected\n', encoding='utf-8')
    manifest = tmp_path / 'paths'
    manifest.write_bytes(b'module/module/main.tf\0')
    helper = Path(__file__).resolve().parents[2] / 'hooks/lib/trivy_selected.py'
    report = {'Results': [{'Target': 'module/main.tf', 'Misconfigurations': [{'Severity': 'CRITICAL'}]}]}
    result = subprocess.run([sys.executable, '-I', str(helper), 'module', str(manifest)],
                            cwd=tmp_path, input=json.dumps(report), capture_output=True, text=True)
    assert result.returncode == 2
    assert 'scan incomplete' in result.stderr


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('payload', ['{}', '{"Results": []}', 'broken JSON'])
def test_invalid_commit_report_blocks_even_with_tool_error_opt_in(consumer, package, tmp_path, shell, payload):
    (consumer / 'main.tf').write_text('# selected\n', encoding='utf-8')
    manifest = tmp_path / 'paths'
    manifest.write_bytes(b'main.tf\0')
    tools = tmp_path / 'tools'
    tools.mkdir()
    scanner = tools / 'scanner.py'
    scanner.write_text(f'import sys\nprint({payload!r})\nsys.exit(1)\n', encoding='utf-8')
    (tools / 'trivy').write_text(f'#!/usr/bin/env bash\nexec "{Path(sys.executable).as_posix()}" "{scanner.as_posix()}"\n',
                                encoding='utf-8', newline='\n')
    (tools / 'trivy').chmod(0o755)
    (tools / 'trivy.cmd').write_text(f'@"{sys.executable}" "{scanner}"\n', encoding='utf-8')
    result = subprocess.run(hook(package, shell, 'trivy-iac-critical'), cwd=consumer,
                            env=dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH'],
                                     SCAN_INDEX_SNAPSHOT='1', SCAN_PUSH_FILES=str(manifest), SCAN_ALLOW_TOOL_ERRORS='1'),
                            capture_output=True)
    assert result.returncode == 1, result.stdout + result.stderr


def test_selection_filter_rejects_unmapped_target(tmp_path):
    (tmp_path / 'module').mkdir()
    (tmp_path / 'module/main.tf').write_text('# selected\n', encoding='utf-8')
    manifest = tmp_path / 'paths'
    manifest.write_bytes(b'module/main.tf\0')
    helper = Path(__file__).resolve().parents[2] / 'hooks/lib/trivy_selected.py'
    report = {'Results': [{'Target': 'unmapped.tf', 'Misconfigurations': [{'Severity': 'CRITICAL'}]}]}
    result = subprocess.run([sys.executable, '-I', str(helper), 'module', str(manifest)],
                            cwd=tmp_path, input=json.dumps(report), capture_output=True, text=True)
    assert result.returncode == 2
    assert 'scan incomplete' in result.stderr

