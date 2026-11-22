"""ESLint and Prettier block a missing working_dir or runner as an incomplete scan.

MAIN's exit code is written down for every cell. The only cells allowed to differ
from it are a missing working_dir with a matching staged file, and trusted-repository
mode without a runner, both without SCAN_ALLOW_TOOL_ERRORS=1.
"""
from collections import namedtuple
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / 'hooks'
TOOLS = ('eslint', 'prettier')
SHELLS = ('sh', 'ps1')
EXTENSIONS = {'eslint': ('.ts',), 'prettier': ('.ts', '.md')}
# The bound covers a whole batch of cells on a busy machine.
TIMEOUT = 2400

INSIDE = ('mobile/app.ts', 'other/other.ts')
OUTSIDE = ('other/other.ts',)
INDEX = None  # the real index, which holds only gone/app.ts

# exists: the directory exists, perhaps spelt differently.
# selects: where main's prefix filter selects a file ('all', 'none', a shell or a hook).
# warns: an existing directory holds a staged file that the prefix filter cannot select.
Scenario = namedtuple('Scenario', 'value staged exists selects warns', defaults=(False,))
SCENARIOS = {
    'default': Scenario(None, INSIDE, True, 'all'),
    'empty': Scenario('', INSIDE, True, 'all'),
    'valid': Scenario('mobile', INSIDE, True, 'all'),
    'slash': Scenario('mobile/', INSIDE, True, 'all'),
    'backslash': Scenario('mobile\\', INSIDE, True, 'ps1', True),
    'two slashes': Scenario('mobile//', INSIDE, True, 'ps1', True),
    'padded': Scenario(' mobile ', INSIDE, True, 'ps1', True),
    'blank': Scenario(' ', INSIDE, True, 'eslint.ps1', True),
    'dot slash root': Scenario('./', INSIDE, True, 'none', True),
    'dot slash': Scenario('./mobile', INSIDE, True, 'none', True),
    'dot backslash': Scenario('.\\mobile', INSIDE, True, 'none', True),
    'case': Scenario('MOBILE', INSIDE, True, 'none', True),
    'absolute': Scenario('{repo}/mobile', INSIDE, True, 'none', True),
    'valid, files outside': Scenario('mobile', OUTSIDE, True, 'none'),
    'dot slash, files outside': Scenario('./mobile', OUTSIDE, True, 'none'),
    'case, files outside': Scenario('MOBILE', OUTSIDE, True, 'none'),
    'non-ASCII, files outside': Scenario('café-€', OUTSIDE, True, 'none'),
    'typo': Scenario('moble', INSIDE, False, 'none'),
    'typo below another case': Scenario('MOBILE/nope', INSIDE, False, 'none'),
    'typo at filesystem root': Scenario('/mobile-does-not-exist', INSIDE, False, 'none'),
    'removed': Scenario('gone', INDEX, False, 'all'),
    'removed, files outside': Scenario('gone', OUTSIDE, False, 'none'),
    'file': Scenario('afile', ('afile/app.ts',), False, 'all'),
    'file, files outside': Scenario('afile', OUTSIDE, False, 'none'),
    'typo, only Markdown': Scenario('moble', ('notes.md',), False, 'none'),
    'typo, nothing matching': Scenario('moble', ('main.tf',), False, 'none'),
}
# The runner matters only for a selected file, so the other modes use a subset.
MODES = {
    'trusted': tuple(SCENARIOS),
    'unprovisioned': ('default', 'typo', 'removed', 'backslash'),
    'runner': ('default', 'typo', 'removed', 'file', 'slash'),
    'no-runner': ('default', 'valid', 'backslash', 'blank', 'case', 'valid, files outside',
                  'typo', 'removed', 'typo, nothing matching'),
    'tool-error': ('default', 'typo', 'removed'),
}
Result = namedtuple('Result', 'code output trace')


def selects(scenario, tool, shell):
    return scenario.selects in ('all', shell, f'{tool}.{shell}')


def matches(scenario, tool):
    return scenario.staged is INDEX or any(name.endswith(EXTENSIONS[tool]) for name in scenario.staged)


def main_exit(scenario, tool, shell, mode, allowed):
    """What these hooks returned before the two fail-open paths were closed."""
    if not selects(scenario, tool, shell):
        return 0
    if not scenario.exists:
        # PowerShell resolved the trusted tool before it looked at the directory.
        return int(shell == 'ps1' and mode == 'unprovisioned')
    if mode == 'tool-error':
        return int(not (tool == 'eslint' and allowed))
    return int(mode == 'unprovisioned')


def incomplete(scenario, tool, shell, mode):
    if not scenario.exists:
        return 'working_dir' if matches(scenario, tool) else None
    return 'runner' if mode == 'no-runner' and selects(scenario, tool, shell) else None


def expected_exit(scenario, tool, shell, mode, allowed):
    if not allowed and incomplete(scenario, tool, shell, mode):
        return 1
    return main_exit(scenario, tool, shell, mode, allowed)


def interpreter(shell):
    found = shutil.which('bash' if shell == 'sh' else 'pwsh')
    if not found:
        pytest.skip('shell unavailable')
    return found


def path_without_runners(folder):
    """PATH with Python and the system tools, but no eslint, prettier or npx."""
    banned = re.compile(r'(eslint|prettier|npx)(\.(cmd|bat|exe|ps1))?', re.IGNORECASE)
    kept = []
    for number, entry in enumerate([str(Path(sys.executable).parent), *os.environ['PATH'].split(os.pathsep)]):
        try:
            names = os.listdir(entry or '.')
        except OSError:
            continue
        if not any(banned.fullmatch(name) for name in names):
            kept.append(entry)
        elif os.name != 'nt':
            # A system bin directory can hold npx next to git: mirror the rest of it.
            mirror = folder / f'path-{number}'
            mirror.mkdir(parents=True)
            for name in names:
                if not banned.fullmatch(name):
                    (mirror / name).symlink_to(Path(entry).resolve() / name)
            kept.append(str(mirror))
    return os.pathsep.join(kept)


def make_repo(tmp_path):
    repo = tmp_path / 'repo'
    for name in (*INSIDE, 'gone/app.ts', 'café-€/keep.txt'):
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text('fixture\n', encoding='utf-8')
    (repo / 'afile').write_text('not a directory\n', encoding='utf-8')
    subprocess.run(['git', 'init', '-q'], cwd=repo, check=True, timeout=120)
    subprocess.run(['git', 'add', 'gone/app.ts'], cwd=repo, check=True, timeout=120)
    shutil.rmtree(repo / 'gone')
    return repo


def make_environment(tmp_path, tool, shell, mode):
    env = {key: value for key, value in os.environ.items() if not key.startswith(('SCAN_', 'GIT_'))}
    env.update(SCAN_HOOK_ID=tool, PATH=path_without_runners(tmp_path / 'mirrors'))
    if mode == 'no-runner':
        env['SCAN_TRUST_REPO_CODE'] = '1'
    if mode in ('unprovisioned', 'no-runner'):
        return env
    tools = tmp_path / 'tools'
    tools.mkdir()
    code = 2 if mode == 'tool-error' else 0
    binary = tools / tool
    binary.write_text(f'#!/bin/sh\necho "$*" >> "$APP_TRACE"\nexit {code}\n', encoding='utf-8', newline='\n')
    binary.chmod(0o755)
    (tools / f'{tool}.cmd').write_text(f'@echo %* >> "%APP_TRACE%"\n@exit /b {code}\n', encoding='utf-8')
    if mode == 'runner':
        env.update(SCAN_TRUST_REPO_CODE='1', PATH=str(tools) + os.pathsep + env['PATH'])
        return env
    config = tools / 'trusted.config'
    config.write_text('{}\n', encoding='utf-8')
    if shell == 'ps1' and os.name == 'nt':
        binary = tools / f'{tool}.cmd'
    name = f'SCAN_{tool.upper()}'
    env.update({f'{name}_BIN': str(binary), f'{name}_CONFIG': str(config)})
    return env


def run_batch(tmp_path, tool, shell, mode, cells, hooks=HOOKS):
    """Run every cell of one hook in one driver process, sharing one repository."""
    program = interpreter(shell)
    repo = make_repo(tmp_path)
    env = make_environment(tmp_path, tool, shell, mode)
    work = tmp_path / 'cells'
    work.mkdir()
    hook = (hooks / f'{tool}.{shell}').as_posix()
    quote = shlex.quote if shell == 'sh' else lambda text: "'" + text.replace("'", "''") + "'"
    lines = []
    for number, (name, allowed) in enumerate(cells):
        scenario = SCENARIOS[name]
        base = work / str(number)
        values = dict(SCAN_ALLOW_TOOL_ERRORS='1' if allowed else '0', SCAN_PUSH_FILES='',
                      SCAN_CONFIG_FILE=base.with_suffix('.yaml').as_posix(),
                      APP_TRACE=str(base.with_suffix('.trace')))
        if scenario.value is not None:
            value = scenario.value.replace('{repo}', repo.as_posix())
            config = {'languages': {'typescript': {'build': {'working_dir': value}}}}
            base.with_suffix('.yaml').write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
        if scenario.staged is not INDEX:
            manifest = base.with_suffix('.paths')
            manifest.write_bytes(b''.join(path.encode() + b'\0' for path in scenario.staged))
            values['SCAN_PUSH_FILES'] = manifest.as_posix()
        output, code = (quote(base.with_suffix(suffix).as_posix()) for suffix in ('.out', '.code'))
        if shell == 'sh':
            settings = ' '.join(f'{key}={quote(value)}' for key, value in values.items())
            lines += [f'{settings} bash {quote(hook)} > {output} 2>&1', f'echo $? > {code}']
        else:
            lines += [f'$env:{key} = {quote(value)}' for key, value in values.items()]
            # The library guards against a second load; every cell needs a fresh one.
            lines += ['$global:_CommonPS1Loaded = $false', '$global:LASTEXITCODE = 0',
                      f'try {{ & {quote(hook)} *> {output}; $status = $LASTEXITCODE }}',
                      f'catch {{ "$_" >> {output}; $status = 1 }}',
                      f'[IO.File]::WriteAllText({code}, "$status")']
    driver = tmp_path / f'driver.{shell}'
    driver.write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    options = [] if shell == 'sh' else ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File']
    batch = subprocess.run([program, *options, str(driver)], cwd=repo, env=env,
                           capture_output=True, timeout=TIMEOUT)
    assert batch.returncode == 0, batch.stdout + batch.stderr

    def read(path):
        return path.read_text(encoding='utf-8', errors='replace') if path.exists() else ''

    results = {}
    for number, cell in enumerate(cells):
        base = work / str(number)
        results[cell] = Result(int(read(base.with_suffix('.code'))),
                               read(base.with_suffix('.out')), read(base.with_suffix('.trace')))
    return results


def flat(text):
    """Ignore the colours and line wrapping of PowerShell's error and warning views."""
    return re.sub(r'\x1b\[[0-9;]*m|[\s|]', '', text)


def problems(scenario, tool, shell, mode, allowed, result):
    expected = expected_exit(scenario, tool, shell, mode, allowed)
    if result.code != expected:
        yield f'exit {result.code}, expected {expected}'
    selected = selects(scenario, tool, shell)
    ran = selected and scenario.exists and mode in ('trusted', 'runner', 'tool-error')
    if bool(result.trace) != ran:
        yield f'runner called: {bool(result.trace)}, expected {ran}'
    if ran:
        root = scenario.value in (None, '.', '', ' ')
        if 'app.ts' not in result.trace or ('other.ts' in result.trace) != root:
            yield f'selection changed: {result.trace!r}'

    output = flat(result.output)
    reason = incomplete(scenario, tool, shell, mode)
    if reason and allowed:
        # PowerShell still refuses an unprovisioned tool, after the warning.
        if 'WARNING' not in output or 'SCAN_ALLOW_TOOL_ERRORS=1' not in output:
            yield 'the opt-in is not announced'
    elif reason:
        if 'scanincomplete' not in output or 'PASS' in output:
            yield 'not reported as an incomplete scan'
        if 'SCAN_ALLOW_TOOL_ERRORS' in output:
            yield 'offers the opt-in as the remedy'
        if reason == 'working_dir':
            wanted = [f"working_dir'{flat(scenario.value)}'", 'Fixlanguages.typescript.build.working_dir']
        else:
            wanted = [f'Provisionthe{tool}runner', 'node_modules']
        for text in wanted:
            if text not in output:
                yield f'message lacks {text}'
    elif scenario.warns and not selected:
        if 'WARNING' not in output or 'wasselected' not in output or 'PASS' in output:
            yield 'silent about a value that selects nothing'
        if '{repo}' not in scenario.value and f"'{flat(scenario.value)}'" not in output:
            yield 'does not name the configured value'
    elif not selected:
        if 'WARNING' in output or 'PASS' not in output:
            yield 'alarm for a normal pass'


@pytest.mark.parametrize('allowed', [False, True], ids=['default', 'opt-in'])
@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('shell', SHELLS)
@pytest.mark.parametrize('tool', TOOLS)
def test_only_approved_incomplete_scans_change_the_exit_code(tmp_path, tool, shell, mode, allowed):
    cells = [(name, allowed) for name in MODES[mode]]
    results = run_batch(tmp_path, tool, shell, mode, cells)
    failures = [f'{name}: {problem}\n  {results[name, allowed].output.strip()[:600]}'
                for name in MODES[mode]
                for problem in problems(SCENARIOS[name], tool, shell, mode, allowed, results[name, allowed])]
    assert not failures, '\n'.join(failures)


@pytest.mark.parametrize('shell', SHELLS)
@pytest.mark.parametrize('tool', TOOLS)
def test_removed_working_dir_blocks_as_a_process(tmp_path, tool, shell):
    """The batch driver catches errors, so check the status that a Git hook receives."""
    program = interpreter(shell)
    repo = make_repo(tmp_path)
    (repo / 'scan-config.yaml').write_text('languages: {typescript: {build: {working_dir: gone}}}\n',
                                          encoding='utf-8')
    env = make_environment(tmp_path, tool, shell, 'trusted')
    options = [] if shell == 'sh' else ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File']
    result = subprocess.run([program, *options, (HOOKS / f'{tool}.{shell}').as_posix()],
                            cwd=repo, env=env, capture_output=True, timeout=300)
    assert result.returncode == 1, result.stdout + result.stderr
