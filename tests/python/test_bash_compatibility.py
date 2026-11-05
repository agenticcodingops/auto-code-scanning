"""Shell libraries reject unsupported Bash before parsing newer syntax."""
from pathlib import Path
import re
import subprocess

import pytest

from .test_autofix_file_guard import bash_executable

ROOT = Path(__file__).resolve().parents[2]


def unsafe_conditional_extglobs(source):
    # Ignore comments and quoted/escaped RHS text, which is a literal pattern.
    source = re.sub(r'^\s*#.*$', '', source, flags=re.MULTILINE)
    if re.search(r'\bshopt\s+-s\s+[^;\n]*\bextglob\b', source):
        return []
    found = []
    word = r'''(?:[^\s"'\\]|\\.|"(?:\\.|[^"\\])*"|'[^']*')+'''
    for conditional in re.finditer(r'\[\[(.*?)\]\]', source, re.DOTALL):
        for comparison in re.finditer(r'(?:==|!=)\s*(' + word + ')', conditional[1]):
            unquoted = re.sub(r'''"(?:\\.|[^"\\])*"|'[^']*'|\\.''', '', comparison[1])
            if re.search(r'[@!+*?]\(', unquoted):
                found.append(comparison[0])
    return found


def test_hook_and_script_conditionals_do_not_require_implicit_extglob():
    failures = []
    for folder in ('hooks', 'scripts'):
        for path in sorted((ROOT / folder).rglob('*.sh')):
            for pattern in unsafe_conditional_extglobs(path.read_text(encoding='utf-8')):
                failures.append(f'{path.relative_to(ROOT)}: {pattern}')
    assert not failures, '\n'.join(failures)


@pytest.mark.parametrize('operator', ['==', '!='])
@pytest.mark.parametrize('prefix', ['@', '!', '+', '*', '?'])
def test_extglob_guard_detects_each_pattern(operator, prefix):
    assert unsafe_conditional_extglobs(f'[[ "$value" {operator}\n prefix{prefix}(a|b) ]]')


@pytest.mark.parametrize('source', [
    'shopt -s extglob\n[[ "$value" == @(a|b) ]]',
    'shopt -s nullglob extglob\n[[ "$value" != @(a|b) ]]',
    '# [[ "$value" == @(a|b) ]]',
    '[[ "$value" == "@(a|b)" ]]',
    "[[ \"$value\" != '@(a|b)' ]]",
    r'[[ "$value" == @\(a\|b\) ]]',
    'case "$value" in a*|b*) : ;; esac',
])
def test_extglob_guard_allows_explicit_enablement_and_literal_patterns(source):
    assert not unsafe_conditional_extglobs(source)


@pytest.mark.parametrize('major,minor,status', [(3, 2, 1), (4, 3, 1), (4, 4, 0), (5, 0, 0)])
def test_common_bash_version_floor(tmp_path, major, minor, status):
    bash = bash_executable()
    if not bash:
        pytest.skip('bash unavailable')
    for name in ('common.sh', 'tool-paths.sh'):
        (tmp_path / name).write_text((ROOT / 'hooks/lib' / name).read_text(encoding='utf-8'),
                                     encoding='utf-8', newline='\n')
    result = subprocess.run([bash, '-c',
        f'source "{tmp_path.as_posix()}/common.sh"; _scan_bash_supported {major} {minor}'],
        cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode == status, result.stdout + result.stderr
