"""Run onboarding and its real verifier against fresh consumer repositories."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


def run(command, repo, env):
    return subprocess.run(command, cwd=repo, env=env, text=True, encoding='utf-8',
                          capture_output=True, timeout=90)


@pytest.mark.parametrize('entrypoint', ['py', 'ps1'])
@pytest.mark.parametrize('runner', ['lefthook', 'pre-commit'])
@pytest.mark.parametrize('tier', ['starter', 'standard', 'strict'])
def test_setup_and_verification_on_fresh_consumer(tmp_path, entrypoint, runner, tier):
    pwsh = shutil.which('pwsh')
    if not pwsh:
        pytest.skip('PowerShell unavailable')
    repo = tmp_path / 'consumer'
    repo.mkdir()
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('GIT_', 'SCAN_', 'TFLINT_', 'CC_SKIP_'))}
    env['PYTHONUTF8'] = '1'
    result = run(['git', 'init', '-q'], repo, env)
    assert result.returncode == 0, result.stderr
    # Only external tools are stubs: setup, rendering, copying, the push adapter,
    # template validation and the PowerShell verifier execute unchanged.
    tools = tmp_path / 'tools'
    tools.mkdir()
    stub = tools / 'tool.py'
    stub.write_text(
        'from pathlib import Path\nimport sys\n'
        'name = sys.argv[1]\n'
        'if sys.argv[2:] == ["install"]:\n'
        '    for hook in (["pre-commit", "pre-push"] if name == "lefthook" else ["pre-commit"]):\n'
        '        Path(".git/hooks", hook).write_text("#!/bin/sh\\n# " + name + "\\n")\n'
        'print("1.0.0")\n', encoding='utf-8')
    for name in ('lefthook', 'pre-commit', 'trivy', 'checkov', 'terraform', 'tflint'):
        launcher = tools / (name + '.cmd' if os.name == 'nt' else name)
        launcher.write_text(
            f'@"{sys.executable}" "{stub}" {name} %*\n@exit /b %errorlevel%\n'
            if os.name == 'nt' else
            f'#!/bin/sh\nexec "{sys.executable}" "{stub}" {name} "$@"\n', encoding='utf-8')
        launcher.chmod(0o755)
    trusted = tmp_path / 'trusted.hcl'
    trusted.write_text('config {}', encoding='utf-8')
    env.update(PATH=str(tools) + os.pathsep + env['PATH'],
               SCAN_TFLINT_CONFIG=str(trusted), SCAN_TFLINT_PLUGIN_DIR=str(tmp_path / 'plugins'))
    # Exercise provider selection as well as the default provider.
    provider = dict(starter='aws', standard='azure', strict='gcp')[tier]
    if entrypoint == 'py':
        command = [sys.executable, str(ROOT / 'scripts/setup-scan-fix.py'),
                   '--repo-path', str(repo), '--tier', tier, '--hooks-runner', runner]
        if provider != 'aws':
            command += ['--cloud-provider', provider]
    else:
        command = [pwsh, '-NoProfile', '-File', str(ROOT / 'scripts/setup-scan-fix.ps1'),
                   '-RepoPath', str(repo), '-Tier', tier, '-HooksRunner', runner]
        if provider != 'aws':
            command += ['-CloudProvider', provider]
    result = run(command, repo, env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '=== SETUP COMPLETE ===' in result.stdout
    config = repo / '.scanning/configs/.checkov.yaml'
    assert config.read_bytes() == (ROOT / f'configs/{provider}/.checkov.yaml').read_bytes()
    assert not (repo / '.checkov.yaml').exists()
    verify = [pwsh, '-NoProfile', '-File', str(ROOT / 'scripts/verify-scanning.ps1'),
              '-HooksRunner', runner, '-Tier', tier]
    result = run(verify, repo, env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'Overall Status: PASSED' in result.stdout
    # The installed layout is required, rather than an optional warning or a
    # fallback that masks a genuinely incomplete installation.
    config.unlink()
    (repo / '.checkov.yaml').write_text('{}', encoding='utf-8')
    result = run(verify, repo, env)
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'Checkov configuration NOT FOUND' in result.stdout
    assert 'Overall Status: FAILED' in result.stdout


@pytest.mark.parametrize('runner', ['lefthook', 'pre-commit'])
@pytest.mark.parametrize('damage', ['missing', 'comment', 'malformed'])
def test_template_validation_rejects_incomplete_config(tmp_path, runner, damage):
    template = (ROOT / 'templates/lefthook/lefthook.yml' if runner == 'lefthook' else
                ROOT / 'templates/strict/pre-commit-config.yaml')
    text = template.read_text(encoding='utf-8')
    if damage == 'malformed':
        text = 'invalid: ['
    elif runner == 'lefthook':
        text = text.replace('run: hooks/dispatcher.sh trivy-secrets',
                            '# run: hooks/dispatcher.sh trivy-secrets' if damage == 'comment' else
                            'run: echo removed')
    else:
        text = text.replace('- id: trivy-secrets',
                            '# - id: trivy-secrets' if damage == 'comment' else '- id: removed')
    config = tmp_path / 'config.yaml'
    config.write_text(text, encoding='utf-8')
    result = run([sys.executable, '-I', str(ROOT / 'scripts/verify-setup-hooks.py'),
                  runner, 'strict', str(config)], tmp_path, os.environ.copy())
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'Hook configuration invalid:' in result.stdout


def test_expected_hook_ids_come_from_selected_template(tmp_path):
    platform = tmp_path / 'platform'
    (platform / 'scripts').mkdir(parents=True)
    shutil.copyfile(ROOT / 'scripts/verify-setup-hooks.py', platform / 'scripts/verify-setup-hooks.py')
    (platform / 'templates/starter').mkdir(parents=True)
    template = platform / 'templates/starter/pre-commit-config.yaml'
    template.write_text('repos:\n- repo: local\n  hooks:\n  - id: template-specific-hook\n', encoding='utf-8')
    config = tmp_path / 'config.yaml'
    config.write_text('repos:\n- repo: local\n  hooks:\n  - id: other-hook\n', encoding='utf-8')
    command = [sys.executable, '-I', str(platform / 'scripts/verify-setup-hooks.py'),
               'pre-commit', 'starter', str(config)]
    result = run(command, tmp_path, os.environ.copy())
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'Required hook missing: template-specific-hook' in result.stdout
    shutil.copyfile(template, config)
    assert run(command, tmp_path, os.environ.copy()).returncode == 0
