"""Destination-scoped push selection and on-demand working-tree builds."""
import json
import os
import shutil
import subprocess
import sys

import pytest

from .test_validation_targets import (
    ZERO, consumer, git, isolate_inherited_git_environment, load_push_runner, package,
)


@pytest.mark.parametrize('destination', ['origin', 'url', 'empty', None])
@pytest.mark.parametrize('default', ['missing', 'unrelated'])
def test_new_branch_fallback_uses_only_destination_refs(consumer, package, monkeypatch, destination, default):
    base = git(consumer, 'rev-parse', 'HEAD')
    git(consumer, 'remote', 'add', 'origin', 'https://example.test/destination.git')
    git(consumer, 'update-ref', 'refs/remotes/origin/main', base)
    if default == 'unrelated':
        tree = git(consumer, 'rev-parse', 'HEAD^{tree}')
        unrelated = git(consumer, 'commit-tree', tree, '-m', 'unrelated root')
        git(consumer, 'update-ref', 'refs/remotes/origin/default', unrelated)
        git(consumer, 'symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/default')
    (consumer / 'new.tf').write_text('# must scan at destination\n')
    git(consumer, 'add', '.')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'branch change')
    tip = git(consumer, 'rev-parse', 'HEAD')
    # A prefix-sharing remote and its default both know the entire pushed tip.
    git(consumer, 'update-ref', 'refs/remotes/origin-mirror/main', tip)
    git(consumer, 'symbolic-ref', 'refs/remotes/origin-mirror/HEAD', 'refs/remotes/origin-mirror/main')
    runner = load_push_runner(package)
    monkeypatch.chdir(consumer)
    remote = 'https://example.test/destination.git' if destination == 'url' else destination
    selected = set(runner.changed_paths(tip, ZERO, remote))
    assert selected == ({'new.tf'} if destination in ('origin', 'url') else {'App.cs', 'App.sln', 'new.tf'})


@pytest.mark.parametrize('mode', ['configured', 'discovered', 'root-discovered'])
@pytest.mark.parametrize('build_exit', [0, 7])
def test_on_demand_csharp_builds_working_tree(tmp_path, package, mode, build_exit):
    result, trace = run_csharp(tmp_path, package, mode, build_exit=build_exit)
    assert result.returncode == int(build_exit != 0), result.stdout + result.stderr
    call = json.loads(trace.read_text())
    expected_dir = tmp_path if mode == 'root-discovered' else tmp_path / 'source space'
    assert call['cwd'] == str(expected_dir)
    assert call['args'][0] == 'build'
    assert (expected_dir / call['args'][1]).resolve() == (expected_dir / 'Chosen.sln').resolve()
    assert call['args'][2:] == ['/p:AnalysisMode=AllEnabledByDefault', '--nologo']
    assert ('PASS' if build_exit == 0 else 'FAIL') in result.stdout


@pytest.mark.parametrize('mode', ['missing-configured', 'missing-discovered', 'bad-working-dir', 'cannot-start'])
def test_on_demand_csharp_reports_incomplete_build(tmp_path, package, mode):
    result, trace = run_csharp(tmp_path, package, mode)
    assert result.returncode == 1, result.stdout + result.stderr
    assert not trace.exists()
    report = json.loads((tmp_path / '.claude/scan-findings.json').read_text(encoding='utf-8-sig'))
    assert report['summary'] == {'total': 1, 'passed': 0, 'failed': 1}
    finding, = report['findings']
    assert finding['passed'] is False
    assert finding['exitCode'] != 0
    assert ('No solution' in finding['outputTail'] if mode.startswith('missing') else
            'working' in finding['outputTail'].lower() if mode == 'bad-working-dir' else
            'cannot start' in finding['outputTail'])


def run_csharp(tmp_path, package, mode, build_exit=0):
    pwsh = shutil.which('pwsh')
    if not pwsh:
        pytest.skip('PowerShell unavailable')
    folder = tmp_path if mode == 'root-discovered' else tmp_path / 'source space'
    folder.mkdir(exist_ok=True)
    if not mode.startswith('missing'):
        (folder / 'Chosen.sln').write_text('working-tree solution')
    if mode == 'configured':
        # A solution discovery would pick first must not override configuration.
        (folder / 'Aardvark.sln').write_text('not the configured solution')
    config = {'languages': {'csharp': {'build': {
        'working_dir': 'absent' if mode == 'bad-working-dir' else str(folder.relative_to(tmp_path)),
        'solution': '' if mode in ('discovered', 'root-discovered', 'missing-discovered') else 'Chosen.sln',
    }}}}
    # JSON is YAML too; keep this harness independent of a PowerShell YAML module.
    (tmp_path / 'scan-config.yaml').write_text(json.dumps(config))
    trace = tmp_path / 'build-trace'
    mock = tmp_path / 'build.py'
    mock.write_text('import json,os,pathlib,sys\n'
                    'pathlib.Path(os.environ["BUILD_TRACE"]).write_text(json.dumps({"cwd":os.getcwd(),"args":sys.argv[1:]}))\n'
                    'sys.exit(int(os.environ["BUILD_EXIT"]))\n')
    bootstrap = tmp_path / 'run.ps1'
    bootstrap.write_text(
        "function dotnet { throw 'cannot start build' }\n" if mode == 'cannot-start' else
        'function dotnet { & $env:BUILD_PY $env:BUILD_MOCK @args }\n')
    with bootstrap.open('a') as output:
        output.write('& $args[0] -ScanType csharp -AutoFix\nexit $LASTEXITCODE\n')
    env = {key: value for key, value in os.environ.items() if not key.startswith(('GIT_', 'SCAN_'))}
    env.update(BUILD_TRACE=str(trace), BUILD_EXIT=str(build_exit), BUILD_PY=sys.executable, BUILD_MOCK=str(mock))
    result = subprocess.run([pwsh, '-NoProfile', '-File', str(bootstrap), str(package / 'scripts/scan-and-fix.ps1')],
                            cwd=tmp_path, env=env, text=True, capture_output=True, timeout=60)
    return result, trace
