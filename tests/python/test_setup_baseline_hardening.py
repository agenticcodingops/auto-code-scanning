"""Behavioral regressions for onboarding, edit feedback and baseline creation."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

import check_fix_allowlist as allowlist
import scan
import setup_scan_fix
from scan_policy import apply_exceptions

ROOT = Path(__file__).resolve().parents[2]


def ps_string(value):
    return "'" + str(value).replace("'", "''") + "'"


def powershell(command, cwd, *, env=None, input=None, executable='pwsh'):
    shell = shutil.which(executable)
    if not shell:
        pytest.skip(f'{executable} unavailable')
    return subprocess.run([shell, '-NoProfile', '-Command', command + '; exit $LASTEXITCODE'], cwd=cwd,
                          env=env, input=input, text=True, capture_output=True, timeout=90)


def clean_env():
    return {k: v for k, v in os.environ.items()
            if not k.startswith(('GIT_', 'SCAN_', 'TFLINT_', 'CC_SKIP_'))}


@pytest.mark.parametrize('path', ['api/src/../../outside.yml', 'api/src//file.cs',
                                    '/api/src/file.cs', 'C:/api/src/file.cs',
                                    'api/src/C:/file.cs', 'api/src/./file.cs',
                                    'api/src/file.cs/', '', r'api\src\..\file.cs'])
def test_allowlist_rejects_invalid_segments(path):
    assert not allowlist.check([path], ['api/src/'], [])[0]


@pytest.mark.parametrize('entry', ['api/src/../', '/api/src', 'api//src', 'C:/api/src'])
def test_allowlist_rejects_invalid_prefixes(entry):
    assert not allowlist.check(['api/src/file.cs'], [entry], [])[0]


@pytest.mark.parametrize('name', ['lefthook', 'pre-commit', 'gh', 'pwsh'])
def test_setup_rejects_repository_tool_before_writes(tmp_path, monkeypatch, name):
    repo = tmp_path / 'repo'
    repo.mkdir()
    tool = repo / (name + '.exe')
    tool.write_bytes(b'fixture')
    monkeypatch.setattr(shutil, 'which', lambda command: str(tool) if command == name else None)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: pytest.fail('tool executed'))
    assert setup_scan_fix.main(['setup', '--repo-path', str(repo)]) == 1
    assert not (repo / 'scan-config.yaml').exists()


@pytest.mark.skipif(os.name != 'nt', reason='Windows short-path identity')
@pytest.mark.parametrize('tool_name', ['lefthook', 'python'])
def test_setup_normalizes_short_repository_path_before_tool_checks(tmp_path, monkeypatch, tool_name):
    import ctypes
    repo = tmp_path / 'repository with a long name'
    repo.mkdir()
    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetShortPathNameW(str(repo), buffer, len(buffer))
    if not length:
        pytest.skip('short paths unavailable')
    alias = Path(buffer.value)
    if alias == repo:
        pytest.skip('short names disabled on this volume')
    assert alias.resolve() == repo.resolve()
    tool = repo / (tool_name + '.exe')
    tool.write_bytes(b'fixture')
    monkeypatch.setattr(shutil, 'which', lambda command: str(tool) if command == tool_name == 'lefthook' else None)
    if tool_name == 'python':
        monkeypatch.setattr(sys, 'executable', str(tool))
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: pytest.fail('tool executed'))
    assert setup_scan_fix.main(['setup', '--repo-path', str(alias)]) == 1
    assert not (repo / 'scan-config.yaml').exists()


@pytest.mark.parametrize('runner', ['lefthook', 'pre-commit'])
def test_setup_invokes_frozen_absolute_tool_paths(tmp_path, monkeypatch, runner):
    repo = tmp_path / 'repo'
    repo.mkdir()
    tools = tmp_path / 'tools'
    tools.mkdir()
    paths = {name: str(tools / (name + '.exe')) for name in ('lefthook', 'pre-commit', 'gh', 'pwsh')}
    for path in paths.values():
        Path(path).write_bytes(b'fixture')
    monkeypatch.setattr(shutil, 'which', lambda name: paths[name])
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        # Later PATH changes must not cause any subprocess to resolve a name again.
        monkeypatch.setattr(shutil, 'which', lambda name: pytest.fail('tool re-resolved'))
        return subprocess.CompletedProcess(command, 0, stdout='[]', stderr='')
    monkeypatch.setattr(subprocess, 'run', run)
    assert setup_scan_fix.main(['setup', '--repo-path', str(repo), '--hooks-runner', runner,
                               '--enable-fix-loop']) == 0
    assert all(Path(call[0]).is_absolute() for call in calls)
    assert {paths[runner], paths['gh'], paths['pwsh']}.issubset({c[0] for c in calls})
    assert all(not Path(call[0]).is_relative_to(repo) for call in calls)


@pytest.mark.parametrize('name', ['lefthook', 'pre-commit', 'gh', 'pwsh', 'python'])
def test_shell_setup_rejects_repository_tool_before_writes(tmp_path, name):
    repo = tmp_path / 'repo'
    repo.mkdir()
    tool = repo / (name + '.ps1')
    tool.write_text("throw 'repository tool executed'\n", encoding="utf-8")
    env = clean_env()
    env.update(REJECT_NAME=name, REJECT_PATH=str(tool))
    command = ('function Get-Command { param($Name, $CommandType, $ErrorAction) '
               'if ($Name -eq $env:REJECT_NAME) { [pscustomobject]@{ Source=$env:REJECT_PATH } } '
               'else { Microsoft.PowerShell.Core\\Get-Command @PSBoundParameters } }; '
               f'& {ps_string(ROOT / "scripts/setup-scan-fix.ps1")} -RepoPath {ps_string(repo)}')
    result = powershell(command, tmp_path, env=env)
    assert result.returncode != 0, result.stdout + result.stderr
    assert 'must resolve outside' in result.stderr
    assert not (repo / 'scan-config.yaml').exists()


@pytest.mark.parametrize('runner', ['lefthook', 'pre-commit'])
def test_shell_setup_keeps_frozen_paths_after_directory_change(tmp_path, runner):
    platform = tmp_path / 'platform'
    for folder in ('scripts', 'hooks', 'schemas', 'templates', 'configs'):
        shutil.copytree(ROOT / folder, platform / folder, ignore=shutil.ignore_patterns('__pycache__'))
    repo = tmp_path / 'repo'
    repo.mkdir()
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    (repo / '.git/hooks/pre-push').write_text('#!/bin/sh\n# File generated by pre-commit\n# end templated\n', encoding="utf-8")
    tools = tmp_path / 'tools'
    tools.mkdir()
    trace = tmp_path / 'trace.jsonl'
    for name in ('lefthook', 'pre-commit', 'gh', 'pwsh'):
        (tools / (name + '.ps1')).write_text(
            f'@{{ tool="{name}"; args=@($args) }} | ConvertTo-Json -Compress | Add-Content $env:TOOL_TRACE\n'
            'if ($args -contains "secret") { "[]" }\nexit 0\n', encoding="utf-8")
    env = clean_env()
    env.update(PATH=str(tools) + os.pathsep + env['PATH'], TOOL_TRACE=str(trace), SETUP_TOOLS=str(tools))
    command = ('function Get-Command { param($Name, $CommandType, $ErrorAction) '
               'if ($Name -in @("lefthook", "pre-commit", "gh", "pwsh")) { '
               '[pscustomobject]@{ Source=(Join-Path $env:SETUP_TOOLS "$Name.ps1") } } '
               'else { Microsoft.PowerShell.Core\\Get-Command @PSBoundParameters } }; '
               'function Push-Location { Microsoft.PowerShell.Management\\Push-Location @args; '
               "function global:lefthook { throw 'bare tool invoked' }; "
               "function global:pre-commit { throw 'bare tool invoked' }; "
               "function global:gh { throw 'bare tool invoked' }; "
               "function global:pwsh { throw 'bare tool invoked' }; "
               "function global:python { throw 'bare tool invoked' } }; "
               f'& {ps_string(platform / "scripts/setup-scan-fix.ps1")} -RepoPath {ps_string(repo)} '
               f'-HooksRunner {runner} -EnableFixLoop')
    result = powershell(command, tmp_path, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'bare tool invoked' not in result.stdout + result.stderr
    calls = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    assert [call['tool'] for call in calls] == [runner, 'gh', 'gh', 'gh', 'pwsh']


@pytest.mark.parametrize('shell', ['bash', 'pwsh'])
@pytest.mark.parametrize('mode', ['finding', 'malformed', 'error', 'invalid-shape', 'clean'])
def test_edit_feedback_never_emits_secret_values(tmp_path, shell, mode):
    sentinel = 'fixture-private-value-938475'
    target = tmp_path / 'settings.txt'
    target.write_text('edited setting\n' + sentinel + '\n', encoding="utf-8")
    document = {'Results': [{'Target': str(target), 'Secrets': [
        {'RuleID': 'fixture-rule', 'StartLine': 2, 'Match': sentinel,
         'Code': {'Lines': [{'Content': sentinel}]}, 'Title': sentinel}]}]}
    raw = json.dumps(document)
    code = 1
    if mode == 'malformed':
        raw = sentinel + '{'
    elif mode == 'error':
        code = 7
    elif mode == 'invalid-shape':
        raw = json.dumps({'Results': sentinel})
    elif mode == 'clean':
        code, raw = 0, '{"SchemaVersion":2}'
    env = clean_env()
    env.update(STUB_REPORT=raw, STUB_CODE=str(code), PRIVATE_SENTINEL=sentinel)
    payload = json.dumps({'tool_input': {'file_path': str(target)}})
    if shell == 'pwsh':
        hook = ROOT / 'templates/claude/hooks/posttooluse-scan.ps1'
        env['STUB_PY'] = sys.executable
        stub = tmp_path / 'scanner.py'
        stub.write_text('import os,sys\nprint(os.environ["PRIVATE_SENTINEL"],file=sys.stderr)\n'
                        'print(os.environ["STUB_REPORT"])\nsys.exit(int(os.environ["STUB_CODE"]))\n', encoding="utf-8")
        command = (f'function trivy {{ & $env:STUB_PY {ps_string(stub)} }}; '
                   f'& {ps_string(hook)}')
        result = powershell(command, tmp_path, env=env, input=payload)
    else:
        bash = shutil.which('bash')
        if not bash:
            pytest.skip('bash unavailable')
        hook = (ROOT / 'templates/claude/hooks/posttooluse-scan.sh').as_posix()
        command = ('trivy() { printf "%s\\n" "$PRIVATE_SENTINEL" >&2; '
                   'printf "%s" "$STUB_REPORT"; return "$STUB_CODE"; }; export -f trivy; '
                   f'bash "{hook}"')
        result = subprocess.run([bash, '-c', command], cwd=tmp_path, env=env,
                                input=payload, text=True, capture_output=True, timeout=45)
    output = result.stdout + result.stderr
    assert sentinel not in output
    assert result.returncode == (0 if mode == 'clean' else 2), output
    if mode == 'finding':
        assert 'fixture-rule' in output and 'count=1' in output
        assert '"line":2' in output.replace(' ', '')
    elif mode != 'clean':
        assert 'details redacted' in output


@pytest.mark.parametrize('policy', ['external', 'missing', 'internal-config', 'internal-cache', 'plugin-dir'])
@pytest.mark.parametrize('init_code', [0, 1])
def test_verifier_uses_external_policy_only(tmp_path, policy, init_code):
    repo = tmp_path / 'repo'
    repo.mkdir()
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    (repo / '.tflint.hcl').write_text('plugin "fixture" { enabled = true }', encoding="utf-8")
    trusted = tmp_path / 'trusted.hcl'
    trusted.write_text('config {}' if policy != 'plugin-dir' else 'config { plugin_dir = "cache" }', encoding="utf-8")
    trace = tmp_path / 'trace.jsonl'
    env = clean_env()
    env.update(SCAN_TFLINT_CONFIG=str(repo / '.tflint.hcl') if policy == 'internal-config' else str(trusted),
               SCAN_TFLINT_PLUGIN_DIR=str(repo / 'cache') if policy == 'internal-cache' else str(tmp_path / 'cache'),
               STUB_TRACE=str(trace), STUB_INIT_CODE=str(init_code))
    if policy == 'missing':
        del env['SCAN_TFLINT_CONFIG']
    command = (
        'function tflint { '
        '@{ args=@($args); cache=$env:TFLINT_PLUGIN_DIR } | ConvertTo-Json -Compress | Add-Content $env:STUB_TRACE; '
        '$global:LASTEXITCODE=if ($args -contains "--init") { [int]$env:STUB_INIT_CODE } else { 2 } }; '
        'function trivy { $global:LASTEXITCODE=0 }; function checkov {}; function pre-commit {}; '
        f'& {ps_string(ROOT / "scripts/verify-scanning.ps1")}')
    result = powershell(command, repo, env=env)
    calls = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()] if trace.exists() else []
    if policy != 'external':
        assert calls == [], result.stdout + result.stderr
        assert 'Cannot verify tflint' in result.stdout
    else:
        assert len(calls) == (1 if init_code else 2), result.stdout + result.stderr
        for call in calls:
            assert f'--config={trusted}' in call['args']
            assert Path(call['cache']) == tmp_path / 'cache'
        if init_code:
            assert 'tflint initialization failed' in result.stdout
        else:
            assert 'verified with trusted external policy' in result.stdout


@pytest.mark.parametrize('tool,code', [('trivy', 1), ('trivy', 9), ('checkov', 2), ('tflint', 1)])
def test_baseline_scanner_error_preserves_existing_file(tmp_path, tool, code):
    repo = tmp_path / 'repo'
    repo.mkdir()
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    folder = repo / '.scan-baseline'
    folder.mkdir()
    baseline = folder / 'baseline.json'
    baseline.write_text('existing reviewed baseline', encoding="utf-8")
    trusted = tmp_path / 'trusted.hcl'
    trusted.write_text('config {}', encoding="utf-8")
    env = clean_env()
    env.update(SCAN_TFLINT_CONFIG=str(trusted), SCAN_TFLINT_PLUGIN_DIR=str(tmp_path / 'cache'))
    command = (f'function {tool} {{ $global:LASTEXITCODE={code}; '
               "'{\"Results\":[],\"results\":{\"failed_checks\":[]},\"issues\":[]}' }; "
               f'& {ps_string(ROOT / "scripts/create-baseline.ps1")} -Tool {tool} -CloudProvider aws -Force')
    result = powershell(command, repo, env=env)
    assert result.returncode != 0, result.stdout + result.stderr
    assert baseline.read_text(encoding="utf-8") == 'existing reviewed baseline'
    assert 'Created Successfully' not in result.stdout


@pytest.mark.parametrize('tool,report', [('trivy', '{}'), ('checkov', '{}'), ('tflint', '{}'),
                                       ('trivy', '{'), ('checkov', '{'), ('tflint', '{')])
def test_baseline_invalid_report_preserves_existing_file(tmp_path, tool, report):
    repo = tmp_path / 'repo'
    repo.mkdir()
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    folder = repo / '.scan-baseline'
    folder.mkdir()
    baseline = folder / 'baseline.json'
    baseline.write_text('existing reviewed baseline', encoding="utf-8")
    trusted = tmp_path / 'trusted.hcl'
    trusted.write_text('config {}', encoding="utf-8")
    env = clean_env()
    env.update(SCAN_TFLINT_CONFIG=str(trusted), SCAN_TFLINT_PLUGIN_DIR=str(tmp_path / 'cache'))
    command = (f'function {tool} {{ $global:LASTEXITCODE=0; {ps_string(report)} }}; '
               f'& {ps_string(ROOT / "scripts/create-baseline.ps1")} -Tool {tool} -CloudProvider aws -Force')
    result = powershell(command, repo, env=env)
    assert result.returncode != 0, result.stdout + result.stderr
    assert baseline.read_text(encoding="utf-8") == 'existing reviewed baseline'


def test_baseline_rejects_linked_plugin_cache_before_scanner_runs(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    trusted = tmp_path / 'trusted.hcl'
    trusted.write_text('config {}', encoding="utf-8")
    target = tmp_path / 'external-cache'
    target.mkdir()
    cache = tmp_path / 'linked-cache'
    if os.name == 'nt':
        subprocess.run(['cmd', '/c', 'mklink', '/J', str(cache), str(target)],
                       check=True, capture_output=True)
    else:
        cache.symlink_to(target, target_is_directory=True)
    marker = tmp_path / 'scanner-ran'
    env = clean_env()
    env.update(SCAN_TFLINT_CONFIG=str(trusted), SCAN_TFLINT_PLUGIN_DIR=str(cache), SCANNER_MARKER=str(marker))
    command = ('function tflint { Set-Content $env:SCANNER_MARKER executed; '
               '$global:LASTEXITCODE=0; \'{"issues":[]}\' }; '
               f'& {ps_string(ROOT / "scripts/create-baseline.ps1")} -Tool tflint -CloudProvider aws -Force')
    result = powershell(command, repo, env=env)
    assert result.returncode != 0
    assert 'symlink or reparse point' in result.stderr
    assert not marker.exists()
    assert not (repo / '.scan-baseline/baseline.json').exists()


@pytest.mark.parametrize('array_report', [False, True])
def test_baseline_covers_untrusted_skip_using_gate_identity(tmp_path, monkeypatch, capsys, array_report):
    repo = tmp_path / 'repo'
    module = repo / 'infra'
    module.mkdir(parents=True)
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    source = module / 'main.tf'
    source.write_text('resource "sample" "one" {\n  #checkov:skip=CKV_TEST_1:reviewed debt\n}\n', encoding="utf-8")
    check = dict(check_id='CKV_TEST_1', file_path='/main.tf', file_line_range=[1, 3],
                 resource='sample.one', suppress_comment='reviewed debt', severity='HIGH')
    report = dict(results=dict(failed_checks=[], skipped_checks=[check]), summary=dict(skipped=1))
    raw = json.dumps([report] if array_report else report)
    env = clean_env()
    env['STUB_REPORT'] = raw
    command = ('function checkov { $global:LASTEXITCODE=1; $env:STUB_REPORT }; '
               f'& {ps_string(ROOT / "scripts/create-baseline.ps1")} -Tool checkov -CloudProvider aws -Force')
    result = powershell(command, module, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    monkeypatch.chdir(repo)
    monkeypatch.setattr(scan, 'run_cmd', lambda *a, **kw: (1, raw, ''))
    findings, error, _ = scan.run_checkov(str(module))
    assert not error and len(findings) == 1
    apply_exceptions(findings, repo, repo, suppressions=False)
    assert all(f['baseline'] for f in findings)
    baseline = json.loads((repo / '.scan-baseline/baseline.json').read_text(encoding="utf-8"))
    assert baseline['entries'][0]['fingerprint'] == scan.occurrence_fingerprint(findings[0], repo)
    monkeypatch.setattr(sys, 'argv', ['scan.py', str(module), '--tools', 'checkov',
                                     '--format', 'json', '--skip-suppressions'])
    with pytest.raises(SystemExit) as exited:
        scan.main()
    assert exited.value.code == 0
    output = json.loads(capsys.readouterr().out)
    assert output['scan_complete'] and output['findings'] == []
    source.write_text(source.read_text(encoding="utf-8") + '# changed\n', encoding="utf-8")
    apply_exceptions(findings, repo, repo, suppressions=False)
    assert not findings[0]['baseline']


@pytest.mark.parametrize('shell', ['pwsh', 'powershell'])
def test_noisy_scanner_still_writes_findings(tmp_path, shell):
    command = ("function trivy { Write-Error 'scanner diagnostic'; $global:LASTEXITCODE=1 }; "
               f'& {ps_string(ROOT / "scripts/scan-and-fix.ps1")} -ScanType secrets -AutoFix')
    result = powershell(command, tmp_path, env=clean_env(), executable=shell)
    assert result.returncode == 1, result.stdout + result.stderr
    data = json.loads((tmp_path / '.claude/scan-findings.json').read_text(encoding='utf-8-sig'))
    assert data['findings'][0]['exitCode'] == 1


def test_baseline_help_describes_content_bound_identity():
    help_text = (ROOT / 'scripts/create-baseline.ps1').read_text(encoding="utf-8").split('#>', 1)[0]
    assert 'occurrence_fingerprint' in help_text and 'file-content' in help_text
    assert 'Any content change' in help_text
    assert 'Line numbers are intentionally excluded' not in help_text


@pytest.mark.parametrize('name', ['README.md', 'docs/APP-CODE-SCANNING.md',
                                  'docs/consumer-repo-setup-guide.md', 'docs/CONSUMER-MIGRATION.md',
                                  'templates/scan-config/starter.yaml', 'templates/scan-config/standard.yaml',
                                  'templates/scan-config/strict.yaml'])
def test_csharp_examples_resolve_from_working_directory(name):
    text = (ROOT / name).read_text(encoding='utf-8')
    assert 'solution: "api/' not in text and 'solution: "app/' not in text
    assert 'relative to working_dir' in text
