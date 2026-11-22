"""Hook messages must describe what the exit contract does (issues 154 and 162)."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from .tool_helpers import application

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('opt_in', [False, True])
@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('hook,filename', [('semgrep-csharp', 'App.cs'), ('semgrep-typescript', 'app.ts')])
def test_semgrep_error_is_never_reported_as_a_pass(tmp_path, hook, filename, shell, opt_in):
    executable = shutil.which('bash' if shell == 'sh' else 'pwsh')
    if not executable:
        pytest.skip('Shell unavailable')
    consumer = tmp_path / 'consumer'
    consumer.mkdir()
    subprocess.run(['git', 'init', '-q', str(consumer)], check=True)
    (consumer / filename).write_text('x\n', encoding='utf-8')
    subprocess.run(['git', '-C', str(consumer), 'add', filename], check=True)
    application(tmp_path / 'tools', 'semgrep', 'import sys\nsys.exit(2)\n')
    env = dict(os.environ, SCAN_HOOK_ID=hook, PATH=str(tmp_path / 'tools') + os.pathsep + os.environ['PATH'])
    env.pop('SCAN_ALLOW_TOOL_ERRORS', None)
    if opt_in:
        env['SCAN_ALLOW_TOOL_ERRORS'] = '1'
    command = [executable] if shell == 'sh' else [executable, '-NoProfile', '-File']
    result = subprocess.run([*command, str(ROOT / f'hooks/{hook}.{shell}')], cwd=consumer, env=env,
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
    message = result.stdout + result.stderr
    assert result.returncode == (0 if opt_in else 1), message
    assert 'PASS' not in message
    if opt_in:
        assert 'not a clean scan' in message


def test_fail_open_is_named_only_for_the_opt_in_and_deliberate_skips():
    allowed = ('explicit local fail-open opt-in', 'allowing push (fail-open)')
    wrong = []
    for path in sorted((ROOT / 'hooks').rglob('*')):
        if path.suffix not in ('.sh', '.ps1'):
            continue
        for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
            if 'fail-open' in line and not any(phrase in line for phrase in allowed):
                wrong.append(f'{path.name}:{number}')
    assert wrong == []
