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


@pytest.mark.parametrize('default', [False, True])
@pytest.mark.parametrize('mapping', ['nested-name', 'custom-target', 'negative'])
def test_destination_ref_ownership_is_unambiguous(consumer, package, monkeypatch, default, mapping):
    base = git(consumer, 'rev-parse', 'HEAD')
    git(consumer, 'remote', 'add', 'origin', 'https://example.test/destination.git')
    # Existing configs can overlap even on Git versions that reject adding a
    # slash-separated remote with `remote add` after its parent already exists.
    git(consumer, 'config', 'remote.origin/mirror.url', 'https://example.test/mirror.git')
    git(consumer, 'config', 'remote.origin/mirror.fetch', '+refs/heads/*:refs/remotes/origin/mirror/*')
    git(consumer, 'update-ref', 'refs/remotes/origin/main', base)
    if default:
        git(consumer, 'symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/main')
    (consumer / 'new.tf').write_text('# must scan despite overlapping remote mappings\n')
    git(consumer, 'add', '.')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'branch change')
    tip = git(consumer, 'rev-parse', 'HEAD')
    if mapping == 'custom-target':
        git(consumer, 'config', '--replace-all', 'remote.origin.fetch', '+refs/heads/*:refs/scan/destination/*')
        git(consumer, 'update-ref', 'refs/scan/destination/main', base)
        # A default alias to a different namespace cannot justify exclusion.
        if default:
            git(consumer, 'symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/mirror/main')
    elif mapping == 'negative':
        git(consumer, 'config', '--remove-section', 'remote.origin/mirror')
        git(consumer, 'config', '--add', 'remote.origin.fetch', '^refs/heads/mirror/*')
    git(consumer, 'update-ref', 'refs/remotes/origin/mirror/main', tip)
    runner = load_push_runner(package)
    monkeypatch.chdir(consumer)
    expected = {'App.cs', 'App.sln', 'new.tf'} if mapping == 'custom-target' else {'new.tf'}
    assert set(runner.changed_paths(tip, ZERO, 'origin')) == expected


@pytest.mark.parametrize('existing', [False, True])
@pytest.mark.parametrize('mixed', [False, True])
@pytest.mark.parametrize('target', [
    'refs/heads/*', 'refs/tags/*', 'refs/notes/*', 'refs/stash', 'HEAD',
    'refs/scan/*', 'topic',
])
def test_local_fetch_targets_scan_conservatively(consumer, package, monkeypatch, existing, mixed, target):
    base = git(consumer, 'rev-parse', 'HEAD')
    git(consumer, 'remote', 'add', 'origin', 'https://example.test/destination.git')
    source = 'refs/heads/*' if '*' in target else 'refs/heads/topic'
    git(consumer, 'config', '--replace-all', 'remote.origin.fetch', f'+{source}:{target}')
    if mixed:
        git(consumer, 'config', '--add', 'remote.origin.fetch', '+refs/heads/*:refs/remotes/origin/*')
    (consumer / 'new.tf').write_text('# local refs cannot establish destination ancestry\n')
    git(consumer, 'add', '.')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'branch change')
    tip = git(consumer, 'rev-parse', 'HEAD')
    if target != 'HEAD':
        git(consumer, 'update-ref', target.replace('*', 'topic'), tip)
    # Even a usable tracking default must not narrow an ambiguous destination.
    git(consumer, 'update-ref', 'refs/remotes/origin/main', tip)
    git(consumer, 'symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/main')
    runner = load_push_runner(package)
    monkeypatch.chdir(consumer)
    expected = {'new.tf'} if existing else {'App.cs', 'App.sln', 'new.tf'}
    assert set(runner.changed_paths(tip, base if existing else ZERO, 'origin')) == expected
    assert runner.destination_refs('origin') == ([], [])


@pytest.mark.parametrize('target', ['refs/heads/topic', 'refs/tags/topic', 'refs/notes/topic', 'refs/stash', 'HEAD'])
@pytest.mark.parametrize('chain', [False, True])
def test_tracking_symbolic_refs_cannot_exclude_local_commits(consumer, package, monkeypatch, target, chain):
    git(consumer, 'remote', 'add', 'origin', 'https://example.test/destination.git')
    (consumer / 'new.tf').write_text('# symbolic tracking aliases must not exclude local commits\n')
    git(consumer, 'add', '.')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'branch change')
    tip = git(consumer, 'rev-parse', 'HEAD')
    if target != 'HEAD':
        git(consumer, 'update-ref', target, tip)
    if chain:
        git(consumer, 'symbolic-ref', 'refs/remotes/origin/alias', target)
        target = 'refs/remotes/origin/alias'
    git(consumer, 'symbolic-ref', 'refs/remotes/origin/main', target)
    git(consumer, 'symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/main')
    runner = load_push_runner(package)
    monkeypatch.chdir(consumer)
    assert runner.destination_refs('origin') == ([], [])
    assert set(runner.changed_paths(tip, ZERO, 'origin')) == {'App.cs', 'App.sln', 'new.tf'}


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


@pytest.mark.parametrize('mode', ['configured', 'discovered', 'root-discovered', 'deep-discovered'])
@pytest.mark.parametrize('build_exit', [0, 7])
def test_on_demand_csharp_builds_working_tree(tmp_path, package, mode, build_exit):
    result, trace = run_csharp(tmp_path, package, mode, build_exit=build_exit)
    assert result.returncode == int(build_exit != 0), result.stdout + result.stderr
    call = json.loads(trace.read_text())
    expected_dir = tmp_path if mode in ('root-discovered', 'deep-discovered') else tmp_path / 'source space'
    assert call['cwd'] == str(expected_dir)
    assert call['args'][0] == 'build'
    solution_dir = tmp_path / 'one/two/three/four/five' if mode == 'deep-discovered' else expected_dir
    assert (expected_dir / call['args'][1]).resolve() == (solution_dir / 'Chosen.sln').resolve()
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
    folder = (tmp_path if mode == 'root-discovered' else tmp_path / 'one/two/three/four/five'
              if mode == 'deep-discovered' else tmp_path / 'source space')
    folder.mkdir(parents=True, exist_ok=True)
    if not mode.startswith('missing'):
        (folder / 'Chosen.sln').write_text('working-tree solution')
    if mode == 'configured':
        # A solution discovery would pick first must not override configuration.
        (folder / 'Aardvark.sln').write_text('not the configured solution')
    config = {'languages': {'csharp': {'enabled': True, 'build': {
        'working_dir': 'absent' if mode == 'bad-working-dir' else str(folder.relative_to(tmp_path)),
        'solution': '' if mode in ('discovered', 'root-discovered', 'missing-discovered') else 'Chosen.sln',
    }}}}
    if mode == 'deep-discovered':
        # No opt-in or configured paths: both eligibility and solution discovery
        # must reach this solution beyond the old depth-three discovery boundary.
        config = {}
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


@pytest.mark.parametrize('scan_type', ['csharp', 'all'])
@pytest.mark.parametrize('dotnet_available', [False, True])
@pytest.mark.parametrize('config,project,expected', [
    (None, None, 0),
    ('{}', None, 0),
    ('languages:\n  csharp:\n    enabled: true\n', None, 1),
    (None, 'src/deep/nested/app.csproj', 1),
    (None, 'app.sln', 1),
    (None, 'app.slnx', 1),
    ('languages:\n  csharp:\n    enabled: false\n', 'app.sln', 0),
    *[(None, f'{folder}/nested/app.csproj', 0)
      for folder in ('.git', 'bin', 'obj', 'node_modules')],
    ('languages:\n  csharp:\n    enabled: "false"\n', 'app.sln', 1),
])
def test_csharp_eligibility(tmp_path, package, scan_type, dotnet_available, config, project, expected):
    pwsh = shutil.which('pwsh')
    if not pwsh:
        pytest.skip('PowerShell unavailable')
    if config is not None:
        (tmp_path / 'scan-config.yaml').write_text(config)
    if project:
        source = tmp_path / project
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text('fixture')
    # Isolate every scanner from locally installed tools. A C# build must never
    # run for skipped cases; otherwise a failing mock keeps this test offline.
    (package / 'hooks/semgrep-typescript.ps1').write_text('exit 0\n')
    bootstrap = tmp_path / 'eligibility.ps1'
    bootstrap.write_text(
        'function trivy { $global:LASTEXITCODE = 0 }\n'
        'function semgrep { $global:LASTEXITCODE = 0 }\n'
        'function dotnet { "ERROR: fixture build failure"; $global:LASTEXITCODE = 7 }\n'
        + ('' if dotnet_available else
           'function Get-Command { param($Name)\n'
           ' if ($Name -eq "dotnet") { return $null }\n'
           ' Microsoft.PowerShell.Core\\Get-Command $Name -ErrorAction SilentlyContinue\n}\n')
        + '& $args[0] -ScanType $args[1] -AutoFix\nexit $LASTEXITCODE\n')
    env = {key: value for key, value in os.environ.items() if not key.startswith(('GIT_', 'SCAN_'))}
    result = subprocess.run([pwsh, '-NoProfile', '-File', str(bootstrap),
                             str(package / 'scripts/scan-and-fix.ps1'), scan_type],
                            cwd=tmp_path, env=env, text=True, capture_output=True, timeout=60)
    assert result.returncode == expected, result.stdout + result.stderr
    report_path = tmp_path / '.claude/scan-findings.json'
    if expected == 0:
        assert 'skipping C#' in result.stdout
        assert 'dotnet build (Roslyn)' not in result.stdout
        assert not report_path.exists()
    elif config and '"false"' in config:
        assert 'must be a boolean' in result.stderr
    else:
        report = json.loads(report_path.read_text(encoding='utf-8-sig'))
        finding, = [item for item in report['findings'] if not item['passed']]
        assert finding['tool'] == 'dotnet build (Roslyn)'
        assert ('dotnet not found' if project and project.endswith(('.sln', '.slnx')) and not dotnet_available
                else 'fixture build failure' if project and project.endswith(('.sln', '.slnx'))
                else 'No solution found') in finding['outputTail']


def test_stop_hook_csharp_failure_has_relevant_remediation(package):
    pwsh = shutil.which('pwsh')
    if not pwsh:
        pytest.skip('PowerShell unavailable')
    (package / 'scan-config.yaml').write_text('languages:\n  csharp:\n    enabled: true\n')
    env = {key: value for key, value in os.environ.items() if not key.startswith(('GIT_', 'SCAN_'))}
    env['CC_STOP_SCAN_TYPE'] = 'csharp'
    stop_hook = os.path.join(os.path.dirname(__file__), '../../templates/claude/hooks/stop-scan.ps1')
    result = subprocess.run([pwsh, '-NoProfile', '-File', stop_hook], input='{}', cwd=package,
                            env=env, text=True, capture_output=True, timeout=60)
    assert result.returncode == 2, result.stdout + result.stderr
    assert 'dotnet build (Roslyn)' in result.stderr
    assert 'build/configuration errors' in result.stderr
    assert 'vault' not in result.stderr
