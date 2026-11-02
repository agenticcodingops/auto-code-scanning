"""Integration regressions bind hook inputs to the index and push transaction."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
ZERO = '0' * 40


def git(repo, *args):
    return subprocess.check_output(['git', *args], cwd=repo).decode().strip()


@pytest.fixture
def consumer(tmp_path):
    repo = tmp_path / 'consumer'
    repo.mkdir()
    git(repo, 'init', '-q')
    git(repo, 'config', 'user.name', 'Fixture')
    git(repo, 'config', 'user.email', 'fixture@example.test')
    git(repo, 'config', 'core.autocrlf', 'false')
    (repo / 'App.sln').write_text('fixture')
    (repo / 'App.cs').write_text('pushed bytes\n')
    git(repo, 'add', '.')
    git(repo, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'fixture')
    return repo


@pytest.fixture
def package(tmp_path):
    package = tmp_path / 'package'
    for folder in ('hooks', 'scripts', 'schemas'):
        for source in (ROOT / folder).rglob('*'):
            if source.is_file() and '__pycache__' not in source.parts:
                target = package / source.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
                target.chmod(0o755)
    shutil.copyfile(ROOT / 'scan-config.yaml', package / 'scan-config.yaml')
    return package


def hook(package, shell, name):
    executable = shutil.which('bash' if shell == 'sh' else 'pwsh')
    if not executable:
        pytest.skip('shell unavailable')
    return [executable, *([] if shell == 'sh' else ['-NoProfile', '-File']),
            str(package / 'hooks' / f'{name}.{shell}')]


@pytest.fixture
def scanner(tmp_path):
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    trace = tmp_path / 'trace'
    mock = bin_dir / 'mock.py'
    mock.write_text('import json,os,pathlib,sys\n'
                    'folder=pathlib.Path.cwd()\n'
                    'if "-d" in sys.argv: folder=pathlib.Path(sys.argv[sys.argv.index("-d")+1])\n'
                    'for arg in sys.argv:\n'
                    ' if arg.startswith("--chdir="): folder=pathlib.Path(arg.split("=",1)[1])\n'
                    'if "--" in sys.argv: folder=pathlib.Path(sys.argv[-1])\n'
                    'with open(os.environ["TRACE"],"a") as f:\n'
                    ' f.write(json.dumps({p.name:p.read_text() for p in folder.iterdir() if p.suffix in (".cs",".tf")})+"\\n")\n'
                    'print(\'{"results":{"failed_checks":[]},"issues":[],"infrastructureAsCodeIssues":[]}\')\n')
    for name in ('dotnet', 'checkov', 'tflint', 'trivy', 'snyk'):
        target = bin_dir / name
        target.write_text(f'#!/usr/bin/env bash\nexec python "{mock.as_posix()}" "$@"\n', newline='\n')
        target.chmod(0o755)
        (bin_dir / f'{name}.cmd').write_text(f'@"{sys.executable}" "{mock}" %*\n')
    return dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ['PATH'], TRACE=str(trace)), trace


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('ref', ['refs/heads/new', 'refs/heads/alternate', 'refs/tags/release'])
def test_push_scans_non_head_object_despite_unrelated_index(consumer, package, scanner, shell, ref):
    oid = git(consumer, 'rev-parse', 'HEAD')
    (consumer / 'App.cs').write_text('different HEAD\n')
    git(consumer, 'add', '.')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'other head')
    (consumer / 'unrelated.txt').write_text('staged')
    git(consumer, 'add', '.')
    env, trace = scanner
    result = subprocess.run(hook(package, shell, 'dotnet-build'), cwd=consumer, env=env,
                            input=f'{ref} {oid} refs/heads/destination {ZERO}\n',
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert trace.exists(), result.stdout + result.stderr
    assert json.loads(trace.read_text().splitlines()[0]) == {'App.cs': 'pushed bytes\n'}
    assert (consumer / 'App.cs').read_text() == 'different HEAD\n'
    assert git(consumer, 'diff', '--cached', '--name-only') == 'unrelated.txt'


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
def test_push_scans_all_refs_and_clean_index(consumer, package, scanner, shell):
    first = git(consumer, 'rev-parse', 'HEAD')
    (consumer / 'App.cs').write_text('second tip\n')
    git(consumer, 'add', '.')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'second')
    second = git(consumer, 'rev-parse', 'HEAD')
    git(consumer, 'tag', '-am', 'release', 'release', first)
    tag = git(consumer, 'rev-parse', 'refs/tags/release')
    env, trace = scanner
    result = subprocess.run(hook(package, shell, 'dotnet-build'), cwd=consumer, env=env,
                            input=f'refs/tags/release {tag} refs/tags/release {ZERO}\n'
                                  f'refs/heads/two {second} refs/heads/two {first}\n'
                                  f'(delete) {ZERO} refs/heads/old {first}\n',
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert trace.exists(), result.stdout + result.stderr
    assert [json.loads(line)['App.cs'] for line in trace.read_text().splitlines()] == [
        'pushed bytes\n', 'second tip\n']


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('staged_valid', [False, True])
def test_config_validates_consumer_index_not_package_or_worktree(consumer, package, shell, staged_valid):
    valid = (ROOT / 'templates/scan-config/starter.yaml').read_text()
    invalid = 'languages: []\n'
    (consumer / 'scan-config.yaml').write_text(valid if staged_valid else invalid)
    git(consumer, 'add', 'scan-config.yaml')
    (consumer / 'scan-config.yaml').write_text(invalid if staged_valid else valid)
    result = subprocess.run(hook(package, shell, 'validate-scan-config'), cwd=consumer,
                            capture_output=True, text=True)
    assert result.returncode == (0 if staged_valid else 1), result.stdout + result.stderr


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
def test_push_missing_or_invalid_transaction_blocks(consumer, package, scanner, shell):
    env, trace = scanner
    for records in ('', 'invalid record\n', f'ref {"f"*40} ref {ZERO}\n'):
        result = subprocess.run(hook(package, shell, 'dotnet-build'), cwd=consumer, env=env,
                                input=records, text=True, capture_output=True)
        assert result.returncode == 1, result.stdout + result.stderr
    assert not trace.exists()


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('name', ['checkov', 'checkov-strict', 'tflint', 'trivy-iac-full', 'snyk-iac'])
def test_iac_hooks_read_object_bytes(consumer, package, scanner, shell, name):
    (consumer / 'main.tf').write_text('# pushed IaC\n')
    git(consumer, 'add', '.')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'iac')
    oid = git(consumer, 'rev-parse', 'HEAD')
    (consumer / 'main.tf').write_text('# live worktree\n')
    env, trace = scanner
    env['SNYK_TOKEN'] = 'fixture'
    result = subprocess.run(hook(package, shell, name), cwd=consumer, env=env,
                            input=f'refs/heads/target {oid} refs/heads/other {ZERO}\n',
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert trace.exists(), result.stdout + result.stderr
    assert any(json.loads(line).get('main.tf') == '# pushed IaC\n' for line in trace.read_text().splitlines())
    assert '# live worktree' in (consumer / 'main.tf').read_text()


def test_pre_commit_adapter_keeps_every_ref_and_other_hooks(consumer, package, scanner):
    import yaml
    # The installed hook must reference repo-owned files, as in vendored setups.
    shutil.copytree(package / 'hooks', consumer / 'hooks')
    (consumer / '.pre-commit-config.yaml').write_text(yaml.safe_dump({'repos': [
        {'repo': 'local', 'hooks': [{'id': 'dotnet-build', 'stages': ['pre-push']}]}]}))
    original = consumer / '.git/hooks/pre-push'
    original.write_text('#!/usr/bin/env bash\n# File generated by pre-commit\n'
                        'cat > original-records\nprintf "%s" "$SKIP" > original-skip\n', newline='\n')
    original.chmod(0o755)
    runner = consumer / 'hooks/pre-push.py'
    for _ in range(2):
        result = subprocess.run([sys.executable, str(runner), '--install-pre-commit'], cwd=consumer,
                                text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
    assert str(consumer) not in original.read_text()
    oid = git(consumer, 'rev-parse', 'HEAD')
    records = f'refs/heads/one {oid} refs/heads/one {ZERO}\nrefs/heads/two {oid} refs/heads/two {ZERO}\n'
    env, trace = scanner
    result = subprocess.run([sys.executable, str(runner), '--pre-commit-runner', 'origin', 'fixture'],
                            cwd=consumer, input=records, text=True, capture_output=True, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert trace.exists()
    assert (consumer / 'original-records').read_text() == records
    assert 'dotnet-build' in (consumer / 'original-skip').read_text()


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
def test_unstaged_off_switch_cannot_hide_push(consumer, package, scanner, shell):
    oid = git(consumer, 'rev-parse', 'HEAD')
    (consumer / 'scan-config.yaml').write_text('global: {local_hooks_enabled: false}\n')
    env, trace = scanner
    result = subprocess.run(hook(package, shell, 'dotnet-build'), cwd=consumer, env=env,
                            input=f'refs/heads/main {oid} refs/heads/main {ZERO}\n',
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert trace.exists()


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
def test_deletion_only_push_has_no_local_scan(consumer, package, scanner, shell):
    env, trace = scanner
    result = subprocess.run(hook(package, shell, 'dotnet-build'), cwd=consumer, env=env,
                            input=f'(delete) {ZERO} refs/heads/old {git(consumer,"rev-parse","HEAD")}\n',
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not trace.exists()


def test_materialization_ignores_archive_attributes_and_preserves_blob_bytes(consumer, package, tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location('push_hooks', package / 'hooks/pre-push.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (consumer / '.gitattributes').write_text('App.cs export-ignore\n*.cs -text\n')
    content = b'// exact object bytes\r\n'
    (consumer / 'App.cs').write_bytes(content)
    git(consumer, 'add', '.')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'attributes')
    oid = git(consumer, 'rev-parse', 'HEAD')
    destination = tmp_path / 'snapshot'
    destination.mkdir()
    previous = Path.cwd()
    try:
        os.chdir(consumer)
        names = module.materialize(oid, destination)
    finally:
        os.chdir(previous)
    assert 'App.cs' in names
    assert (destination / 'App.cs').read_bytes() == content


def test_native_runner_accepts_empty_git_transaction(consumer, package):
    result = subprocess.run([sys.executable, str(package / 'hooks/pre-push.py'), '--stdin-from-git'],
                            cwd=consumer, input='', text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_adapter_install_and_reinstall_with_real_runner(consumer, package):
    if not shutil.which('pre-commit'):
        pytest.skip('pre-commit unavailable')
    shutil.copytree(package / 'hooks', consumer / 'hooks')
    (consumer / '.pre-commit-config.yaml').write_text('repos: []\n')
    command = [sys.executable, str(consumer / 'hooks/pre-push.py'), '--install-pre-commit']
    for _ in range(2):
        result = subprocess.run(command, cwd=consumer, text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
        result = subprocess.run(['pre-commit', 'install', '--hook-type', 'pre-push'], cwd=consumer,
                                text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run(command, cwd=consumer, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    legacy = consumer / '.git/hooks/pre-push.legacy'
    assert not legacy.exists()
    assert (consumer / '.git/hooks/pre-push.pre-commit').is_file()


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
def test_missing_solution_blocks_object_scan(consumer, package, scanner, shell):
    git(consumer, 'rm', 'App.sln')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'no solution')
    oid = git(consumer, 'rev-parse', 'HEAD')
    env, trace = scanner
    result = subprocess.run(hook(package, shell, 'dotnet-build'), cwd=consumer, env=env,
                            input=f'refs/heads/main {oid} refs/heads/main {ZERO}\n',
                            text=True, capture_output=True)
    assert result.returncode == 1, result.stdout + result.stderr
    assert not trace.exists()


def test_real_multi_ref_push_reaches_native_adapter(consumer, package, scanner, tmp_path):
    shutil.copytree(package / 'hooks', consumer / 'hooks')
    (consumer / '.pre-commit-config.yaml').write_text('repos:\n- repo: local\n  hooks:\n  - id: dotnet-build\n')
    original = consumer / '.git/hooks/pre-push'
    original.write_text('#!/usr/bin/env bash\n# File generated by pre-commit\ncat > original-records\n', newline='\n')
    original.chmod(0o755)
    result = subprocess.run([sys.executable, str(consumer / 'hooks/pre-push.py'), '--install-pre-commit'],
                            cwd=consumer, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    first = git(consumer, 'rev-parse', 'HEAD')
    (consumer / 'App.cs').write_text('another pushed object\n')
    git(consumer, 'add', 'App.cs')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'another object')
    second = git(consumer, 'rev-parse', 'HEAD')
    remote = tmp_path / 'remote.git'
    git(consumer, 'init', '--bare', '-q', str(remote))
    env, trace = scanner
    result = subprocess.run(['git', 'push', str(remote), f'{first}:refs/heads/one', f'{second}:refs/heads/two'],
                            cwd=consumer, env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    scanned = [json.loads(line)['App.cs'] for line in trace.read_text().splitlines()]
    assert scanned == ['pushed bytes\n', 'another pushed object\n']
    assert len((consumer / 'original-records').read_text().splitlines()) == 2
