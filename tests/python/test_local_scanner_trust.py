"""Local scanner policy and source bytes have explicit trust boundaries."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from .test_validation_targets import scanner

ROOT = Path(__file__).resolve().parents[2]


def load_runner(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'hooks' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(repo, *args):
    return subprocess.check_output(['git', *args], cwd=repo).decode().strip()


@pytest.fixture
def consumer(tmp_path, monkeypatch):
    for key in tuple(os.environ):
        if key.startswith(('GIT_', 'SCAN_')):
            monkeypatch.delenv(key)
    repo = tmp_path / 'consumer'
    repo.mkdir()
    git(repo, 'init', '-q')
    monkeypatch.chdir(repo)
    return repo


@pytest.mark.parametrize('content', ['external-checks-dir: example', 'external-checks-git: example',
                                   'external-modules-download-path: example', 'output-file-path: example',
                                   'future-option: example', 'download-external-modules: true',
                                   'skip-check: {invalid: mapping}', 'skip-check: [', '[]'])
def test_driver_rejects_nonpassive_policy_before_launch(consumer, content, monkeypatch):
    import scan
    policy = consumer / 'policy.yaml'
    policy.write_text(content)
    launched = []
    def run(*args, **kwargs):
        launched.append(args)
        return 0, '{"results":{"failed_checks":[],"skipped_checks":[]}}', ''
    monkeypatch.setattr(scan, 'run_cmd', run)
    assert scan.run_checkov(consumer, config_file=policy)[1] is True
    assert launched == []


def test_driver_policy_root_selects_policy_and_disables_discovery(consumer, tmp_path, monkeypatch):
    import scan
    untrusted = consumer / '.scanning/configs/.checkov.yaml'
    untrusted.parent.mkdir(parents=True)
    untrusted.write_text('external-checks-dir: example\n')
    trusted = tmp_path / 'policy'
    (trusted / '.scanning/configs').mkdir(parents=True)
    (trusted / '.scanning/configs/.checkov.yaml').write_text('skip-check: [CKV_AWS_19]\n')
    seen = []
    def run(cmd, **kwargs):
        selected = Path(cmd[cmd.index('--config-file') + 1])
        seen.append(selected.read_text())
        return 0, '{"results":{"failed_checks":[],"skipped_checks":[]}}', ''
    monkeypatch.setattr(scan, 'run_cmd', run)
    assert scan.run_checkov(consumer, config_file=untrusted, trusted_root=trusted)[1] is False
    assert len(seen) == 1 and 'CKV_AWS_19' in seen[0] and 'external-checks' not in seen[0]
    seen.clear()
    assert scan.run_checkov(consumer)[1] is False
    assert len(seen) == 1 and 'external-checks' not in seen[0]


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
def test_push_rejects_nonpassive_policy_before_hook(consumer, monkeypatch, shell):
    policy = consumer / '.scanning/configs/.checkov.yaml'
    policy.parent.mkdir(parents=True)
    policy.write_text('external-checks-dir: example\n')
    (consumer / 'main.tf').write_text('resource "sample" "one" {}\n')
    git(consumer, 'add', '.')
    tree = git(consumer, 'write-tree')
    runner = load_runner('policy_push', 'pre-push.py')
    monkeypatch.setattr(runner, 'tips', lambda _: [(tree, '0' * 40)])
    monkeypatch.setattr(runner, 'changed_paths', lambda *a: ['main.tf'])
    monkeypatch.setattr(runner, 'select_shell', lambda _: (shell, 'unused'))
    launched = []
    original = subprocess.run
    def run(command, **kwargs):
        if command[0] == 'git':
            return original(command, **kwargs)
        launched.append(command)
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(runner.subprocess, 'run', run)
    with pytest.raises(ValueError, match='Checkov policy'):
        runner.scan('transaction', [('checkov', [])], shell)
    assert launched == []


@pytest.fixture
def package(tmp_path):
    package = tmp_path / 'package'
    shutil.copytree(ROOT / 'hooks', package / 'hooks')
    shutil.copytree(ROOT / 'scripts', package / 'scripts')
    for path in package.rglob('*.sh'):
        path.write_text(path.read_text(), encoding='utf-8', newline='\n')
    return package


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('hook,source,tool', [
    ('semgrep-csharp', 'App.cs', 'semgrep'),
    ('semgrep-typescript', 'app.ts', 'semgrep'),
    ('trivy-iac-critical', 'main.tf', 'trivy'),
    ('sqlfluff', 'query.sql', 'sqlfluff'),
])
def test_scanners_read_index_bytes(consumer, package, tmp_path, hook, source, tool, shell):
    runner = load_runner('shell_lookup', 'pre-push.py')
    _, executable = runner.select_shell(shell)
    (consumer / source).write_text('staged-review-marker\n')
    git(consumer, 'add', '--', source)
    (consumer / source).write_text('worktree-review-marker\n')
    trace = tmp_path / 'trace.json'
    binary = tmp_path / 'bin'
    binary.mkdir()
    probe = binary / 'probe.py'
    probe.write_text('''import json, os, pathlib, sys
root = pathlib.Path.cwd()
files = {p.name: p.read_text() for p in root.rglob('*') if p.is_file() and p.suffix in ('.cs','.ts','.tf','.sql')}
pathlib.Path(os.environ['TRACE']).write_text(json.dumps({'cwd':str(root),'files':files}))
if '--output' in sys.argv:
    pathlib.Path(sys.argv[sys.argv.index('--output')+1]).write_text(json.dumps({'results':[
        {'check_id':'review-rule','path':next(iter(files)), 'start':{'line':1}, 'end':{'line':1},
         'extra':{'severity':'ERROR','message':'Review finding'}}]}))
print('{"Results":[]}')
sys.exit(1 if any('staged-review-marker' in text for text in files.values()) else 0)
''')
    (binary / tool).write_text(f'#!/usr/bin/env bash\n"{Path(sys.executable).as_posix()}" "{probe.as_posix()}" "$@"\n', newline='\n')
    (binary / tool).chmod(0o755)
    (binary / f'{tool}.cmd').write_text(f'@"{sys.executable}" "{probe}" %*\n')
    env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ['PATH'], TRACE=str(trace))
    command = ([executable, '-NoProfile', '-File'] if shell == 'ps1' else [executable])
    result = subprocess.run(command + [str(package / f'hooks/{hook}.{shell}')], cwd=consumer,
                            env=env, capture_output=True, text=True)
    assert trace.exists(), result.stdout + result.stderr
    seen = json.loads(trace.read_text())
    assert Path(seen['cwd']) != consumer
    assert seen['files'][source] == 'staged-review-marker\n'
    assert (consumer / source).read_text() == 'worktree-review-marker\n'
    assert result.returncode == 1, result.stdout + result.stderr
    assert not Path(seen['cwd']).exists()


def test_missing_tracking_refs_are_quiet_in_powershell(consumer):
    pwsh = shutil.which('pwsh')
    if not pwsh:
        pytest.skip('PowerShell unavailable')
    result = subprocess.run([pwsh, '-NoProfile', '-Command',
        f"$ErrorActionPreference='Stop'; . '{(ROOT / 'hooks/lib/common.ps1').as_posix()}'; "
        "Get-ChangedFilesForDetect; Write-Output 'completed'"], cwd=consumer, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'completed'
    assert result.stderr == ''


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
def test_tracking_reference_probes_request_quiet_mode(shell):
    source = (ROOT / f'hooks/lib/common.{shell}').read_text()
    if shell == 'sh':
        assert 'git rev-parse --verify -q "$reference"' in source
    else:
        for reference in ('push', 'upstream'):
            assert f"git rev-parse --verify -q '@{{{reference}}}'" in source


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('hook', ['checkov', 'checkov-strict'])
@pytest.mark.parametrize('policy,extra', [('external-checks-dir: example\n', []),
                                         ('{}\n', ['--external-checks-dir', 'example'])])
def test_checkov_wrappers_reject_code_selection(consumer, package, scanner, shell, hook, policy, extra):
    runner = load_runner('wrapper_shell', 'pre-push.py')
    _, executable = runner.select_shell(shell)
    (consumer / 'main.tf').write_text('# source\n')
    config = consumer / '.scanning/configs/.checkov.yaml'
    config.parent.mkdir(parents=True)
    config.write_text(policy)
    manifest = consumer.parent / 'paths'
    manifest.write_bytes(b'main.tf\0')
    env, trace = scanner
    env.update(SCAN_PUSH_SNAPSHOT='1', SCAN_PUSH_FILES=str(manifest))
    command = ([executable, '-NoProfile', '-File'] if shell == 'ps1' else [executable])
    result = subprocess.run(command + [str(package / f'hooks/{hook}.{shell}')] + extra,
                            cwd=consumer, env=env, capture_output=True, text=True)
    assert result.returncode != 0, result.stdout + result.stderr
    assert not trace.exists()


@pytest.mark.parametrize('entry', ['link', 'unmerged'])
def test_index_export_errors_block_before_scanner(consumer, package, scanner, entry):
    blob = subprocess.check_output(['git', 'hash-object', '-w', '--stdin'], input=b'index input', cwd=consumer).decode().strip()
    if entry == 'link':
        git(consumer, 'update-index', '--add', '--cacheinfo', f'120000,{blob},App.cs')
    else:
        subprocess.run(['git', 'update-index', '--index-info'], cwd=consumer,
                       input=f'100644 {blob} 1\tApp.cs\n100644 {blob} 2\tApp.cs\n'.encode(), check=True)
    env, trace = scanner
    result = subprocess.run([sys.executable, str(package / 'hooks/pre-commit.py'), 'semgrep-csharp'],
                            cwd=consumer, env=env, capture_output=True, text=True)
    assert result.returncode == 1
    assert not trace.exists()
