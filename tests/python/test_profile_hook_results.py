"""Exercise the profiler with an external runner, without running scanners."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from .tool_helpers import application

ROOT = Path(__file__).resolve().parents[2]


def profile(tmp_path, runner_source=None, extra=()):
    pwsh = shutil.which('pwsh')
    if not pwsh:
        pytest.skip('PowerShell unavailable')
    tools = tmp_path / 'tools'
    if runner_source is not None:
        application(tools, 'pre-commit', runner_source)
    repo = tmp_path / 'consumer'
    repo.mkdir()
    subprocess.run(['git', 'init', '-q', str(repo)], check=True, capture_output=True)
    (repo / 'unchanged.txt').write_bytes(b'caller contents\n')
    index = repo / '.git/index'
    before_index = index.read_bytes() if index.exists() else None
    output = tmp_path / 'results'
    env = os.environ.copy()
    if runner_source is None:
        # Keep PowerShell's built-in commands available, but no external runner.
        env['PATH'] = str(Path(pwsh).parent)
    else:
        env['PATH'] = str(tools) + os.pathsep + env['PATH']
    result = subprocess.run(
        [pwsh, '-NoProfile', '-File', str(ROOT / 'scripts/profile-hook-performance.ps1'),
         '-Iterations', '2', '-OutputPath', str(output), *extra],
        cwd=repo, env=env, capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert (repo / 'unchanged.txt').read_bytes() == b'caller contents\n'
    assert (index.read_bytes() if index.exists() else None) == before_index
    return result, output


@pytest.mark.parametrize('checkov_exits', [(3, 3), (3, 0), (0, 3)])
def test_profiler_separates_failures_and_records_every_exit(tmp_path, checkov_exits):
    source = '''import sys
from pathlib import Path
assert sys.argv[1] == 'run'
assert sys.argv[3:] in (['--all-files', '--hook-stage', 'pre-commit'],
                        ['--all-files', '--hook-stage', 'pre-push'])
if sys.argv[2] == 'checkov':
    counter = Path(__file__).with_suffix('.count')
    iteration = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(iteration + 1))
    sys.exit(CHECKOV_EXITS[iteration])
'''.replace('CHECKOV_EXITS', repr(checkov_exits))
    result, output = profile(tmp_path, source)
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


def test_profiler_rejects_removed_fixture_parameter(tmp_path):
    result, output = profile(tmp_path, 'raise AssertionError("must not run")',
                             ['-FixtureDir', 'unused-fixture'])
    assert result.returncode != 0
    assert 'FixtureDir' in result.stderr
    assert not output.exists()
