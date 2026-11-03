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
    env['STUB_REPORT'] = json.dumps(dict(results=results))
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
