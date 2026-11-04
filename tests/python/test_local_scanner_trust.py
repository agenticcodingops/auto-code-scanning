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
                                   'external-modules-download-path: example', 'output-file-path: [example]',
                                   'future-option: example', 'download-external-modules: true',
                                   'skip-check: {invalid: mapping}', 'skip-check: [', '[]'])
def test_driver_rejects_nonpassive_policy_before_launch(consumer, content, monkeypatch):
    import scan
    policy = consumer / 'policy.yaml'
    policy.write_text(content, encoding='utf-8')
    launched = []
    def run(*args, **kwargs):
        launched.append(args)
        return 0, '{"results":{"failed_checks":[],"skipped_checks":[]}}', ''
    monkeypatch.setattr(scan, 'run_cmd', run)
    assert scan.run_checkov(consumer, config_file=policy)[1] is True
    assert launched == []


def test_driver_accepts_and_drops_legacy_output_path(consumer, monkeypatch):
    # Earlier setup releases wrote output-file-path into consumer configs.
    import scan
    policy = consumer / 'policy.yaml'
    policy.write_text('output-file-path: .scan-results\nskip-check: [CKV_AWS_19]\n', encoding='utf-8')
    seen = []
    def run(cmd, **kwargs):
        seen.append(Path(cmd[cmd.index('--config-file') + 1]).read_text(encoding='utf-8'))
        return 0, '{"results":{"failed_checks":[],"skipped_checks":[]}}', ''
    monkeypatch.setattr(scan, 'run_cmd', run)
    assert scan.run_checkov(consumer, config_file=policy)[1] is False
    assert len(seen) == 1 and 'CKV_AWS_19' in seen[0] and 'output-file-path' not in seen[0]


def test_driver_policy_root_selects_policy_and_disables_discovery(consumer, tmp_path, monkeypatch):
    import scan
    untrusted = consumer / '.scanning/configs/.checkov.yaml'
    untrusted.parent.mkdir(parents=True)
    untrusted.write_text('external-checks-dir: example\n', encoding='utf-8')
    trusted = tmp_path / 'policy'
    (trusted / '.scanning/configs').mkdir(parents=True)
    (trusted / '.scanning/configs/.checkov.yaml').write_text('skip-check: [CKV_AWS_19]\n', encoding='utf-8')
    seen = []
    def run(cmd, **kwargs):
        selected = Path(cmd[cmd.index('--config-file') + 1])
        seen.append(selected.read_text(encoding='utf-8'))
        return 0, '{"results":{"failed_checks":[],"skipped_checks":[]}}', ''
    monkeypatch.setattr(scan, 'run_cmd', run)
    assert scan.run_checkov(consumer, config_file=untrusted, trusted_root=trusted)[1] is False
    assert len(seen) == 1 and 'CKV_AWS_19' in seen[0] and 'external-checks' not in seen[0]
    seen.clear()
    assert scan.run_checkov(consumer)[1] is False
    assert len(seen) == 1 and 'external-checks' not in seen[0]


def test_other_scanners_can_load_without_policy_dependencies():
    command = (f'import sys; sys.path.insert(0, {str(ROOT / "scripts")!r}); '
               'import scan; assert scan.run_checkov(".")[1] is True; print("loaded")')
    result = subprocess.run([sys.executable, '-I', '-S', '-c', command],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == 'loaded'
    assert 'policy support unavailable' in result.stderr


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
def test_push_rejects_nonpassive_policy_before_hook(consumer, monkeypatch, shell):
    policy = consumer / '.scanning/configs/.checkov.yaml'
    policy.parent.mkdir(parents=True)
    policy.write_text('external-checks-dir: example\n', encoding='utf-8')
    (consumer / 'main.tf').write_text('resource "sample" "one" {}\n', encoding='utf-8')
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
        path.write_text(path.read_text(encoding='utf-8'), encoding='utf-8', newline='\n')
    return package


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('hook,source,tool', [
    ('semgrep-csharp', 'App.cs', 'semgrep'),
    ('semgrep-typescript', 'app.ts', 'semgrep'),
    ('trivy-iac-critical', 'main.tf', 'trivy'),
    ('sqlfluff', 'query.sql', 'sqlfluff'),
])
def test_security_scanners_read_index_and_sql_linter_reads_worktree(consumer, package, tmp_path, hook, source, tool, shell):
    runner = load_runner('shell_lookup', 'pre-push.py')
    _, executable = runner.select_shell(shell)
    (consumer / source).write_text('staged-review-marker\n', encoding='utf-8')
    git(consumer, 'add', '--', source)
    (consumer / source).write_text('worktree-review-marker\n', encoding='utf-8')
    trace = tmp_path / 'trace.json'
    binary = tmp_path / 'bin'
    binary.mkdir()
    probe = binary / 'probe.py'
    probe.write_text('''import json, os, pathlib, sys
root = pathlib.Path.cwd()
files = {p.name: p.read_text(encoding='utf-8') for p in root.rglob('*') if p.is_file() and p.suffix in ('.cs','.ts','.tf','.sql')}
pathlib.Path(os.environ['TRACE']).write_text(json.dumps({'cwd':str(root),'files':files}), encoding='utf-8')
if '--output' in sys.argv:
    pathlib.Path(sys.argv[sys.argv.index('--output')+1]).write_text(json.dumps({'results':[
        {'check_id':'review-rule','path':next(iter(files)), 'start':{'line':1}, 'end':{'line':1},
         'extra':{'severity':'ERROR','message':'Review finding'}}]}), encoding='utf-8')
print('{"Results":[]}')
sys.exit(1 if any('staged-review-marker' in text for text in files.values()) else 0)
''', encoding='utf-8')
    (binary / tool).write_text(f'#!/usr/bin/env bash\n"{Path(sys.executable).as_posix()}" "{probe.as_posix()}" "$@"\n', newline='\n', encoding='utf-8')
    (binary / tool).chmod(0o755)
    (binary / f'{tool}.cmd').write_text(f'@"{sys.executable}" "{probe}" %*\n', encoding='utf-8')
    env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ['PATH'], TRACE=str(trace))
    command = ([executable, '-NoProfile', '-File'] if shell == 'ps1' else [executable])
    result = subprocess.run(command + [str(package / f'hooks/{hook}.{shell}')], cwd=consumer,
                            env=env, capture_output=True, text=True)
    assert trace.exists(), result.stdout + result.stderr
    seen = json.loads(trace.read_text(encoding='utf-8'))
    is_security_scanner = hook != 'sqlfluff'
    assert (Path(seen['cwd']) != consumer) is is_security_scanner
    expected = 'staged-review-marker\n' if is_security_scanner else 'worktree-review-marker\n'
    assert seen['files'][source] == expected
    assert (consumer / source).read_text(encoding='utf-8') == 'worktree-review-marker\n'
    assert result.returncode == int(is_security_scanner), result.stdout + result.stderr
    assert Path(seen['cwd']).exists() is (not is_security_scanner)


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
    source = (ROOT / f'hooks/lib/common.{shell}').read_text(encoding='utf-8')
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
    (consumer / 'main.tf').write_text('# source\n', encoding='utf-8')
    config = consumer / '.scanning/configs/.checkov.yaml'
    config.parent.mkdir(parents=True)
    config.write_text(policy, encoding='utf-8')
    manifest = consumer.parent / 'paths'
    manifest.write_bytes(b'main.tf\0')
    env, trace = scanner
    env.update(SCAN_PUSH_SNAPSHOT='1', SCAN_PUSH_FILES=str(manifest))
    command = ([executable, '-NoProfile', '-File'] if shell == 'ps1' else [executable])
    result = subprocess.run(command + [str(package / f'hooks/{hook}.{shell}')] + extra,
                            cwd=consumer, env=env, capture_output=True, text=True)
    assert result.returncode != 0, result.stdout + result.stderr
    message = result.stdout + result.stderr
    assert 'Checkov' in message and any(word in message for word in ('disabled', 'rejected'))
    assert not trace.exists()


@pytest.mark.parametrize('entry', ['link', 'unmerged'])
def test_index_export_errors_block_before_scanner(consumer, package, scanner, entry):
    report = consumer / '.scanning/last-scan.json'
    report.parent.mkdir()
    report.write_text('previous report\n', encoding='utf-8')
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
    assert not report.exists()


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
def test_index_snapshot_preserves_consumer_tool_boundary(consumer, package, scanner, shell):
    runner = load_runner('boundary_shell', 'pre-push.py')
    _, executable = runner.select_shell(shell)
    (consumer / 'main.tf').write_text('# staged source\n', encoding='utf-8')
    git(consumer, 'add', 'main.tf')
    env, trace = scanner
    original_bin = Path(env['PATH'].split(os.pathsep)[0])
    local_bin = consumer / 'bin'
    shutil.copytree(original_bin, local_bin)
    env['PATH'] = str(local_bin) + os.pathsep + os.environ['PATH']
    command = ([executable, '-NoProfile', '-File'] if shell == 'ps1' else [executable])
    result = subprocess.run(command + [str(package / f'hooks/trivy-iac-critical.{shell}')],
                            cwd=consumer, env=env, capture_output=True, text=True)
    assert result.returncode != 0, result.stdout + result.stderr
    assert not trace.exists()


@pytest.mark.parametrize('ruleset', ['rules/custom.yml', 'rules', 'absolute', '.', 'absolute-root'])
def test_snapshot_keeps_local_rule_inputs_in_the_index(consumer, monkeypatch, ruleset):
    rules = consumer / 'rules/custom.yml'
    rules.parent.mkdir()
    rules.write_text('staged rule inputs\n', encoding='utf-8')
    (consumer / 'App.cs').write_text('// source\n', encoding='utf-8')
    git(consumer, 'add', '.')
    rules.write_text('worktree rule inputs\n', encoding='utf-8')
    configured = {'absolute': str(rules), 'absolute-root': str(consumer)}.get(ruleset, ruleset)
    monkeypatch.setenv('SEMGREP_RULESET_CSHARP', configured)
    runner = load_runner('local_rules_snapshot', 'pre-commit.py')
    monkeypatch.setattr(runner.push, 'select_shell', lambda _: ('sh', 'scanner-shell'))
    original = subprocess.run
    def run(command, **kwargs):
        if command[0] != 'scanner-shell':
            return original(command, **kwargs)
        snapshot = kwargs['cwd']
        assert (snapshot / 'rules/custom.yml').read_text(encoding='utf-8') == 'staged rule inputs\n'
        assert not Path(kwargs['env']['SEMGREP_RULESET_CSHARP']).is_absolute()
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(runner.subprocess, 'run', run)
    assert runner.scan('semgrep-csharp', [], 'sh') == 0


def test_hook_runners_load_without_pyyaml(monkeypatch):
    # Hooks that never read a Checkov policy must not need PyYAML just to load.
    monkeypatch.setitem(sys.modules, 'yaml', None)
    for name in ('checkov_policy', 'pre_push_no_yaml', 'pre_commit_no_yaml'):
        sys.modules.pop(name, None)
    load_runner('pre_push_no_yaml', 'pre-push.py')
    load_runner('pre_commit_no_yaml', 'pre-commit.py')


@pytest.mark.parametrize('ruleset', ['rules/custom.yml', 'absolute', 'absolute-missing', 'p/csharp'])
def test_unstaged_relative_ruleset_fails_clearly(consumer, monkeypatch, ruleset):
    # A local rule file the snapshot cannot see is an error; a registry reference is not.
    rules = consumer / 'rules/custom.yml'
    rules.parent.mkdir()
    rules.write_text('worktree only\n', encoding='utf-8')
    if ruleset == 'absolute-missing':
        rules.unlink()
    (consumer / 'App.cs').write_text('// source\n', encoding='utf-8')
    git(consumer, 'add', 'App.cs')
    monkeypatch.setenv('SEMGREP_RULESET_CSHARP', str(rules) if ruleset.startswith('absolute') else ruleset)
    runner = load_runner('unstaged_rules_snapshot', 'pre-commit.py')
    monkeypatch.setattr(runner.push, 'select_shell', lambda _: ('sh', 'scanner-shell'))
    original = subprocess.run
    seen = []
    def run(command, **kwargs):
        if command[0] != 'scanner-shell':
            return original(command, **kwargs)
        seen.append(kwargs['env']['SEMGREP_RULESET_CSHARP'])
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(runner.subprocess, 'run', run)
    if ruleset == 'p/csharp':
        assert runner.scan('semgrep-csharp', [], 'sh') == 0
        assert seen == ['p/csharp']
    else:
        with pytest.raises(ValueError, match='not staged'):
            runner.scan('semgrep-csharp', [], 'sh')
        assert seen == []


@pytest.mark.parametrize('split_index', [False, True])
def test_snapshot_capture_leaves_the_shared_index_unlocked_and_unchanged(consumer, package, scanner, split_index):
    (consumer / 'main.tf').write_text('# source\n', encoding='utf-8')
    git(consumer, 'add', '.')
    if split_index:
        git(consumer, 'update-index', '--split-index')
    before = (consumer / '.git/index').read_bytes()
    lock = consumer / '.git/index.lock'
    lock.write_text('another index writer\n', encoding='utf-8')
    env, trace = scanner
    result = subprocess.run([sys.executable, str(package / 'hooks/pre-commit.py'), 'trivy-iac-critical', '--shell', 'ps1' if os.name == 'nt' else 'sh'],
                            cwd=consumer, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert trace.exists()
    assert (consumer / '.git/index').read_bytes() == before
    assert lock.read_text(encoding='utf-8') == 'another index writer\n'


def test_commit_iac_snapshot_keeps_context_but_limits_manifest(consumer, monkeypatch):
    module = consumer / 'module'
    module.mkdir()
    (module / 'main.tf').write_text('# original\n', encoding='utf-8')
    (module / 'variables.tf').write_text('# unchanged module context\n', encoding='utf-8')
    (module / 'settings.tf.json').write_text('{}\n', encoding='utf-8')
    (module / 'terraform.tfvars').write_text('value = "staged"\n', encoding='utf-8')
    (module / 'ignored.txt').write_text('not Terraform\n', encoding='utf-8')
    (module / 'nested').mkdir()
    (module / 'nested/main.tf').write_text('# other module\n', encoding='utf-8')
    git(consumer, 'add', '.')
    git(consumer, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test',
        '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'fixture')
    (module / 'main.tf').write_text('# staged change\n', encoding='utf-8')
    git(consumer, 'add', 'module/main.tf')
    (module / 'main.tf').write_text('# worktree change\n', encoding='utf-8')
    (module / 'variables.tf').write_text('# worktree context\n', encoding='utf-8')
    runner = load_runner('selected_iac_snapshot', 'pre-commit.py')
    monkeypatch.setattr(runner.push, 'select_shell', lambda _: ('sh', 'scanner-shell'))
    original = subprocess.run
    def run(command, **kwargs):
        if command[0] != 'scanner-shell':
            return original(command, **kwargs)
        snapshot = kwargs['cwd']
        assert (snapshot / 'module/main.tf').read_text(encoding='utf-8') == '# staged change\n'
        assert (snapshot / 'module/variables.tf').read_text(encoding='utf-8') == '# unchanged module context\n'
        assert (snapshot / 'module/settings.tf.json').read_text(encoding='utf-8') == '{}\n'
        assert (snapshot / 'module/terraform.tfvars').read_text(encoding='utf-8') == 'value = "staged"\n'
        assert not (snapshot / 'module/ignored.txt').exists()
        assert not (snapshot / 'module/nested/main.tf').exists()
        assert Path(kwargs['env']['SCAN_PUSH_FILES']).read_bytes() == b'module/main.tf\0'
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(runner.subprocess, 'run', run)
    assert runner.scan('trivy-iac-critical', [], 'sh') == 0


def test_security_snapshot_omits_sql_only_policy(consumer, monkeypatch):
    (consumer / 'App.cs').write_text('// source\n', encoding='utf-8')
    (consumer / '.sqlfluff').write_text('[sqlfluff]\ndialect = ansi\n', encoding='utf-8')
    git(consumer, 'add', '.')
    runner = load_runner('security_policy_inputs', 'pre-commit.py')
    monkeypatch.setattr(runner.push, 'select_shell', lambda _: ('sh', 'scanner-shell'))
    original = subprocess.run
    def run(command, **kwargs):
        if command[0] != 'scanner-shell':
            return original(command, **kwargs)
        assert (kwargs['cwd'] / 'App.cs').is_file()
        assert not (kwargs['cwd'] / '.sqlfluff').exists()
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(runner.subprocess, 'run', run)
    assert runner.scan('semgrep-csharp', [], 'sh') == 0


@pytest.fixture
def passive_probe(tmp_path):
    """Record scanner operands and files visible in its working directory."""
    binary = tmp_path / 'probe-bin'
    binary.mkdir()
    trace = tmp_path / 'probe.jsonl'
    probe = binary / 'probe.py'
    probe.write_text('''import json, os, pathlib, sys
root = pathlib.Path.cwd()
files = {p.relative_to(root).as_posix(): p.read_text(encoding='utf-8')
         for p in root.rglob('*') if p.is_file() and '.git' not in p.parts}
with open(os.environ['TRACE'], 'a', encoding='utf-8') as output:
    output.write(json.dumps({'args':sys.argv[1:], 'files':files}) + '\\n')
if '--output' in sys.argv:
    pathlib.Path(sys.argv[sys.argv.index('--output')+1]).write_text('{"results":[]}', encoding='utf-8')
print('{"Results":[]}')
sys.exit(int(os.environ.get('PROBE_EXIT', '0')))
''', encoding='utf-8')
    for tool in ('sqlfluff', 'semgrep', 'trivy'):
        target = binary / tool
        target.write_text(f'#!/usr/bin/env bash\nexec "{Path(sys.executable).as_posix()}" -I "{probe.as_posix()}" "$@"\n',
                          encoding='utf-8', newline='\n')
        target.chmod(0o755)
        (binary / f'{tool}.cmd').write_text(f'@"{sys.executable}" -I "{probe}" %*\n', encoding='utf-8')
    return dict(os.environ, PATH=str(binary) + os.pathsep + os.environ['PATH'], TRACE=str(trace)), trace


def wrapper_command(package, shell, hook):
    runner = load_runner('review_shell', 'pre-push.py')
    _, executable = runner.select_shell(shell)
    return ([executable, '-NoProfile', '-File'] if shell == 'ps1' else [executable]) + [
        str(package / f'hooks/{hook}.{shell}')]


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('hook,source', [('semgrep-csharp', 'App.cs'),
                                       ('semgrep-typescript', 'app.ts'), ('trivy-iac-critical', 'main.tf')])
@pytest.mark.parametrize('allow_errors', [False, True])
def test_staged_security_hooks_require_python_before_scanner(consumer, package, passive_probe, shell, hook, source, allow_errors):
    (consumer / source).write_text('staged source\n', encoding='utf-8')
    git(consumer, 'add', source)
    # Interpreter probing (including old/broken candidates) has separate coverage.
    # Model its unavailable result while keeping the scanner installed and usable.
    common = package / f'hooks/lib/common.{shell}'
    unavailable = ('\nfind_python() { return 1; }\n' if shell == 'sh' else
                   '\nfunction Find-WorkingPython { return $null }\n')
    common.write_text(common.read_text(encoding='utf-8') + unavailable, encoding='utf-8', newline='\n')
    env, trace = passive_probe
    env['SCAN_ALLOW_TOOL_ERRORS'] = '1' if allow_errors else '0'
    result = subprocess.run(wrapper_command(package, shell, hook), cwd=consumer, env=env,
                            capture_output=True, text=True)
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'Python is required for index snapshots' in result.stdout + result.stderr
    assert not trace.exists(), 'scanner ran before the required snapshot was created'


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('hook,source', [('semgrep-csharp', 'App.cs'),
                                       ('semgrep-typescript', 'app.ts'), ('trivy-iac-critical', 'main.tf')])
def test_snapshot_launcher_ignores_inherited_pythonpath(consumer, package, passive_probe, shell, hook, source):
    (consumer / source).write_text('staged source\n', encoding='utf-8')
    git(consumer, 'add', source)
    marker = consumer / 'import-marker'
    (consumer / 'argparse.py').write_text(
        f'from pathlib import Path\nPath({str(marker)!r}).write_text("imported")\nraise SystemExit(0)\n',
        encoding='utf-8')
    env, trace = passive_probe
    env['PYTHONPATH'] = str(consumer)
    result = subprocess.run(wrapper_command(package, shell, hook), cwd=consumer, env=env,
                            capture_output=True, text=True)
    assert not marker.exists(), result.stdout + result.stderr
    assert result.returncode == 0, result.stdout + result.stderr
    assert trace.exists(), result.stdout + result.stderr


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
def test_push_launcher_isolates_imports_before_transaction_validation(consumer, package, shell):
    marker = consumer / 'import-marker'
    (consumer / 'argparse.py').write_text(
        f'from pathlib import Path\nPath({str(marker)!r}).write_text("imported")\nraise SystemExit(0)\n',
        encoding='utf-8')
    result = subprocess.run(wrapper_command(package, shell, 'checkov'), cwd=consumer,
                            env=dict(os.environ, PYTHONPATH=str(consumer)), input='invalid transaction\n',
                            capture_output=True, text=True)
    assert not marker.exists(), result.stdout + result.stderr
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'scan incomplete' in result.stderr


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('root_config', [False, True])
def test_sql_worktree_configuration_templates_and_legacy_dialect(consumer, package, passive_probe, shell, root_config):
    # Commit template dependencies first: unchanged inputs must remain available.
    (consumer / 'macros').mkdir()
    (consumer / 'macros/shared.sql').write_text('{% macro value() %}1{% endmacro %}\n', encoding='utf-8')
    (consumer / 'templates').mkdir()
    (consumer / 'templates/base.sql').write_text('select 1;\n', encoding='utf-8')
    git(consumer, 'add', '.')
    git(consumer, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test',
        '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'fixture')
    (consumer / 'sql').mkdir()
    staged = {'query.sql': 'select 1;\n', 'sql/query.sql': 'select 2;\n',
              'pyproject.toml': '[tool.sqlfluff.core]\nexclude_rules = "LT01"\n',
              'setup.cfg': '[sqlfluff]\nexclude_rules = LT01\n',
              'sql/.sqlfluff': '[sqlfluff]\ndialect = postgres\n',
              '.sqlfluffignore': 'generated/\n'}
    if root_config:
        staged['.sqlfluff'] = ('[sqlfluff]\ndialect = sqlite\n[sqlfluff:templater:jinja]\n'
                               'load_macros_from_path = macros\nloader_search_path = templates\n')
    for name, content in staged.items():
        (consumer / name).write_text(content, encoding='utf-8')
    git(consumer, 'add', '.')
    # Both config and templates are read from the worktree, including unstaged edits.
    visible = dict(staged, **{'macros/shared.sql': 'worktree macro\n',
                              'templates/base.sql': 'worktree template\n'})
    visible['pyproject.toml'] += '# worktree configuration\n'
    if root_config:
        visible['.sqlfluff'] = visible['.sqlfluff'].replace('sqlite', 'tsql')
    for name, content in visible.items():
        (consumer / name).write_text(content, encoding='utf-8')
    env, trace = passive_probe
    result = subprocess.run(wrapper_command(package, shell, 'sqlfluff'), cwd=consumer, env=env,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    calls = [json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()]
    assert len(calls) == 1
    call = calls[0]
    assert all(call['files'][name] == content for name, content in visible.items())
    args = call['args']
    assert sorted(args[args.index('--') + 1:]) == ['query.sql', 'sql/query.sql']
    assert ('--dialect' in args) is (not root_config)
    if not root_config:
        assert args[args.index('--dialect') + 1] == 'ansi'


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('tool_exit', [0, 1, 2])
@pytest.mark.parametrize('allow_errors', [False, True])
def test_sql_single_invocation_preserves_exit_policy(consumer, package, passive_probe, shell, tool_exit, allow_errors):
    (consumer / 'query.sql').write_text('select 1;\n', encoding='utf-8')
    git(consumer, 'add', '.')
    env, trace = passive_probe
    env.update(PROBE_EXIT=str(tool_exit), SCAN_ALLOW_TOOL_ERRORS='1' if allow_errors else '0')
    result = subprocess.run(wrapper_command(package, shell, 'sqlfluff'), cwd=consumer, env=env,
                            capture_output=True, text=True)
    assert len(trace.read_text(encoding='utf-8').splitlines()) == 1
    expected = int(tool_exit == 1 or (tool_exit > 1 and not allow_errors))
    assert result.returncode == expected, result.stdout + result.stderr
    if tool_exit in (0, 1):
        import jsonschema
        schema = json.loads((ROOT / 'schemas/last-scan.schema.json').read_text(encoding='utf-8'))
        report = json.loads((consumer / '.scanning/last-scan.json').read_text(encoding='utf-8'))
        jsonschema.validate(report, schema)
        # Consumers accept the single-run report and reject the retired batch contract.
        report['batches'] = [{'name': 'default', 'exit_code': tool_exit, 'output': ''}]
        with pytest.raises(jsonschema.ValidationError, match='batches'):
            jsonschema.validate(report, schema)


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('hook', ['checkov', 'checkov-strict'])
@pytest.mark.parametrize('arguments,accepted', [
    (['origin', 'https://example.test/repo.git'], True),
    (['--external-checks-dir', 'example'], False),
    (['origin', 'https://example.test/repo.git', '--external-checks-dir', 'example'], False),
    (['origin'], False),
])
def test_legacy_push_consumes_only_remote_pair(consumer, package, scanner, shell, hook, arguments, accepted):
    (consumer / 'main.tf').write_text('# selected source\n', encoding='utf-8')
    git(consumer, 'add', '.')
    env, trace = scanner
    env['SCAN_LEGACY_PUSH_STATE'] = '1'
    result = subprocess.run(wrapper_command(package, shell, hook) + arguments,
                            cwd=consumer, env=env, capture_output=True, text=True)
    if accepted:
        assert result.returncode == 0, result.stdout + result.stderr
        assert trace.exists(), result.stdout + result.stderr
    else:
        assert result.returncode != 0, result.stdout + result.stderr
        assert 'Checkov extra arguments are disabled' in result.stdout + result.stderr
        assert not trace.exists()


@pytest.mark.parametrize('output', ['cli', 'json', 'sarif', ['cli', 'json']])
def test_passive_policy_accepts_valid_output_and_removes_it(consumer, output):
    import yaml
    from checkov_policy import passive_policy
    path = consumer / 'policy.yaml'
    path.write_text(yaml.safe_dump({'output': output}), encoding='utf-8')
    assert passive_policy(path) == {'download-external-modules': False, 'skip-download': True}


@pytest.mark.parametrize('output', ['unsupported', ['cli', 'unsupported'], 1, {'cli': True}])
def test_passive_policy_rejects_invalid_output(consumer, output):
    import yaml
    from checkov_policy import passive_policy
    path = consumer / 'policy.yaml'
    path.write_text(yaml.safe_dump({'output': output}), encoding='utf-8')
    with pytest.raises(ValueError, match='output'):
        passive_policy(path)


@pytest.mark.parametrize('hook', ['checkov', 'checkov-strict'])
@pytest.mark.parametrize('tool_exit', [0, 1, 2])
def test_powershell_prepares_one_policy_and_cleans_it_on_all_exits(consumer, package, scanner, hook, tool_exit):
    for folder in ('one', 'two'):
        (consumer / folder).mkdir()
        (consumer / folder / 'main.tf').write_text('# selected\n', encoding='utf-8')
    manifest = consumer.parent / 'paths'
    manifest.write_bytes(b'one/main.tf\0two/main.tf\0')
    helper = package / 'hooks/lib/checkov_policy.py'
    helper.write_text(helper.read_text(encoding='utf-8') + '''
    with open(__import__('os').environ['PREPARATION_TRACE'], 'a') as trace:
        trace.write('prepared\\n')
''', encoding='utf-8')
    # Record the exact policy path and contents for every scanner call.
    env, trace = scanner
    binary = Path(env['PATH'].split(os.pathsep)[0])
    mock = binary / 'mock.py'
    mock.write_text(mock.read_text(encoding='utf-8').replace(
        "folder=pathlib.Path.cwd()", "folder=pathlib.Path.cwd()\n"
        "with open(os.environ['POLICY_CALLS'], 'a') as f:\n"
        " p=pathlib.Path(sys.argv[sys.argv.index('--config-file')+1])\n"
        " f.write(json.dumps({'path':str(p),'content':p.read_text()})+'\\n')"), encoding='utf-8')
    preparations, calls = consumer.parent / 'preparations', consumer.parent / 'policy-calls'
    env.update(SCAN_PUSH_SNAPSHOT='1', SCAN_PUSH_FILES=str(manifest), SCANNER_EXIT=str(tool_exit),
               PREPARATION_TRACE=str(preparations), POLICY_CALLS=str(calls))
    result = subprocess.run(wrapper_command(package, 'ps1', hook), cwd=consumer, env=env,
                            capture_output=True, text=True)
    assert result.returncode == (0 if tool_exit == 0 else 1), result.stdout + result.stderr
    assert preparations.read_text().splitlines() == ['prepared']
    seen = [json.loads(line) for line in calls.read_text().splitlines()]
    assert len(seen) == (1 if tool_exit == 2 else 2)
    assert len({row['path'] for row in seen}) == 1
    assert all('download-external-modules: false' in row['content'] for row in seen)
    assert not Path(seen[0]['path']).exists()


def test_snapshot_runner_accepts_only_security_scanners():
    runner = load_runner('security_commit_hooks', 'pre-commit.py')
    assert set(runner.EXTENSIONS) == {'semgrep-csharp', 'semgrep-typescript', 'trivy-iac-critical'}
