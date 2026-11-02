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
                    'print(\'{"results":{"failed_checks":[]},"issues":[],"infrastructureAsCodeIssues":[]}\')\n')
    for name in ('dotnet', 'checkov', 'tflint', 'trivy', 'snyk'):
        target = bin_dir / name
        target.write_text(f'#!/usr/bin/env bash\nexec python "{mock.as_posix()}" "$@"\n', newline='\n')
        target.chmod(0o755)
        (bin_dir / f'{name}.cmd').write_text(f'@"{sys.executable}" "{mock}" %*\n')
    return dict(clean_env(), PATH=str(bin_dir) + os.pathsep + os.environ['PATH'], TRACE=str(trace)), trace


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
    policies = consumer / '.scanning/configs'
    policies.mkdir(parents=True)
    (policies / '.tflint.hcl').write_text('# tracked policy\n')
    (policies / '.checkov.yaml').write_text('quiet: true\n')
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


def load_push_runner(package):
    import importlib.util
    spec = importlib.util.spec_from_file_location('push_runner', package / 'hooks/pre-push.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    (policies / '.tflint.hcl').write_text('# required cloud rules\n')
    oid = git(consumer, 'rev-parse', 'HEAD')
    env, trace = scanner
    result = subprocess.run(hook(package, shell, 'tflint'), cwd=consumer, env=env,
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
    assert all(module.MANIFEST_STAGES[name] == manifest[name]['stages'] for name in module.HOOKS)


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
    (bin_dir / 'pre-commit.ps1').write_text("'installed' | Set-Content -LiteralPath $env:INSTALL_TRACE\n")
    unix_runner = bin_dir / 'pre-commit'
    unix_runner.write_text('#!/bin/sh\nprintf installed > "$INSTALL_TRACE"\n', newline='\n')
    unix_runner.chmod(0o755)
    result = subprocess.run([pwsh, '-NoProfile', '-File', str(ROOT / 'scripts/setup-scan-fix.ps1'),
                             '-RepoPath', str(consumer), '-HooksRunner', 'pre-commit'],
                            env=dict(clean_env(), PATH=str(bin_dir), INSTALL_TRACE=str(trace)),
                            text=True, capture_output=True)
    assert result.returncode != 0, result.stdout + result.stderr
    assert not trace.exists()


def test_git_helper_ignores_inherited_repository_selection(consumer, tmp_path, monkeypatch):
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    git(elsewhere, 'init', '-q')
    monkeypatch.setenv('GIT_DIR', str(elsewhere / '.git'))
    monkeypatch.setenv('GIT_INDEX_FILE', str(elsewhere / 'index'))
    monkeypatch.setenv('GIT_WORK_TREE', str(elsewhere))
    assert Path(git(consumer, 'rev-parse', '--show-toplevel')).resolve() == consumer.resolve()
