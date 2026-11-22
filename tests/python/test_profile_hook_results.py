"""Exercise the profiler with an external runner, without running scanners."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from .tool_helpers import application

ROOT = Path(__file__).resolve().parents[2]


def profile(tmp_path, runner_source=None, extra=(), python_source=None, committed='committed.txt',
            timeout=60):
    pwsh = shutil.which('pwsh')
    if not pwsh:
        pytest.skip('PowerShell unavailable')
    tools = tmp_path / 'tools'
    if runner_source is not None:
        application(tools, 'pre-commit', runner_source)
    if python_source is not None:
        application(tools, 'python', python_source)
    repo = tmp_path / 'consumer'
    repo.mkdir()
    subprocess.run(['git', 'init', '-q', str(repo)], check=True, capture_output=True)
    (repo / committed).write_bytes(b'')
    for args in (['add', committed], ['commit', '-q', '-m', 'fixture']):
        subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                        '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=' + str(tmp_path / 'no-hooks'), *args],
                       check=True, capture_output=True)
    (repo / 'unchanged.txt').write_bytes(b'caller contents\n')
    index = repo / '.git/index'
    before_index = index.read_bytes() if index.exists() else None
    output = tmp_path / 'results'
    env = {key: value for key, value in os.environ.items() if not key.startswith(('SCAN_', 'TFLINT_'))}
    if runner_source is None:
        # Keep PowerShell's built-in commands available, but no external runner.
        env['PATH'] = str(Path(pwsh).parent)
    else:
        env['PATH'] = str(tools) + os.pathsep + env['PATH']
    result = subprocess.run(
        [pwsh, '-NoProfile', '-File', str(ROOT / 'scripts/profile-hook-performance.ps1'),
         '-Iterations', '2', '-OutputPath', str(output), *extra],
        cwd=repo, env=env, capture_output=True, text=True, encoding='utf-8', timeout=timeout)
    assert (repo / 'unchanged.txt').read_bytes() == b'caller contents\n'
    assert (index.read_bytes() if index.exists() else None) == before_index
    return result, output


@pytest.mark.parametrize('checkov_exits', [(3, 3), (3, 0), (0, 3)])
def test_profiler_separates_failures_and_records_every_exit(tmp_path, checkov_exits):
    runner = '''import sys
assert sys.argv[1] == 'run'
assert sys.argv[3:] == ['--all-files', '--hook-stage', 'pre-commit']
'''
    source = '''import sys
from pathlib import Path
if '-c' in sys.argv:  # interpreter probe
    sys.exit(0)
assert sys.argv[1:3] == ['-E', '-P']
assert Path(sys.argv[3]).name == 'pre-push.py'
assert sys.argv[4] == '--hooks'
local_ref, local, remote_ref, remote = sys.stdin.read().split()
assert len(local) == len(remote) and set(remote) == {'0'} and set(local) != {'0'}
if sys.argv[5] == 'checkov':
    counter = Path(__file__).with_suffix('.count')
    iteration = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(iteration + 1))
    sys.exit(CHECKOV_EXITS[iteration])
'''.replace('CHECKOV_EXITS', repr(checkov_exits))
    result, output = profile(tmp_path, runner, python_source=source)
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads((output / 'performance-latest.json').read_text(encoding='utf-8-sig'))
    failed = next(h for h in data['hooks'] if h['id'] == 'checkov')
    assert failed['status'] == 'FAILED'
    assert failed['exit_codes'] == list(checkov_exits)
    assert failed['average_seconds'] is None
    assert failed['within_target'] is False
    assert data['summary']['hooks_failed'] == 1
    assert data['summary']['hooks_over_target'] == 0
    assert data['summary']['pre_push_complete'] is False
    assert data['summary']['pre_push_within_target'] is False
    expected_subtotal = sum(h['average_seconds'] for h in data['hooks']
                            if h['stage'] == 'pre-push' and h['succeeded'])
    assert data['summary']['pre_push_total'] == round(expected_subtotal, 2)
    assert 'Failed hooks: 1' in result.stdout
    assert '[INCOMPLETE]' in result.stdout
    for hook in data['hooks']:
        assert len(hook['exit_codes']) == len(hook['iterations']) == 2
        if hook['id'] != 'checkov':
            assert hook['exit_codes'] == [0, 0]
            assert hook['status'] in ('OK', 'SLOW')


def test_profiler_missing_runner_never_reports_ok(tmp_path):
    result, output = profile(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads((output / 'performance-latest.json').read_text(encoding='utf-8-sig'))
    assert data['summary']['hooks_failed'] == 8
    assert data['summary']['hooks_within_target'] == 0
    assert data['summary']['slowest_hook'] is None
    assert '[OK]' not in result.stdout
    assert all(hook['exit_codes'] == [None, None] for hook in data['hooks'])
    assert all(all(hook['errors']) for hook in data['hooks'])


def test_profiler_gives_push_hooks_a_transaction_the_real_runner_accepts(tmp_path):
    for scanner in ('trivy', 'checkov', 'tflint'):
        application(tmp_path / 'tools', scanner, 'raise SystemExit(0)\n')  # no real scans or downloads
    # Two iterations of four real push-runner transactions, so allow for slow process startup.
    result, output = profile(tmp_path, 'raise SystemExit(0)\n', committed='main.tf', timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads((output / 'performance-latest.json').read_text(encoding='utf-8-sig'))
    checkov = next(h for h in data['hooks'] if h['id'] == 'checkov')
    # Reaching the pushed-policy check proves that the transaction selected the committed file.
    assert checkov['status'] == 'FAILED'
    assert 'requires tracked .scanning/configs/.checkov.yaml' in ' '.join(checkov['errors'][0].split())


def test_profiler_rejects_removed_fixture_parameter(tmp_path):
    result, output = profile(tmp_path, 'raise AssertionError("must not run")',
                             ['-FixtureDir', 'unused-fixture'])
    assert result.returncode != 0
    assert 'FixtureDir' in result.stderr
    assert not output.exists()
