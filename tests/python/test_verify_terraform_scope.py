"""Run the real verifier with isolated external tool stubs and consumer YAML."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from .tool_helpers import application

ROOT = Path(__file__).resolve().parents[2]


def verify(tmp_path, config, configs=('lefthook',), runner=None, python_mode='normal'):
    pwsh, git = shutil.which('pwsh'), shutil.which('git')
    if not pwsh:
        pytest.skip('PowerShell unavailable')
    repo = tmp_path / 'consumer'
    repo.mkdir()
    subprocess.run([git, 'init', '-q', str(repo)], check=True, capture_output=True)
    if config is not None:
        (repo / 'scan-config.yaml').write_text(config, encoding='utf-8')
    for selected in configs:
        source = (ROOT / 'templates/lefthook/lefthook.yml' if selected == 'lefthook'
                  else ROOT / 'templates/standard/pre-commit-config.yaml')
        shutil.copyfile(source, repo / ('lefthook.yml' if selected == 'lefthook'
                                       else '.pre-commit-config.yaml'))
    selected = runner or (configs[0] if len(configs) == 1 else 'lefthook')
    for hook in ('pre-commit', 'pre-push'):
        marker = ('# scan push transaction adapter\n# --pre-commit-runner\n'
                  if selected == 'pre-commit' and hook == 'pre-push' else '# ' + selected + '\n')
        (repo / '.git/hooks' / hook).write_text(marker, encoding='utf-8')
    # Repository modules must never be loaded while deciding scope or checking hooks.
    for name in ('yaml.py', 'sitecustomize.py'):
        (repo / name).write_text('raise RuntimeError("CONSUMER_CODE_EXECUTED")', encoding='utf-8')
    tools = tmp_path / 'tools'
    for name in ('trivy', 'lefthook', 'pre-commit'):
        application(tools, name, 'print("1.0.0")\n')
    application(tools, 'git', 'import subprocess, sys\nsys.exit(subprocess.call(['
                + repr(git) + ', *sys.argv[1:]]))\n')
    if python_mode in ('normal', 'no-parser', 'failure'):
        python_flags = ', "-S"' if python_mode == 'no-parser' else ''
        source = ('import subprocess, sys\nsys.exit(subprocess.call([' + repr(sys.executable)
                  + python_flags + ', *sys.argv[1:]]))\n' if python_mode != 'failure'
                  else 'raise SystemExit(19)\n')
        application(tools, 'python', source)
    elif python_mode == 'inside':
        application(repo / 'bin', 'python',
                    'from pathlib import Path\nPath("consumer-code-executed").touch()\nprint("false")\n')
    # Expose only these stubs: Git/Python installation directories can contain
    # other scanners or another Python, which would invalidate missing-tool cases.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('GIT_', 'SCAN_', 'TFLINT_'))}
    paths = [str(tools)]
    if python_mode == 'inside':
        paths.insert(0, str(repo / 'bin'))
    env['PATH'] = os.pathsep.join(paths)
    command = [pwsh, '-NoProfile', '-File', str(ROOT / 'scripts/verify-scanning.ps1')]
    if runner:
        command += ['-HooksRunner', runner]
    result = subprocess.run(command, cwd=repo, env=env, capture_output=True,
                            text=True, encoding='utf-8', timeout=60)
    assert not (repo / 'consumer-code-executed').exists()
    return result


def test_app_only_verifier_skips_terraform_checks(tmp_path):
    result = verify(tmp_path, 'languages:\n  terraform:\n    enabled: false\n')
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'Overall Status: PASSED' in result.stdout
    assert 'lefthook pre-commit hook installed' in result.stdout
    for name in ('Checkov', 'Terraform', 'tflint'):
        assert f'[PASS] {name}' not in result.stdout
        assert f'{name} NOT FOUND' not in result.stdout
    assert '[SKIP]' in result.stdout
    assert 'languages.terraform.enabled is explicitly false' in result.stdout
    assert 'CONSUMER_CODE_EXECUTED' not in result.stdout + result.stderr


@pytest.mark.parametrize('config', [
    None, '', '{}', 'languages: {}', 'languages: {terraform: {}}',
    'languages: {terraform: {enabled: true}}',
    'languages: {terraform: {enabled: "false"}}',
    'languages: {terraform: {enabled: 0}}',
    'languages: {terraform: {enabled: null}}',
    'languages: {terraform: false}', 'languages: []', '[]', 'invalid: [',
])
def test_verifier_scope_fails_closed(tmp_path, config):
    result = verify(tmp_path, config)
    assert result.returncode == 1, result.stdout + result.stderr
    for name in ('Checkov', 'Terraform', 'tflint'):
        assert f'{name} NOT FOUND' in result.stdout
    assert 'Trusted external tflint configuration NOT FOUND' in result.stdout
    assert 'Checkov configuration NOT FOUND' in result.stdout
    assert 'Cannot test tflint - not installed' in result.stdout
    assert '[SKIP]' not in result.stdout


@pytest.mark.parametrize('python_mode', ['no-parser', 'failure', 'inside', 'missing'])
def test_verifier_scope_requires_a_trusted_working_parser(tmp_path, python_mode):
    result = verify(tmp_path, 'languages: {terraform: {enabled: false}}',
                    python_mode=python_mode)
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'Terraform NOT FOUND' in result.stdout
    assert '[SKIP]' not in result.stdout
    assert 'Terraform remains in scope' in result.stdout


@pytest.mark.parametrize(('configs', 'runner', 'expected'), [
    (('pre-commit',), None, 'pre-commit'),
    (('lefthook', 'pre-commit'), None, 'lefthook'),
    ((), None, 'lefthook'),
    (('lefthook', 'pre-commit'), 'pre-commit', 'pre-commit'),
    (('pre-commit',), 'lefthook', 'lefthook'),
])
def test_verifier_runner_detection_and_explicit_override(tmp_path, configs, runner, expected):
    result = verify(tmp_path, 'languages: {terraform: {enabled: false}}', configs, runner)
    assert f'3. Checking {expected} Hooks' in result.stdout
    if expected in configs:
        assert result.returncode == 0, result.stdout + result.stderr
    else:
        assert result.returncode == 1, result.stdout + result.stderr
        filename = 'lefthook.yml' if expected == 'lefthook' else '.pre-commit-config.yaml'
        assert f'Cannot check hooks - {filename} not found' in result.stdout
