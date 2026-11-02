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


def clean_env():
    return {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}


@pytest.fixture(autouse=True)
def isolate_inherited_git_environment(monkeypatch):
    # Hook-invoked pytest must never stage or commit into the invoking repository.
    for key in tuple(os.environ):
        if key.startswith('GIT_'):
            monkeypatch.delenv(key)


def git(repo, *args):
    return subprocess.check_output(['git', *args], cwd=repo, env=clean_env()).decode().strip()


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
                    'if "POLICY_TRACE" in os.environ:\n'
                    ' policies=[sys.argv[i+1] for i,a in enumerate(sys.argv[:-1]) if a in ("--config","--config-file")]\n'
                    ' pathlib.Path(os.environ["POLICY_TRACE"]).write_text(pathlib.Path(policies[0]).read_text() if policies else "missing")\n'
                    'print(\'{"results":{"failed_checks":[]},"issues":[],"infrastructureAsCodeIssues":[]}\')\n'
                    'sys.exit(int(os.environ.get("SCANNER_EXIT", "0")))\n')
    for name in ('dotnet', 'checkov', 'tflint', 'trivy', 'snyk'):
        target = bin_dir / name
        target.write_text(f'#!/usr/bin/env bash\nexec python "{mock.as_posix()}" "$@"\n', newline='\n')
        target.chmod(0o755)
        (bin_dir / f'{name}.cmd').write_text(f'@"{sys.executable}" "{mock}" %*\n')
    trusted = tmp_path / 'trusted.tflint.hcl'
    trusted.write_text('# external trusted rules\n')
    plugins = tmp_path / 'trusted-plugins'
    plugins.mkdir()
    return dict(clean_env(), PATH=str(bin_dir) + os.pathsep + os.environ['PATH'], TRACE=str(trace),
                SCAN_TFLINT_CONFIG=str(trusted), SCAN_TFLINT_PLUGIN_DIR=str(plugins)), trace


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
@pytest.mark.parametrize('staged_valid', [False, True])
def test_staged_config_ignores_blob_replacement(consumer, package, shell, staged_valid):
    valid = (ROOT / 'templates/scan-config/starter.yaml').read_text()
    invalid = 'languages: []\n'
    config = consumer / 'scan-config.yaml'
    config.write_text(valid if staged_valid else invalid)
    git(consumer, 'add', 'scan-config.yaml')
    original = git(consumer, 'rev-parse', ':scan-config.yaml')
    config.write_text(invalid if staged_valid else valid)
    replacement = git(consumer, 'hash-object', '-w', 'scan-config.yaml')
    git(consumer, 'replace', original, replacement)
    assert subprocess.check_output(['git', 'show', ':scan-config.yaml'], cwd=consumer,
                                   env=clean_env()) == config.read_bytes()
    result = subprocess.run(hook(package, shell, 'validate-scan-config'), cwd=consumer,
                            capture_output=True, text=True)
    assert result.returncode == (0 if staged_valid else 1), result.stdout + result.stderr


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('kind', ['commit', 'tree'])
def test_staged_config_change_detection_ignores_replacements(consumer, package, shell, kind):
    config = consumer / 'scan-config.yaml'
    config.write_text((ROOT / 'templates/scan-config/starter.yaml').read_text())
    git(consumer, 'add', 'scan-config.yaml')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'valid config')
    original = git(consumer, 'rev-parse', 'HEAD' if kind == 'commit' else 'HEAD^{tree}')
    config.write_text('languages: []\n')
    git(consumer, 'add', 'scan-config.yaml')
    replacement = git(consumer, 'write-tree')
    if kind == 'commit':
        replacement = git(consumer, 'commit-tree', replacement, '-m', 'replacement')
    git(consumer, 'replace', original, replacement)
    assert git(consumer, 'diff', '--cached', '--name-only') == ''
    result = subprocess.run(hook(package, shell, 'validate-scan-config'), cwd=consumer,
                            capture_output=True, text=True)
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'INVALID' in result.stdout


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('exit_code', [0, 1])
def test_push_exports_current_report_even_on_failure(consumer, package, scanner, shell, exit_code):
    report = consumer / '.scanning/last-scan.json'
    report.parent.mkdir()
    report.write_text('{"stale":true}')
    # A committed old report must not be mistaken for scanner output either.
    git(consumer, 'add', '.scanning/last-scan.json')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'old report')
    oid = git(consumer, 'rev-parse', 'HEAD')
    env, _ = scanner
    env['SCANNER_EXIT'] = str(exit_code)
    result = subprocess.run(hook(package, shell, 'dotnet-build'), cwd=consumer, env=env,
                            input=f'refs/heads/main {oid} refs/heads/main {ZERO}\n',
                            text=True, capture_output=True)
    assert result.returncode == exit_code, result.stdout + result.stderr
    current = json.loads(report.read_text(encoding='utf-8-sig'))
    assert current['tools_executed'] == ['dotnet-build']
    assert current['summary']['total_findings'] == exit_code
    assert (consumer / 'App.cs').read_text() == 'pushed bytes\n'


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
def test_push_without_report_removes_earlier_and_tracked_reports(consumer, package, scanner, shell):
    git(consumer, 'rm', 'App.sln')
    report = consumer / '.scanning/last-scan.json'
    report.parent.mkdir()
    report.write_text('{"stale":true}')
    git(consumer, 'add', '.')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'missing solution and old report')
    oid = git(consumer, 'rev-parse', 'HEAD')
    env, _ = scanner
    result = subprocess.run(hook(package, shell, 'dotnet-build'), cwd=consumer, env=env,
                            input=f'refs/heads/main {oid} refs/heads/main {ZERO}\n',
                            text=True, capture_output=True)
    assert result.returncode == 1, result.stdout + result.stderr
    assert not report.exists()


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
    policies = consumer / '.scanning/configs'
    policies.mkdir(parents=True)
    (policies / '.checkov.yaml').write_text('quiet: true\n')
    git(consumer, 'add', '.')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'iac')
    oid = git(consumer, 'rev-parse', 'HEAD')
    (consumer / 'main.tf').write_text('# live worktree\n')
    env, trace = scanner
    env['SNYK_TOKEN'] = 'fixture'
    if name == 'tflint':
        env['POLICY_TRACE'] = str(consumer.parent / 'linter-policy-trace')
    result = subprocess.run(hook(package, shell, name), cwd=consumer, env=env,
                            input=f'refs/heads/target {oid} refs/heads/other {ZERO}\n',
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert trace.exists(), result.stdout + result.stderr
    assert any(json.loads(line).get('main.tf') == '# pushed IaC\n' for line in trace.read_text().splitlines())
    assert '# live worktree' in (consumer / 'main.tf').read_text()
    report = json.loads((consumer / '.scanning/last-scan.json').read_text(encoding='utf-8-sig'))
    assert report['summary']['total_findings'] == 0
    if name == 'tflint':
        assert Path(env['POLICY_TRACE']).read_text() == '# external trusted rules\n'


@pytest.mark.parametrize('skip', ['', 'other-hook,dotnet-build,checkov'])
def test_pre_commit_adapter_keeps_every_ref_and_other_hooks(consumer, package, scanner, skip):
    import yaml
    # The installed hook must reference repo-owned files, as in vendored setups.
    shutil.copytree(package / 'hooks', consumer / 'hooks')
    (consumer / '.pre-commit-config.yaml').write_text(yaml.safe_dump({'repos': [
        {'repo': 'https://github.com/agenticcodingops/auto-code-scanning', 'hooks': [{'id': 'dotnet-build', 'stages': ['pre-push']}]}]}))
    original = consumer / '.git/hooks/pre-push'
    original.write_text('#!/usr/bin/env bash\n# File generated by pre-commit\nARGS=()\n# end templated\n'
                        'cat > original-records\nprintf "%s" "${SKIP:-}" > original-skip\ncp "$SCAN_PUSH_FILTERED_CONFIG" original-config\n', newline='\n')
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
    env['SKIP'] = skip
    result = subprocess.run([sys.executable, str(runner), '--pre-commit-runner', 'origin', 'fixture'],
                            cwd=consumer, input=records, text=True, capture_output=True, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert trace.exists() == ('dotnet-build' not in skip.split(','))
    assert (consumer / 'original-records').read_text() == records
    assert (consumer / 'original-skip').read_text() == skip
    assert yaml.safe_load((consumer / 'original-config').read_text())['repos'] == []


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
    (consumer / '.pre-commit-config.yaml').write_text('repos:\n- repo: https://github.com/agenticcodingops/auto-code-scanning\n  hooks:\n  - id: dotnet-build\n')
    original = consumer / '.git/hooks/pre-push'
    original.write_text('#!/usr/bin/env bash\n# File generated by pre-commit\nARGS=()\n# end templated\ncat > original-records\n', newline='\n')
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


@pytest.mark.parametrize('live_disabled', [False, True])
@pytest.mark.parametrize('finding_tool', [None, 'checkov', 'tflint', 'dotnet-build'])
def test_lefthook_dispatcher_scans_real_push_objects(
        consumer, package, scanner, tmp_path, live_disabled, finding_tool):
    import yaml

    # Keep this literal command in sync with the shipped consumer entry point.
    command = 'bash hooks/dispatcher.sh pre-push --hooks checkov,tflint,dotnet-build'
    template = yaml.safe_load((ROOT / 'templates/lefthook/lefthook.yml').read_text())
    push_command = template['pre-push']['commands']['scan-push-objects']
    assert push_command['run'] == command
    assert push_command['use_stdin'] is True

    (consumer / 'scan-config.yaml').write_text('local_hooks_enabled: true\n')
    (consumer / 'main.tf').write_text(f'# finding: {finding_tool}\n')
    (consumer / 'App.cs').write_text(f'// finding: {finding_tool}\n')
    policies = consumer / '.scanning/configs'
    policies.mkdir(parents=True)
    (policies / '.checkov.yaml').write_text('quiet: true\n')
    git(consumer, 'add', '.')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'push target')
    pushed = git(consumer, 'rev-parse', 'HEAD')

    # Push a non-HEAD ref while the live tree and index contain clean bytes.
    (consumer / 'main.tf').write_text('# clean live tree\n')
    (consumer / 'App.cs').write_text('// clean live tree\n')
    git(consumer, 'add', '.')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'clean checkout')
    if live_disabled:
        (consumer / 'scan-config.yaml').write_text('local_hooks_enabled: false\n')

    shutil.copytree(package / 'hooks', consumer / 'hooks')
    entry = consumer / '.git/hooks/pre-push'
    entry.write_text(f'#!/usr/bin/env bash\nexec {command}\n', newline='\n')
    entry.chmod(0o755)
    remote = tmp_path / 'remote.git'
    git(consumer, 'init', '--bare', '-q', str(remote))

    # Only tool executables are doubles. Findings depend on the source bytes
    # actually received, so scanning HEAD/the worktree would incorrectly pass.
    env, trace = scanner
    (tmp_path / 'bin/mock.py').write_text('''import json, os, pathlib, sys
tool = 'checkov' if '-d' in sys.argv else 'dotnet-build' if 'build' in sys.argv else 'tflint'
if '--init' in sys.argv:
    sys.exit(0)
sources = {p.name: p.read_text() for p in pathlib.Path.cwd().iterdir()
           if p.suffix in ('.cs', '.tf')}
with open(os.environ['TRACE'], 'a') as output:
    output.write(json.dumps({'tool': tool, 'sources': sources}) + '\\n')
finding = any('finding: ' + tool in content for content in sources.values())
print(json.dumps({'results': {'failed_checks': [{'severity': 'HIGH'}] if finding else []},
                  'issues': [{'rule': {'severity': 'error'}}] if finding else []}))
sys.exit((2 if tool == 'tflint' else 1) if finding else 0)
''')
    result = subprocess.run(['git', 'push', str(remote), f'{pushed}:refs/heads/target'],
                            cwd=consumer, env=env, text=True, capture_output=True, timeout=120)
    output = result.stdout + result.stderr
    assert result.returncode == (1 if finding_tool else 0), output
    assert trace.exists(), output
    scans = [json.loads(line) for line in trace.read_text().splitlines()]
    assert [scan['tool'] for scan in scans] == ['checkov', 'tflint', 'dotnet-build'], output
    assert all(scan['sources'] == {'App.cs': f'// finding: {finding_tool}\n',
                                   'main.tf': f'# finding: {finding_tool}\n'} for scan in scans)
    assert 'local scanning disabled' not in output
    refs = git(consumer, '--git-dir', str(remote), 'for-each-ref', '--format=%(objectname)')
    assert refs == ('' if finding_tool else pushed), output
    assert (consumer / 'App.cs').read_text() == '// clean live tree\n'
    assert git(consumer, 'diff', '--cached', '--name-only') == ''
    assert (consumer / 'scan-config.yaml').read_text() == (
        'local_hooks_enabled: false\n' if live_disabled else 'local_hooks_enabled: true\n')


def load_push_runner(package):
    import importlib.util
    spec = importlib.util.spec_from_file_location('push_runner', package / 'hooks/pre-push.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BAD_SCAN_CONFIGS = [
    ('true\n', 'scan-config.yaml.<root>'),
    ('[]\n', 'scan-config.yaml.<root>'),
    ('null\n', 'scan-config.yaml.<root>'),
    ('global: true\n', 'global'),
    ('global: []\n', 'global'),
    ('global: null\n', 'global'),
    ('global: {local_hooks_enabled: []}\n', 'global.local_hooks_enabled'),
    ('local_hooks_enabled: "false"\n', 'local_hooks_enabled'),
    ('languages: []\n', 'languages'),
    ('languages: false\n', 'languages'),
    ('languages: null\n', 'languages'),
    ('languages: {csharp: []}\n', 'languages.csharp'),
    ('languages: {csharp: {build: true}}\n', 'languages.csharp.build'),
    ('languages: {csharp: {build: null}}\n', 'languages.csharp.build'),
    ('languages: {csharp: {build: {solution: []}}}\n', 'languages.csharp.build.solution'),
    ('languages: {csharp: {build: {working_dir: 42}}}\n', 'languages.csharp.build.working_dir'),
    ('languages: {typescript: {build: {working_dir: {}}}}\n', 'languages.typescript.build.working_dir'),
    ('global: {local_hooks_enabled: false}\nlanguages: []\n', 'languages'),
]


@pytest.mark.parametrize('content,key', BAD_SCAN_CONFIGS)
@pytest.mark.parametrize('shell', ['sh', 'ps1'])
def test_wrong_shaped_pushed_config_blocks_cleanly(consumer, package, scanner, shell, content, key):
    (consumer / 'scan-config.yaml').write_text(content)
    git(consumer, 'add', '.')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'malformed config')
    oid = git(consumer, 'rev-parse', 'HEAD')
    # Live configuration must not replace the invalid pushed configuration.
    (consumer / 'scan-config.yaml').write_text('{}\n')
    env, trace = scanner
    env['SCAN_ALLOW_TOOL_ERRORS'] = '1'
    result = subprocess.run(hook(package, shell, 'dotnet-build'), cwd=consumer, env=env,
                            input=f'refs/heads/main {oid} refs/heads/main {ZERO}\n',
                            text=True, capture_output=True)
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stderr.splitlines() == [f'[pre-push] ERROR: {key} must be ' +
        ('a string' if key.endswith(('solution', 'working_dir')) else
         'a boolean' if key.endswith('local_hooks_enabled') else 'a mapping') + '; scan incomplete']
    assert not trace.exists()


@pytest.mark.parametrize('content,key', BAD_SCAN_CONFIGS)
@pytest.mark.parametrize('shell', ['sh', 'ps1'])
def test_shared_config_readers_reject_wrong_shapes(tmp_path, shell, content, key):
    (tmp_path / 'scan-config.yaml').write_text(content)
    common = (ROOT / 'hooks/lib' / f'common.{shell}').as_posix()
    executable = hook(ROOT, shell, 'dotnet-build')[0]
    script = (f'set -e; source "{common}"; value="$(read_scan_config languages.csharp.build.solution NONE)"; echo continued'
              if shell == 'sh' else
              f'. "{common}"; $value = Read-ScanConfigValue -Key languages.csharp.build.solution -Default NONE; Write-Output continued')
    command = [executable, '-c', script] if shell == 'sh' else [executable, '-NoProfile', '-Command', script]
    result = subprocess.run(command, cwd=tmp_path, env=clean_env(), capture_output=True, text=True)
    assert result.returncode == 1, result.stdout + result.stderr
    assert key in result.stderr
    assert len(result.stderr.splitlines()) == 1
    assert 'continued' not in result.stdout
    assert 'Traceback' not in result.stderr


@pytest.mark.parametrize('content,key', [
    ('[]', '<root>'), ('{}', 'repos'), ('repos: {}', 'repos'),
    ('repos: [null]', 'repos[0]'), ('repos: [{repo: []}]', 'repos[0].repo'),
    ('repos: [{repo: local, hooks: {}}]', 'repos[0].hooks'),
    ('repos: [{repo: local, hooks: [false]}]', 'repos[0].hooks[0]'),
    ('repos: [{repo: local, hooks: [{id: []}]}]', '.id'),
    ('repos: [{repo: local, hooks: [{id: checkov, entry: []}]}]', '.entry'),
    ('repos: [{repo: local, hooks: [{id: checkov, args: null}]}]', '.args'),
    ('repos: [{repo: local, hooks: [{id: checkov, args: [false]}]}]', '.args[]'),
    ('repos: [{repo: local, hooks: [{id: checkov, stages: pre-push}]}]', '.stages'),
    ('repos: [{repo: local, hooks: [{id: checkov, stages: [{}]}]}]', '.stages[]'),
])
def test_adapter_rejects_wrong_shaped_runner_configuration(consumer, package, content, key):
    (consumer / '.pre-commit-config.yaml').write_text(content)
    result = subprocess.run([sys.executable, str(package / 'hooks/pre-push.py'), '--pre-commit-runner'],
                            cwd=consumer, env=clean_env(), input='', capture_output=True, text=True)
    assert result.returncode == 1, result.stdout + result.stderr
    assert key in result.stderr
    assert len(result.stderr.splitlines()) == 1
    assert 'Traceback' not in result.stderr


@pytest.mark.parametrize('filename,content', [('scan-config.yaml', 'global: [\n'),
                                            ('.pre-commit-config.yaml', 'repos: [\n')])
def test_push_configuration_parse_errors_are_one_line(consumer, package, filename, content):
    (consumer / filename).write_text(content)
    git(consumer, 'add', '.')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'invalid YAML')
    oid = git(consumer, 'rev-parse', 'HEAD')
    options = ['--pre-commit-runner'] if filename.startswith('.') else ['--hooks', 'dotnet-build']
    result = subprocess.run([sys.executable, str(package / 'hooks/pre-push.py'), *options],
                            cwd=consumer, env=clean_env(), capture_output=True, text=True,
                            input=f'refs/heads/main {oid} refs/heads/main {ZERO}\n')
    assert result.returncode == 1, result.stdout + result.stderr
    assert filename + ': invalid YAML' in result.stderr
    assert len(result.stderr.splitlines()) == 1


@pytest.mark.parametrize('schema', [[], {'type': 'unknown'}])
def test_staged_validator_rejects_malformed_schema_without_traceback(consumer, package, schema):
    (consumer / 'scan-config.yaml').write_text('{}\n')
    git(consumer, 'add', '.')
    (package / 'schemas/scan-config.schema.json').write_text(json.dumps(schema))
    result = subprocess.run([sys.executable, str(package / 'scripts/validate-scan-config.py'), '--staged'],
                            cwd=consumer, env=clean_env(), capture_output=True, text=True)
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'invalid validation schema' in result.stdout
    assert 'Traceback' not in result.stdout + result.stderr


@pytest.mark.parametrize('filename', ['scan_config.py', 'push-hook-ids.txt'])
def test_missing_runner_support_file_blocks_without_traceback(consumer, package, filename):
    (package / 'hooks/lib' / filename).unlink()
    result = subprocess.run([sys.executable, str(package / 'hooks/pre-push.py'), '--stdin-from-git'],
                            cwd=consumer, env=clean_env(), input='', text=True, capture_output=True)
    assert result.returncode == 1, result.stdout + result.stderr
    assert len(result.stderr.splitlines()) == 1
    assert 'scan incomplete' in result.stderr


@pytest.mark.parametrize('content,expected', [('{}', ''),
    ('languages: {csharp: {build: {solution: App.sln}}}', 'App.sln'),
    ('languages: []', None)])
def test_windows_powershell_config_reader_handles_empty_native_arguments(tmp_path, content, expected):
    executable = shutil.which('powershell') if os.name == 'nt' else None
    if not executable:
        pytest.skip('Windows PowerShell unavailable')
    (tmp_path / 'scan-config.yaml').write_text(content)
    common = (ROOT / 'hooks/lib/common.ps1').as_posix()
    result = subprocess.run([executable, '-NoProfile', '-Command',
        f'. "{common}"; $value = Read-ScanConfigValue -Key languages.csharp.build.solution; Write-Output "value=$value"'],
        cwd=tmp_path, env=clean_env(), capture_output=True, text=True)
    assert result.returncode == (1 if expected is None else 0), result.stdout + result.stderr
    if expected is None:
        assert len(result.stderr.splitlines()) == 1
        assert 'languages must be a mapping' in result.stderr
    else:
        assert result.stdout.strip() == 'value=' + expected


@pytest.mark.parametrize('last_writes_report', [False, True])
def test_push_exports_each_report_and_clears_between_scanners_and_objects(
        consumer, package, monkeypatch, last_writes_report):
    (consumer / 'main.tf').write_text('# first tip\n')
    report = consumer / '.scanning/last-scan.json'
    report.parent.mkdir()
    report.write_text('{"stale":true}')
    git(consumer, 'add', '.')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'first tip')
    first = git(consumer, 'rev-parse', 'HEAD')
    (consumer / 'main.tf').write_text('# second tip\n')
    git(consumer, 'add', '.')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'second tip')
    second = git(consumer, 'rev-parse', 'HEAD')
    runner = load_push_runner(package)
    monkeypatch.chdir(consumer)
    monkeypatch.setattr(runner, 'select_shell', lambda shell: ('sh', 'fixture'))
    calls, exports, snapshots = [], [], []
    publish = runner.export_report
    real_run = subprocess.run

    def run(command, *args, **kwargs):
        if command[0] != 'fixture':
            return real_run(command, *args, **kwargs)
        cwd, env = kwargs['cwd'], kwargs['env']
        snapshots.append(cwd)
        assert not report.exists()
        snapshot_report = cwd / '.scanning/last-scan.json'
        assert not snapshot_report.exists()
        assert env['SCAN_PUSH_SNAPSHOT'] == '1'
        calls.append(Path(command[1]).stem)
        if len(calls) < 4 or last_writes_report:
            snapshot_report.write_text(json.dumps({'scan': len(calls)}))
        return subprocess.CompletedProcess(command, 1 if len(calls) == 4 else 0)

    def export(source, destination):
        publish(source, destination)
        exports.append(json.loads(destination.read_text()) if destination.exists() else None)

    monkeypatch.setattr(runner.subprocess, 'run', run)
    monkeypatch.setattr(runner, 'export_report', export)
    records = f'refs/heads/one {first} refs/heads/one {ZERO}\nrefs/heads/two {second} refs/heads/two {ZERO}\n'
    assert runner.scan(records, [('dotnet-build', []), ('trivy-iac-full', [])], 'sh') == 1
    assert calls == ['dotnet-build', 'trivy-iac-full'] * 2
    assert exports == [{'scan': 1}, {'scan': 2}, {'scan': 3}, {'scan': 4} if last_writes_report else None]
    assert report.exists() == last_writes_report
    assert all(not snapshot.exists() for snapshot in snapshots)


@pytest.mark.parametrize('transaction', ['empty', 'deletion', 'invalid', 'skipped', 'disabled'])
def test_push_without_scan_clears_previous_report(consumer, package, monkeypatch, transaction):
    if transaction == 'disabled':
        (consumer / 'scan-config.yaml').write_text('global: {local_hooks_enabled: false}\n')
        git(consumer, 'add', 'scan-config.yaml')
        git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'disabled hooks')
    oid = git(consumer, 'rev-parse', 'HEAD')
    records = f'refs/heads/main {oid} refs/heads/main {ZERO}\n'
    if transaction == 'empty':
        records = ''
    elif transaction == 'deletion':
        records = f'(delete) {ZERO} refs/heads/main {oid}\n'
    elif transaction == 'invalid':
        records = 'invalid record\n'
    report = consumer / '.scanning/last-scan.json'
    report.parent.mkdir()
    report.write_text('{"stale":true}')
    monkeypatch.chdir(consumer)
    runner = load_push_runner(package)
    if transaction == 'invalid':
        with pytest.raises(ValueError, match='Malformed'):
            runner.scan(records, [('dotnet-build', [])], 'auto', from_git=True)
    else:
        hooks = [] if transaction == 'skipped' else [('dotnet-build', [])]
        assert runner.scan(records, hooks, 'auto', from_git=True) == 0
    assert not report.exists()


@pytest.mark.parametrize('operation', ['scan', 'export'])
def test_push_report_refuses_linked_consumer_output(consumer, package, tmp_path, monkeypatch, operation):
    outside = tmp_path / 'outside'
    outside.mkdir()
    sentinel = outside / 'last-scan.json'
    sentinel.write_text('original')
    link = consumer / '.scanning'
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        if os.name != 'nt':
            pytest.skip('directory link unavailable')
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)], capture_output=True)
        if result.returncode:
            pytest.skip('junction unavailable')
    source = tmp_path / 'current-report.json'
    source.write_text('current')
    runner = load_push_runner(package)
    monkeypatch.chdir(consumer)
    with pytest.raises(OSError, match='symlink or reparse point'):
        if operation == 'scan':
            runner.scan('', [], 'auto', from_git=True)
        else:
            runner.export_report(source, link / 'last-scan.json')
    assert sentinel.read_text() == 'original'
    assert list(outside.iterdir()) == [sentinel]


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('kind', ['commit', 'tree', 'blob', 'tag'])
def test_push_ignores_replacement_objects(consumer, package, scanner, shell, kind):
    original = git(consumer, 'rev-parse', 'HEAD')
    git(consumer, 'tag', '-am', 'original', 'original', original)
    (consumer / 'App.cs').write_text('replacement bytes\n')
    git(consumer, 'add', 'App.cs')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'replacement')
    replacement = git(consumer, 'rev-parse', 'HEAD')
    git(consumer, 'tag', '-am', 'replacement', 'replacement', replacement)
    suffix = {'commit': '', 'tree': '^{tree}', 'blob': ':App.cs'}
    if kind == 'tag':
        oid = git(consumer, 'rev-parse', 'refs/tags/original')
        replaced = oid
        substitute = git(consumer, 'rev-parse', 'refs/tags/replacement')
    else:
        oid = original
        replaced = git(consumer, 'rev-parse', original + suffix[kind])
        substitute = git(consumer, 'rev-parse', replacement + suffix[kind])
    git(consumer, 'replace', replaced, substitute)
    # Prove the fixture actually redirects ordinary Git object reads.
    assert git(consumer, 'show', oid + ':App.cs') == 'replacement bytes'
    env, trace = scanner
    result = subprocess.run(hook(package, shell, 'dotnet-build'), cwd=consumer, env=env,
                            input=f'refs/heads/target {oid} refs/heads/target {ZERO}\n',
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert trace.exists(), result.stdout + result.stderr
    assert [json.loads(line)['App.cs'] for line in trace.read_text().splitlines()] == ['pushed bytes\n']


@pytest.mark.parametrize('location', ['https://github.com/agenticcodingops/auto-code-scanning', 'local'])
@pytest.mark.parametrize('skip,expected', [('', ['checkov', 'tflint']),
                                         ('checkov', ['tflint']),
                                         ('other,checkov,tflint', []),
                                         ('checkov-extra', ['checkov', 'tflint'])])
def test_adapted_hook_selection_honors_skip(consumer, package, monkeypatch, location, skip, expected):
    import yaml
    adapted = [{'id': name, 'entry': f'bash hooks/dispatcher.sh {name}'} for name in ('checkov', 'tflint')]
    other = {'id': 'other', 'entry': 'custom-scanner'}
    commit_only = {'id': 'dotnet-build', 'entry': 'bash hooks/dispatcher.sh dotnet-build', 'stages': ['pre-commit']}
    config = {'repos': [{'repo': location, 'hooks': [*adapted, other, commit_only]}]}
    (consumer / '.pre-commit-config.yaml').write_text(yaml.safe_dump(config))
    monkeypatch.chdir(consumer)
    monkeypatch.setenv('SKIP', skip)
    selected, forwarded = load_push_runner(package).push_configuration()
    assert selected == [(name, []) for name in expected]
    # Skipped adapted hooks cannot run again in the saved runner.
    assert forwarded['repos'] == [{'repo': location, 'hooks': [other, commit_only]}]


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
def test_untracked_policy_blocks_instead_of_silently_changing_rules(consumer, package, scanner, shell):
    (consumer / '.gitignore').write_text('.scanning/\n')
    (consumer / 'main.tf').write_text('# fixture\n')
    git(consumer, 'add', '.')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'ignored policies')
    policies = consumer / '.scanning/configs'
    policies.mkdir(parents=True)
    (policies / '.checkov.yaml').write_text('# required cloud rules\n')
    oid = git(consumer, 'rev-parse', 'HEAD')
    env, trace = scanner
    result = subprocess.run(hook(package, shell, 'checkov'), cwd=consumer, env=env,
                            input=f'refs/heads/main {oid} refs/heads/main {ZERO}\n',
                            text=True, capture_output=True)
    assert result.returncode == 1, result.stdout + result.stderr
    assert not trace.exists()


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
def test_tracked_custom_policy_directory_is_honored(consumer, package, scanner, shell, tmp_path):
    policies = consumer / 'policies'
    policies.mkdir()
    content = '# reviewed cloud rules\n'
    (policies / '.checkov.yaml').write_text(content)
    (consumer / 'main.tf').write_text('# fixture\n')
    git(consumer, 'add', '.')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'tracked policies')
    oid = git(consumer, 'rev-parse', 'HEAD')
    env, _ = scanner
    policy_trace = tmp_path / 'policy-trace'
    env.update(SCAN_CONFIG_DIR='policies', POLICY_TRACE=str(policy_trace))
    result = subprocess.run(hook(package, shell, 'checkov'), cwd=consumer, env=env,
                            input=f'refs/heads/main {oid} refs/heads/main {ZERO}\n',
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert policy_trace.read_text() == content


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('setting', ['SCAN_TFLINT_CONFIG', 'SCAN_TFLINT_PLUGIN_DIR'])
def test_push_linter_rejects_consumer_owned_executable_inputs(consumer, package, scanner, shell, setting):
    (consumer / 'main.tf').write_text('# pushed source\n')
    (consumer / '.tflint.hcl').write_text('# untrusted repository config\n')
    git(consumer, 'add', '.')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'linter inputs')
    oid = git(consumer, 'rev-parse', 'HEAD')
    env, trace = scanner
    env[setting] = str(consumer / ('.tflint.hcl' if setting == 'SCAN_TFLINT_CONFIG' else 'plugins'))
    result = subprocess.run(hook(package, shell, 'tflint'), cwd=consumer, env=env,
                            input=f'refs/heads/main {oid} refs/heads/main {ZERO}\n',
                            text=True, capture_output=True)
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'outside the consumer repository' in result.stderr
    assert not trace.exists()


@pytest.mark.parametrize('stages,expected', [(None, True), (['pre-commit'], False), (['pre-push'], True), (['push'], True)])
def test_manifest_stages_override_global_defaults(consumer, package, monkeypatch, stages, expected):
    import yaml
    hook_config = {'id': 'checkov'}
    if stages is not None:
        hook_config['stages'] = stages
    config = {'default_stages': ['pre-commit'], 'repos': [{'repo': 'https://github.com/agenticcodingops/auto-code-scanning', 'hooks': [hook_config]}]}
    (consumer / '.pre-commit-config.yaml').write_text(yaml.safe_dump(config))
    monkeypatch.chdir(consumer)
    assert bool(load_push_runner(package).configured_hooks()) == expected


@pytest.mark.parametrize('available,expected', [('pwsh', 'ps1'), ('powershell', 'ps1'), ('bash', 'sh')])
def test_windows_auto_shell_uses_available_fallback(package, monkeypatch, available, expected):
    module = load_push_runner(package)
    monkeypatch.setattr(module.shutil, 'which', lambda name: name if name == available else None)
    monkeypatch.setattr(module, 'bash', lambda: 'bash')
    implementation, executable = module.select_shell('auto', windows=True)
    assert implementation == expected
    assert executable == available


def test_push_stage_defaults_match_the_platform_manifest(package):
    import yaml
    module = load_push_runner(package)
    manifest = {h['id']: h for h in yaml.safe_load((ROOT / '.pre-commit-hooks.yaml').read_text())}
    push_ids = {name for name, hook in manifest.items() if 'pre-push' in hook['stages']}
    assert len(module.HOOKS) == len(set(module.HOOKS))
    assert set(module.HOOKS) == push_ids
    assert all(module.MANIFEST_STAGES[name] == manifest[name]['stages'] for name in module.HOOKS)


@pytest.mark.parametrize('ostype', ['linux-gnu', 'msys'])
@pytest.mark.parametrize('hook_id', (ROOT / 'hooks/lib/push-hook-ids.txt').read_text().split()
                         + ['validate-scan-config', 'trivy-iac-critical'])
def test_dispatcher_live_kill_switch_exempts_every_push_scanner(package, consumer, ostype, hook_id):
    # Stub only the downstream scanner: the real dispatcher must reach it, pass
    # arguments through and preserve its failure instead of returning a skip.
    (package / 'scan-config.yaml').write_text('local_hooks_enabled: false\n')
    (package / 'hooks' / f'{hook_id}.sh').write_text(
        '#!/usr/bin/env bash\nprintf "dispatched:%s:%s\\n" "$SCAN_HOOK_ID" "$1"\nexit 23\n',
        newline='\n')
    (package / 'hooks' / f'{hook_id}.sh').chmod(0o755)
    (package / 'hooks' / f'{hook_id}.ps1').write_text(
        'Write-Output "dispatched:$($env:SCAN_HOOK_ID):$($args[0])"\nexit 23\n')
    env = dict(clean_env(), OSTYPE=ostype)
    env.pop('SCAN_CONFIG_FILE', None)
    result = subprocess.run(hook(package, 'sh', 'dispatcher') + [hook_id, 'argument'],
                            cwd=consumer, env=env, text=True, capture_output=True)
    output = result.stdout + result.stderr
    if hook_id == 'trivy-iac-critical':
        assert result.returncode == 0, output
        assert 'local scanning disabled' in output
        assert 'dispatched:' not in output
    else:
        assert result.returncode == 23, output
        assert f'dispatched:{hook_id}:argument' in output
        assert 'local scanning disabled' not in output


def test_unrelated_colliding_ids_and_aliases_are_preserved(consumer, package, monkeypatch):
    import yaml
    own = {'id': 'checkov', 'alias': 'policy-check', 'stages': ['push']}
    unrelated = {'id': 'checkov', 'alias': 'yaml-check', 'entry': 'custom-scanner', 'language': 'system', 'stages': ['pre-push']}
    config = {'repos': [
        {'repo': 'https://github.com/agenticcodingops/auto-code-scanning', 'hooks': [own]},
        {'repo': 'local', 'hooks': [unrelated]},
    ]}
    (consumer / '.pre-commit-config.yaml').write_text(yaml.safe_dump(config))
    monkeypatch.chdir(consumer)
    selected, forwarded = load_push_runner(package).push_configuration()
    assert selected == [('checkov', [])]
    assert forwarded['repos'] == [{'repo': 'local', 'hooks': [unrelated]}]


def test_real_runner_executes_unrelated_hook_with_colliding_id(consumer, package, scanner):
    import yaml
    if not shutil.which('pre-commit'):
        pytest.skip('pre-commit unavailable')
    shutil.copytree(package / 'hooks', consumer / 'hooks')
    other = {'id': 'checkov', 'alias': 'other-check', 'name': 'other check', 'language': 'system',
             'entry': 'python -c "from pathlib import Path; Path(\'other-ran\').write_text(\'yes\')"',
             'always_run': True, 'stages': ['pre-push'], 'pass_filenames': False}
    config = {'repos': [
        {'repo': 'https://github.com/agenticcodingops/auto-code-scanning', 'rev': 'unused', 'hooks': [{'id': 'checkov'}]},
        {'repo': 'local', 'hooks': [other]},
    ]}
    (consumer / '.pre-commit-config.yaml').write_text(yaml.safe_dump(config))
    runner = consumer / 'hooks/pre-push.py'
    result = subprocess.run([sys.executable, str(runner), '--install-pre-commit'], cwd=consumer,
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    oid = git(consumer, 'rev-parse', 'HEAD')
    env, _ = scanner
    env['SKIP'] = 'unrelated-user-skip'
    result = subprocess.run([sys.executable, str(runner), '--pre-commit-runner', 'origin', 'fixture'],
                            cwd=consumer, env=env, text=True, capture_output=True,
                            input=f'refs/heads/main {oid} refs/heads/main {ZERO}\n')
    assert result.returncode == 0, result.stdout + result.stderr
    assert (consumer / 'other-ran').read_text() == 'yes'
    assert yaml.safe_load((consumer / '.pre-commit-config.yaml').read_text()) == config


def test_adapter_install_uses_python_38_compatible_writes(consumer, package, monkeypatch):
    runner = load_push_runner(package)
    original = consumer / '.git/hooks/pre-push'
    original.write_text('#!/usr/bin/env bash\n# File generated by pre-commit\n# end templated\n')
    previous = Path.write_text
    def older_write_text(self, data, encoding=None, errors=None):
        return previous(self, data, encoding=encoding, errors=errors)
    monkeypatch.setattr(Path, 'write_text', older_write_text)
    monkeypatch.chdir(consumer)
    assert runner.install() == 0
    assert 'scan push transaction adapter' in original.read_text()


def test_adapter_publish_error_restores_original_hook(consumer, package, monkeypatch):
    runner = load_push_runner(package)
    original = consumer / '.git/hooks/pre-push'
    content = '#!/usr/bin/env bash\n# File generated by pre-commit\n# end templated\n'
    original.write_text(content)
    previous = Path.replace
    def failing_replace(self, target):
        if self.name.startswith('.scan-push-'):
            raise OSError('fixture publication failure')
        return previous(self, target)
    monkeypatch.setattr(Path, 'replace', failing_replace)
    monkeypatch.chdir(consumer)
    with pytest.raises(OSError, match='publication'):
        runner.install()
    assert original.read_text() == content


def test_materialization_write_failure_does_not_hang(consumer, package, tmp_path):
    (consumer / 'App.cs').write_bytes(b'x' * (4 * 1024 * 1024))
    git(consumer, 'add', 'App.cs')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'large blob')
    oid = git(consumer, 'rev-parse', 'HEAD')
    destination = tmp_path / 'failed-snapshot'
    destination.mkdir()
    code = '''import runpy,sys
from pathlib import Path
runner=runpy.run_path(sys.argv[1])
original=Path.open
def fail(self,*args,**kwargs):
    if self.name == 'App.cs' and args and args[0] == 'wb':
        raise OSError('fixture destination failure')
    return original(self,*args,**kwargs)
Path.open=fail
runner['materialize'](sys.argv[2],Path(sys.argv[3]))
'''
    result = subprocess.run([sys.executable, '-c', code, str(package / 'hooks/pre-push.py'), oid, str(destination)],
                            cwd=consumer, text=True, capture_output=True, timeout=10)
    assert result.returncode != 0
    assert 'fixture destination failure' in result.stderr


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
def test_staged_config_type_change_cannot_skip_validation(consumer, package, shell):
    (consumer / 'scan-config.yaml').write_text((ROOT / 'scan-config.yaml').read_text())
    git(consumer, 'add', 'scan-config.yaml')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'regular config')
    blob = subprocess.check_output(['git', 'hash-object', '-w', '--stdin'], cwd=consumer,
                                   input=b'other.yaml', env=clean_env()).decode().strip()
    git(consumer, 'update-index', '--cacheinfo', f'120000,{blob},scan-config.yaml')
    result = subprocess.run(hook(package, shell, 'validate-scan-config'), cwd=consumer,
                            text=True, capture_output=True)
    assert result.returncode == 1, result.stdout + result.stderr


def test_setup_without_python_does_not_install_hooks(consumer, tmp_path):
    pwsh = shutil.which('pwsh')
    if not pwsh:
        pytest.skip('PowerShell unavailable')
    bin_dir = tmp_path / 'only-runner'
    bin_dir.mkdir()
    trace = tmp_path / 'installed'
    (bin_dir / 'pre-commit.ps1').write_text(
        "if ($args[0] -eq 'install') { 'installed' | Set-Content -LiteralPath $env:INSTALL_TRACE }\n")
    unix_runner = bin_dir / 'pre-commit'
    unix_runner.write_text('#!/bin/sh\nif [ "${1:-}" = install ]; then '
                           'printf installed > "$INSTALL_TRACE"; fi\n', newline='\n')
    unix_runner.chmod(0o755)
    result = subprocess.run([pwsh, '-NoProfile', '-File', str(ROOT / 'scripts/setup-scan-fix.ps1'),
                             '-RepoPath', str(consumer), '-HooksRunner', 'pre-commit'],
                            env=dict(clean_env(), PATH=str(bin_dir), INSTALL_TRACE=str(trace)),
                            text=True, capture_output=True)
    assert result.returncode != 0, result.stdout + result.stderr
    assert not trace.exists()
    assert 'FAILED: pre-commit hook installation' in result.stdout
    assert 'FAILED: push transaction adapter installation' in result.stdout
    assert (consumer / '.github/workflows/code-security-scan.yml').is_file()


def test_git_helper_ignores_inherited_repository_selection(consumer, tmp_path, monkeypatch):
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    git(elsewhere, 'init', '-q')
    monkeypatch.setenv('GIT_DIR', str(elsewhere / '.git'))
    monkeypatch.setenv('GIT_INDEX_FILE', str(elsewhere / 'index'))
    monkeypatch.setenv('GIT_WORK_TREE', str(elsewhere))
    assert Path(git(consumer, 'rev-parse', '--show-toplevel')).resolve() == consumer.resolve()


def directory_link(link, target):
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        if os.name != 'nt':
            pytest.skip('directory symlink unavailable')
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)], capture_output=True)
        if result.returncode:
            pytest.skip('directory junction unavailable')


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
def test_push_scans_and_exports_report_with_linked_temp_base(consumer, package, scanner, tmp_path, shell):
    actual = tmp_path / 'actual-temp'
    actual.mkdir()
    linked = tmp_path / 'linked-temp'
    directory_link(linked, actual)
    nested = linked / 'nested'
    nested.mkdir()
    env, trace = scanner
    env.update(TMPDIR=str(nested), TMP=str(nested), TEMP=str(nested))
    oid = git(consumer, 'rev-parse', 'HEAD')
    result = subprocess.run(hook(package, shell, 'dotnet-build'), cwd=consumer, env=env,
                            input=f'ref {oid} ref {ZERO}\n', text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(trace.read_text()) == {'App.cs': 'pushed bytes\n'}
    assert json.loads((consumer / '.scanning/last-scan.json').read_text())['summary']['total_findings'] == 0
    assert list(actual.iterdir()) == [actual / 'nested']
    assert not list(nested.iterdir())


def test_push_refuses_link_created_inside_canonical_snapshot(consumer, package, tmp_path, monkeypatch):
    runner = load_push_runner(package)
    outside = tmp_path / 'outside-report'
    outside.mkdir()
    sentinel = outside / 'last-scan.json'
    sentinel.write_text('untouched')
    materialize = runner.materialize

    def linked_report(oid, snapshot):
        names = materialize(oid, snapshot)
        directory_link(snapshot / '.scanning', outside)
        return names

    monkeypatch.chdir(consumer)
    monkeypatch.setattr(runner, 'materialize', linked_report)
    oid = git(consumer, 'rev-parse', 'HEAD')
    with pytest.raises(OSError, match='symlink or reparse point'):
        runner.scan(f'ref {oid} ref {ZERO}\n', [('dotnet-build', [])], 'auto')
    assert sentinel.read_text() == 'untouched'


def helper_without_git(package, tmp_path, shell, command, manifest, **settings):
    executable = shutil.which('bash' if shell == 'sh' else 'pwsh')
    if not executable:
        pytest.skip('shell unavailable')
    common = (package / f'hooks/lib/common.{shell}').as_posix()
    env = dict(clean_env(), SCAN_PUSH_SNAPSHOT='1', SCAN_ALLOW_TOOL_ERRORS='1',
               SCAN_PUSH_FILES=str(manifest) if manifest else '')
    env.update(settings)
    if shell == 'sh':
        # Keep only the file utilities needed by the helpers; Git truly cannot
        # be resolved, and this works with Git Bash as well as POSIX shells.
        prefix = (f'set -euo pipefail; source "{common}"; '
                  'CAT=$(command -v cat); MKTEMP=$(command -v mktemp); '
                  'RM=$(command -v rm); SORT=$(command -v sort); '
                  'cat() { "$CAT" "$@"; }; mktemp() { "$MKTEMP" "$@"; }; '
                  'rm() { "$RM" "$@"; }; sort() { "$SORT" "$@"; }; '
                  'export PATH=""; ! command -v git; ')
        args = [executable, '-c', prefix + command]
    else:
        prefix = f". '{common}'; $env:PATH=''; if (Get-Command git -ErrorAction SilentlyContinue) {{ throw 'git still available' }}; "
        args = [executable, '-NoProfile', '-Command', prefix + command]
    return subprocess.run(args, cwd=tmp_path, env=env, capture_output=True, text=True, encoding='utf-8')


SELECTION_HELPERS = [
    ('sh', '_changed_files_for_detect'), ('sh', 'detect_changed_dirs'),
    ('sh', 'detect_all_changed_dirs'), ('sh', 'get_staged_files'),
    ('ps1', 'Get-ChangedFilesForDetect'), ('ps1', 'Get-ChangedDirs'),
    ('ps1', 'Get-AllChangedDirs'), ('ps1', 'Get-StagedFiles'),
]


@pytest.mark.parametrize('shell,helper', SELECTION_HELPERS)
@pytest.mark.parametrize('contents', [b'', b'module space/main.tf\0App.cs\0'])
def test_push_manifest_selection_without_git(package, tmp_path, shell, helper, contents):
    manifest = tmp_path / 'paths'
    manifest.write_bytes(contents)
    result = helper_without_git(package, tmp_path, shell, helper, manifest)
    assert result.returncode == 0, result.stdout + result.stderr
    actual = result.stdout.replace('\\', '/').replace('\0', '\n').splitlines()
    if not contents:
        assert actual == []
    elif 'Dirs' in helper or 'dirs' in helper:
        expected = ['module space'] if helper in ('Get-ChangedDirs', 'detect_changed_dirs') else ['.', 'module space']
        assert actual == expected
    else:
        assert actual == ['module space/main.tf', 'App.cs']


@pytest.mark.parametrize('shell,helper', SELECTION_HELPERS)
def test_push_unreadable_manifest_blocks_without_git(package, tmp_path, shell, helper):
    result = helper_without_git(package, tmp_path, shell, helper, tmp_path / 'missing-paths')
    assert result.returncode == 1, result.stdout + result.stderr
    assert not result.stdout.strip()
    assert result.stderr.strip()


@pytest.mark.parametrize('shell,helper', SELECTION_HELPERS + [
    ('sh', 'export_staged_to_tmp App.cs'), ('ps1', 'Export-StagedFilesToTempDir -Files App.cs'),
    ('ps1', "Invoke-GitPaths -Arguments @('diff', '--cached', '--name-only', '-z')"),
])
@pytest.mark.parametrize('snapshot', ['0', '1'])
def test_push_git_required_without_manifest_blocks_even_with_opt_in(package, tmp_path, shell, helper, snapshot):
    result = helper_without_git(package, tmp_path, shell, helper, None,
                                SCAN_PUSH_SNAPSHOT=snapshot, SCAN_LEGACY_PUSH_STATE='1')
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'git is required' in result.stderr
    assert 'scan incomplete' in result.stderr


@pytest.mark.parametrize('shell,helper', [
    ('sh', 'export_staged_to_tmp missing.cs'),
    ('ps1', 'Export-StagedFilesToTempDir -Files missing.cs'),
])
def test_staged_export_failure_blocks(consumer, package, shell, helper):
    executable = shutil.which('bash' if shell == 'sh' else 'pwsh')
    if not executable:
        pytest.skip('shell unavailable')
    common = (package / f'hooks/lib/common.{shell}').as_posix()
    args = ([executable, '-c', f'set -euo pipefail; source "{common}"; {helper}'] if shell == 'sh' else
            [executable, '-NoProfile', '-Command', f". '{common}'; {helper}"])
    result = subprocess.run(args, cwd=consumer, env=clean_env(), capture_output=True, text=True)
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'scan incomplete' in result.stderr


@pytest.mark.parametrize('name', (ROOT / 'hooks/lib/push-hook-ids.txt').read_text().split())
@pytest.mark.parametrize('scanner_exit', [0, 1])
def test_powershell_push_scanners_run_manifest_without_git(
        package, scanner, tmp_path, name, scanner_exit):
    pwsh = shutil.which('pwsh')
    if not pwsh:
        pytest.skip('PowerShell unavailable')
    snapshot = tmp_path / 'snapshot'
    snapshot.mkdir()
    (snapshot / 'main.tf').write_text('# pushed Terraform\n')
    (snapshot / 'App.cs').write_text('pushed C#\n')
    (snapshot / 'App.sln').write_text('fixture')
    manifest = tmp_path / 'paths'
    manifest.write_bytes(b'main.tf\0App.cs\0App.sln\0')
    env, trace = scanner
    if os.name != 'nt':
        # The fixture's POSIX scanner shims need these interpreters, while Git
        # must remain absent from the child process's executable search path.
        (tmp_path / 'bin/bash').symlink_to(shutil.which('bash'))
        (tmp_path / 'bin/python').symlink_to(sys.executable)
    env.update(PATH=str(tmp_path / 'bin'), SCAN_PUSH_SNAPSHOT='1', SCAN_PUSH_FILES=str(manifest),
               SCANNER_EXIT=str(scanner_exit), SNYK_TOKEN='fixture')
    command = ("if (Get-Command git -ErrorAction SilentlyContinue) { throw 'git still available' }; "
               f"& '{(package / f'hooks/{name}.ps1').as_posix()}'; exit $LASTEXITCODE")
    result = subprocess.run([pwsh, '-NoProfile', '-Command', command], cwd=snapshot,
                            env=env, capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == scanner_exit, result.stdout + result.stderr
    assert trace.is_file(), result.stdout + result.stderr
    assert 'No Terraform files' not in result.stdout
    assert 'No C# files' not in result.stdout
