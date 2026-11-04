"""Exercise setup status and explicit baseline approval contexts."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

import scan_policy
import setup_scan_fix

ROOT = Path(__file__).resolve().parents[2]
REAL_SKIP_SOURCE = ('resource "aws_s3_bucket" "sample" {\n'
                    '  #checkov:skip=CKV_AWS_20:Reviewed exception\n'
                    '  bucket = "baseline-fixture"\n}\n')


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


@pytest.mark.parametrize('revision', ['missing', 'tree', 'blob', 'option'])
def test_baseline_rejects_invalid_base_before_scanning(tmp_path, revision):
    repo = tmp_path / 'repo'
    repo.mkdir()

    def git(*args):
        return subprocess.run(['git', '-C', str(repo), *args], check=True,
                              text=True, capture_output=True).stdout.strip()

    git('init', '-q')
    git('config', 'user.name', 'Test')
    git('config', 'user.email', 'test@example.com')
    (repo / 'main.tf').write_text('resource "sample" "one" {}\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-qm', 'base')
    value = {'missing': 'missing-base', 'tree': git('rev-parse', 'HEAD^{tree}'),
             'blob': git('rev-parse', 'HEAD:main.tf'), 'option': '--fixture-option'}[revision]
    baseline = repo / '.scan-baseline/baseline.json'
    baseline.parent.mkdir()
    baseline.write_text('existing reviewed baseline', encoding='utf-8')
    command = ('function checkov { throw "scanner must not run" }; '
               f'& {ps_string(ROOT / "scripts/create-baseline.ps1")} -Tool checkov '
               f'-CloudProvider aws -Force -BaseCommit {ps_string(value)}')
    result = powershell(command, repo, env=clean_env())
    assert result.returncode != 0, result.stdout + result.stderr
    assert 'BaseCommit must identify an existing commit' in result.stderr
    assert 'scanner must not run' not in result.stdout + result.stderr
    assert baseline.read_text(encoding='utf-8') == 'existing reviewed baseline'


@pytest.mark.parametrize('failed_step', ['runner', 'verification', 'both'])
@pytest.mark.parametrize('failure', ['exit', 'os-error'])
def test_setup_records_runner_and_verification_failures(tmp_path, monkeypatch, capsys, failed_step, failure):
    repo = tmp_path / 'repo'
    repo.mkdir()
    tools = {name: str(tmp_path / (name + '.exe')) for name in ('lefthook', 'pwsh')}
    for path in tools.values():
        Path(path).write_bytes(b'fixture')
    monkeypatch.setattr(setup_scan_fix.shutil, 'which', lambda name: tools.get(name))
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        target = ('runner' if command[0] == tools['lefthook'] else
                  'verification' if command[0] == tools['pwsh'] else None)
        if target and failed_step in (target, 'both'):
            if failure == 'os-error':
                raise OSError('fixture launch failed')
            if kwargs.get('check'):
                raise subprocess.CalledProcessError(7, command, output='', stderr='fixture failure')
            return subprocess.CompletedProcess(command, 7)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, 'run', run)
    assert setup_scan_fix.main(['setup', '--repo-path', str(repo)]) == 1
    output = capsys.readouterr().out
    assert '=== SETUP COMPLETED WITH ERRORS ===' in output
    for target, label in [('runner', 'lefthook installation'), ('verification', 'scan verification')]:
        assert (f'FAILED: {label}' in output) == (failed_step in (target, 'both'))
        if failed_step in (target, 'both'):
            assert f'[OK]   {label}' not in output
    assert 'lefthook installed' not in output
    assert any(command[0] == tools['pwsh'] for command in calls)
    assert (repo / '.github/workflows/code-security-scan.yml').is_file()


@pytest.mark.parametrize('authority', ['checkout', 'commit'])
@pytest.mark.parametrize('approved', [False, True])
@pytest.mark.parametrize('scoped', [False, True])
def test_baseline_uses_explicit_approval_context(tmp_path, authority, approved, scoped):
    repo, trusted = tmp_path / 'repo', tmp_path / 'trusted'
    module = repo / 'infra'
    module.mkdir(parents=True)
    (trusted / 'infra').mkdir(parents=True)
    source = ('resource "sample" "one" {\n'
              '  #checkov:skip=CKV_TEST_1:Reviewed exception\n}\n')
    without_skip = source.replace('  #checkov:skip=CKV_TEST_1:Reviewed exception\n', '')

    def git(*args):
        return subprocess.run(['git', '-C', str(repo), *args], check=True,
                              text=True, capture_output=True).stdout.strip()

    git('init', '-q')
    git('config', 'user.name', 'Test')
    git('config', 'user.email', 'test@example.com')
    path = module / 'main.tf'
    path.write_text(source if approved else without_skip, encoding='utf-8')
    (trusted / 'infra/main.tf').write_text(path.read_text(encoding='utf-8'), encoding='utf-8')
    git('add', '.')
    git('commit', '-qm', 'base')
    base_commit = git('rev-parse', 'HEAD')
    # Deliberately give the local default ref the opposite approval decision.
    path.write_text(without_skip if approved else source, encoding='utf-8')
    git('add', '.')
    git('commit', '-qm', 'local reference')
    git('update-ref', 'refs/remotes/origin/main', git('rev-parse', 'HEAD'))
    path.write_text(source, encoding='utf-8')
    check = dict(check_id='CKV_TEST_1', file_path='/main.tf', file_line_range=[1, 3],
                 resource='sample.one', severity='HIGH')
    results = dict(failed_checks=[], skipped_checks=[check])
    env = clean_env()
    env['STUB_REPORT'] = json.dumps(dict(results=results, summary=dict(skipped=1)))
    option = (f'-PolicyRoot {ps_string(trusted)}' if authority == 'checkout' else
              f'-BaseCommit {base_commit}')
    directory = '-MonorepoScope infra' if scoped else '-TerraformDir infra'
    command = ('function checkov { $global:LASTEXITCODE=1; $env:STUB_REPORT }; '
               f'& {ps_string(ROOT / "scripts/create-baseline.ps1")} -Tool checkov '
               f'-CloudProvider aws -Force {directory} {option}')
    result = powershell(command, repo, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    baseline = json.loads((repo / '.scan-baseline/baseline.json').read_text(encoding='utf-8'))
    options = dict(policy_root=trusted) if authority == 'checkout' else dict(base_commit=base_commit)
    pending = scan_policy.checkov_checks(results, repo, scan_directory=module, **options)
    assert len(baseline['entries']) == len(pending) == int(not approved)
    if pending:
        assert baseline['entries'][0]['file'] == 'infra/main.tf'
        assert baseline['entries'][0]['fingerprint'] == scan_policy.occurrence_fingerprint(
            dict(tool='checkov', rule_id=check['check_id'], file='infra/main.tf',
                 resource='sample.one', line=1, end_line=3), repo)


@pytest.mark.parametrize('report_source', ['captured', 'live'])
def test_baseline_retains_skips_from_real_scanner_reports(tmp_path, report_source):
    """Quiet output must not erase a skipped record before gate normalization."""
    repo = tmp_path / 'repo'
    repo.mkdir()
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    (repo / 'main.tf').write_text(REAL_SKIP_SOURCE, encoding='utf-8')
    if report_source == 'live':
        runner = pytest.importorskip('checkov.terraform.runner')
        filters = pytest.importorskip('checkov.runner_filter')
        report = runner.Runner().run(root_folder=str(repo), runner_filter=filters.RunnerFilter(
            checks=['CKV_AWS_20'], download_external_modules=False))
        reports = dict(full=report.get_dict(), quiet=report.get_dict(is_quiet=True))
    else:
        reports = json.loads((ROOT / 'tests/fixtures/checkov-baseline-reports.json').read_text(encoding='utf-8'))
        assert reports['full']['summary']['checkov_version'] == '3.3.8'
    assert len(reports['full']['results']['skipped_checks']) == 1
    assert 'skipped_checks' not in reports['quiet']['results']
    for name, report in reports.items():
        (tmp_path / f'{name}.json').write_text(json.dumps(report), encoding='utf-8')
    env = clean_env()
    env.update(FULL_REPORT=str(tmp_path / 'full.json'), QUIET_REPORT=str(tmp_path / 'quiet.json'))
    # Replay the real serializer's two output modes, honoring the actual CLI args.
    command = ('function checkov { $global:LASTEXITCODE=0; '
               'if ($args -contains "--quiet") { Get-Content -Raw $env:QUIET_REPORT } '
               'else { Get-Content -Raw $env:FULL_REPORT } }; '
               f'& {ps_string(ROOT / "scripts/create-baseline.ps1")} -Tool checkov -CloudProvider aws -Force')
    result = powershell(command, repo, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    entries = json.loads((repo / '.scan-baseline/baseline.json').read_text(encoding='utf-8'))['entries']
    pending = scan_policy.checkov_checks(reports['full']['results'], repo)
    assert len(entries) == len(pending) == 1
    assert entries[0]['rule_id'] == pending[0]['check_id'] == 'CKV_AWS_20'
    assert entries[0]['fingerprint'] == scan_policy.occurrence_fingerprint(
        dict(tool='checkov', rule_id='CKV_AWS_20', file='main.tf',
             resource='aws_s3_bucket.sample', line=1, end_line=4), repo)


@pytest.mark.parametrize('mode', ['missing', 'missing-count', 'missing-summary', 'truncated', 'boolean', 'negative'])
def test_baseline_rejects_incomplete_skip_records_without_overwriting(tmp_path, mode):
    repo = tmp_path / 'repo'
    repo.mkdir()
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    (repo / 'main.tf').write_text(REAL_SKIP_SOURCE, encoding='utf-8')
    reports = json.loads((ROOT / 'tests/fixtures/checkov-baseline-reports.json').read_text(encoding='utf-8'))
    report = reports['quiet' if mode in ('missing', 'negative') else 'full']
    if mode == 'missing-count':
        del report['summary']['skipped']
    elif mode == 'missing-summary':
        del report['summary']
    elif mode != 'missing':
        report['summary']['skipped'] = {'truncated': 2, 'boolean': True, 'negative': -1}[mode]
    existing = repo / '.scan-baseline/baseline.json'
    existing.parent.mkdir()
    existing.write_text('previously reviewed baseline', encoding='utf-8')
    env = clean_env()
    env['SCANNER_REPORT'] = json.dumps(report)
    # Configuration can select quiet output even without an explicit CLI flag.
    command = ('function checkov { $global:LASTEXITCODE=0; $env:SCANNER_REPORT }; '
               f'& {ps_string(ROOT / "scripts/create-baseline.ps1")} -Tool checkov -CloudProvider aws -Force')
    result = powershell(command, repo, env=env)
    assert result.returncode != 0, result.stdout + result.stderr
    assert existing.read_text(encoding='utf-8') == 'previously reviewed baseline'
    assert 'Created Successfully' not in result.stdout


@pytest.mark.parametrize('failed_step', ['runner', 'verification', 'both'])
@pytest.mark.parametrize('failure', ['exit', 'launch'])
def test_shell_setup_records_runner_and_verification_failures(tmp_path, failed_step, failure):
    """Run the real shell setup and verifier process, including nonzero exits."""
    platform = tmp_path / 'platform'
    for folder in ('scripts', 'hooks', 'schemas', 'templates', 'configs'):
        shutil.copytree(ROOT / folder, platform / folder, ignore=shutil.ignore_patterns('__pycache__'))
    repo = tmp_path / 'repo'
    repo.mkdir()
    tools = tmp_path / 'tools'
    tools.mkdir()
    for name, path, marker in [('runner', tools / 'lefthook.ps1', 'RUNNER_REACHED'),
                               ('verification', platform / 'scripts/verify-scanning.ps1', 'VERIFY_REACHED')]:
        action = ("throw 'fixture launch failure'" if failure == 'launch' else 'exit 7') if failed_step in (name, 'both') else 'exit 0'
        path.write_text(f"Write-Output '{marker}'\n{action}\n", encoding='utf-8')
    env = clean_env()
    env['RUNNER_TOOL'] = str(tools / 'lefthook.ps1')
    command = ('function Get-Command { param($Name, $CommandType, $ErrorAction) '
               'if ($Name -eq "lefthook") { [pscustomobject]@{ Source=$env:RUNNER_TOOL } } '
               'elseif ($Name -notin @("pre-commit", "gh")) { '
               'Microsoft.PowerShell.Core\\Get-Command @PSBoundParameters } }; '
               f'& {ps_string(platform / "scripts/setup-scan-fix.ps1")} -RepoPath {ps_string(repo)}')
    result = powershell(command, tmp_path, env=env)
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert '=== SETUP COMPLETED WITH ERRORS ===' in output
    for step, label in [('runner', 'lefthook installation'), ('verification', 'scan verification')]:
        assert (f'FAILED: {label}' in output) == (failed_step in (step, 'both'))
        if failed_step in (step, 'both'):
            assert f'[OK]   {label}' not in output
    assert 'VERIFY_REACHED' in output
    assert (repo / '.github/workflows/code-security-scan.yml').is_file()
