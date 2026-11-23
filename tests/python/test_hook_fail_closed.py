"""A scanner crash or a missing exit code must block the PowerShell hooks."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
CRASH_HOOKS = ['trivy-secrets', 'trivy-iac-critical', 'trivy-iac-full', 'checkov', 'checkov-strict',
               'snyk-iac', 'tflint']

# Linux cannot report a negative status, so the test replaces the scanner lookup in a copy of the
# library with a function that sets the status Windows reports.
FAKE_SCANNER = '''
function Invoke-FakeScanner {
    if ($args -contains '--init' -or $args -contains 'whoami') { $global:LASTEXITCODE = 0; return }
    $global:LASTEXITCODE = if ($env:FAKE_STATUS -eq 'null') { $null } else { [int]$env:FAKE_STATUS }
}
function Test-ToolAvailable { return 'Invoke-FakeScanner' }
'''


@pytest.fixture
def consumer(tmp_path):
    folder = tmp_path / 'consumer'
    folder.mkdir()
    subprocess.run(['git', 'init', '-q', str(folder)], check=True)
    (folder / 'main.tf').write_text('# fixture\n', encoding='utf-8')
    subprocess.run(['git', '-C', str(folder), 'add', 'main.tf'], check=True)
    return folder


def selected(tmp_path, **extra):
    manifest = tmp_path / 'paths'
    manifest.write_bytes(b'main.tf\0')
    env = dict(os.environ, SCAN_PUSH_SNAPSHOT='1', SCAN_PUSH_FILES=str(manifest), SCAN_HOOK_ID='fail-closed')
    env.pop('SCAN_ALLOW_TOOL_ERRORS', None)
    env.update(extra)
    return env


def run(shell, hook, consumer, env):
    executable = shutil.which('bash' if shell == 'sh' else 'pwsh')
    if not executable:
        pytest.skip('Shell unavailable')
    command = [executable] if shell == 'sh' else [executable, '-NoProfile', '-File']
    return subprocess.run([*command, str(hook)], cwd=consumer, env=env, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=180)


@pytest.mark.parametrize('status,opt_in,expected', [
    ('-1073741819', False, 1),
    ('-1', False, 1),
    ('null', False, 1),
    ('-1073741819', True, 0),
    ('0', False, 0),
])
@pytest.mark.parametrize('hook', CRASH_HOOKS)
def test_unknown_exit_status_is_an_incomplete_scan(tmp_path, consumer, hook, status, opt_in, expected):
    hooks = tmp_path / 'package' / 'hooks'
    shutil.copytree(ROOT / 'hooks', hooks)
    with (hooks / 'lib/common.ps1').open('a', encoding='utf-8') as library:
        library.write(FAKE_SCANNER)
    config = tmp_path / 'trusted.hcl'
    config.write_text('# fixture\n', encoding='utf-8')
    env = selected(tmp_path, FAKE_STATUS=status, SNYK_TOKEN='fixture-token',
                   SCAN_TFLINT_CONFIG=str(config), SCAN_TFLINT_PLUGIN_DIR=str(tmp_path / 'plugins'))
    if hook == 'trivy-iac-critical':
        env['SCAN_INDEX_SNAPSHOT'] = '1'
    if opt_in:
        env['SCAN_ALLOW_TOOL_ERRORS'] = '1'
    result = run('ps1', hooks / f'{hook}.ps1', consumer, env)
    message = result.stdout + result.stderr
    assert result.returncode == expected, message
    if expected:
        assert 'PASS' not in message
        assert 'Tool error' in message
    elif opt_in:
        assert 'explicit local fail-open opt-in' in message
