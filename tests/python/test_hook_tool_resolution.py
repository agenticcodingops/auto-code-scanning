"""Tools are verified before probes and invoked through their frozen paths."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from .test_content_boundaries import link_or_skip
from .test_local_scanner_trust import consumer, git, package
from .tool_helpers import application
from .baseline_helpers import scanner_stub

ROOT = Path(__file__).resolve().parents[2]


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def run_library(package, shell, command, cwd, env):
    executable = shutil.which('bash' if shell == 'sh' else 'pwsh')
    if not executable:
        pytest.skip('shell unavailable')
    common = (package / f'hooks/lib/common.{shell}').as_posix()
    prefix = f"source {quote(common)}; " if shell == 'sh' else f"$ErrorActionPreference='Stop'; . {quote(common)}; "
    return subprocess.run([executable, *(['-c'] if shell == 'sh' else ['-NoProfile', '-Command']),
                           prefix + command], cwd=cwd, env=env, capture_output=True,
                          text=True, timeout=45)


def stub(folder, name, trace):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (name + ('.cmd' if os.name == 'nt' else ''))
    path.write_text(f'@echo invoked>>"{trace}"\n@exit /b 0\n' if os.name == 'nt' else
                    f'#!/bin/sh\necho invoked >> {quote(trace)}\nexit 0\n', encoding='utf-8', newline='\n')
    path.chmod(0o755)
    # Bash uses the extensionless entry; PowerShell uses PATHEXT on Windows.
    if os.name == 'nt':
        bash_path = folder / name
        bash_path.write_text(f'#!/bin/sh\necho invoked >> {quote(trace.as_posix())}\nexit 0\n',
                             encoding='utf-8', newline='\n')
        bash_path.chmod(0o755)
    return path


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('snapshot', ['none', 'index', 'push'])
def test_checkout_python_is_rejected_before_probe(consumer, package, tmp_path, shell, snapshot):
    trace = tmp_path / 'trace'
    binary = consumer / 'bin'
    stub(binary, 'python', trace)
    env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ['PATH'])
    cwd = consumer
    if snapshot != 'none':
        cwd = tmp_path / 'snapshot'
        cwd.mkdir()
        env.update({f'SCAN_{snapshot.upper()}_SNAPSHOT': '1', 'SCAN_CONSUMER_ROOT': str(consumer)})
    command = 'find_python' if shell == 'sh' else 'Find-WorkingPython'
    result = run_library(package, shell, command, cwd, env)
    assert result.returncode != 0, result.stdout + result.stderr
    assert not trace.exists(), 'untrusted interpreter executed during capability probe'
    assert 'outside' in result.stderr


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('tool', ['checkov', 'trivy', 'tflint', 'semgrep', 'gitleaks', 'snyk', 'dotnet', 'sqlfluff'])
def test_scanner_function_cannot_override_verified_application(consumer, package, tmp_path, shell, tool):
    trace = tmp_path / 'trace'
    binary = tmp_path / 'external bin'
    stub(binary, tool, trace)
    env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ['PATH'])
    if shell == 'sh':
        command = (f"{tool}() {{ echo SHADOW >&2; return 9; }}; "
                   f"require_tool {tool}; \"$SCAN_TOOL\"")
    else:
        command = (f"function {tool} {{ throw 'SHADOW' }}; "
                   f"$scanner = Test-ToolAvailable {tool}; & $scanner")
    result = run_library(package, shell, command, consumer, env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert trace.read_text().strip() == 'invoked'
    assert 'SHADOW' not in result.stdout + result.stderr


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('location', ['inside', 'external-link-inside', 'inside-link-external'])
def test_scanners_check_invoked_and_canonical_paths(consumer, package, tmp_path, shell, location):
    trace = tmp_path / 'trace'
    inside, outside = consumer / 'bin', tmp_path / 'external bin'
    target = inside if location != 'inside-link-external' else outside
    stub(target, 'trivy', trace)
    binary = target
    if location != 'inside':
        binary = outside if location == 'external-link-inside' else inside
        link_or_skip(target, binary, True)
    env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ['PATH'])
    command = 'require_tool trivy' if shell == 'sh' else 'Test-ToolAvailable trivy'
    result = run_library(package, shell, command, consumer, env)
    assert result.returncode != 0, result.stdout + result.stderr
    assert 'outside' in result.stderr
    assert not trace.exists()


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
def test_external_virtual_environment_keeps_its_invoked_identity(consumer, package, tmp_path, shell):
    venv = tmp_path / 'external environment'
    subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(venv)], check=True)
    binary = venv / ('Scripts' if os.name == 'nt' else 'bin')
    env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ['PATH'])
    command = ('py="$(find_python)"; "$py" -E -P -c "import sys; print(sys.prefix)"' if shell == 'sh' else
               '$py = Find-WorkingPython; & $py -E -P -c "import sys; print(sys.prefix)"')
    result = run_library(package, shell, command, consumer, env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert Path(result.stdout.strip()).resolve() == venv.resolve()


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('name,tool', [
    ('checkov', 'checkov'), ('checkov-strict', 'checkov'),
    ('trivy-iac-critical', 'trivy'), ('trivy-iac-full', 'trivy'), ('trivy-secrets', 'trivy'),
    ('tflint', 'tflint'), ('semgrep-csharp', 'semgrep'), ('semgrep-typescript', 'semgrep'),
    ('gitleaks', 'gitleaks'), ('snyk-iac', 'snyk'), ('dotnet-build', 'dotnet'),
    ('dotnet-format', 'dotnet'), ('sqlfluff', 'sqlfluff'),
])
def test_each_wrapper_executes_verified_scanner_despite_function_shadow(
        consumer, package, tmp_path, shell, name, tool):
    for filename in ('App.cs', 'app.ts', 'query.sql', 'main.tf', 'App.sln'):
        (consumer / filename).write_text('fixture\n', encoding='utf-8')
    git(consumer, 'add', '.')
    binary = tmp_path / 'external bin'
    binary.mkdir()
    trace = tmp_path / 'trace'
    probe = binary / 'probe.py'
    probe.write_text('import json,os,pathlib,sys\n'
                     'with open(os.environ["TOOL_TRACE"],"a") as f: f.write("invoked\\n")\n'
                     'if "--output" in sys.argv:\n'
                     ' pathlib.Path(sys.argv[sys.argv.index("--output")+1]).write_text(\'{"results":[]}\')\n'
                     'print(os.environ["TOOL_REPORT"])\n', encoding='utf-8')
    (binary / tool).write_text(f'#!/bin/sh\nexec "{Path(sys.executable).as_posix()}" "{probe.as_posix()}" "$@"\n',
                               encoding='utf-8', newline='\n')
    (binary / tool).chmod(0o755)
    (binary / (tool + '.cmd')).write_text(f'@"{sys.executable}" "{probe}" %*\n', encoding='utf-8')
    config = tmp_path / 'trusted.hcl'
    config.write_text('# trusted\n', encoding='utf-8')
    plugins = tmp_path / 'plugins'
    plugins.mkdir()
    report = {'trivy': '{"Results":[]}', 'checkov': '{"results":{"failed_checks":[]}}',
              'gitleaks': '[]'}.get(tool, '{}')
    env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ['PATH'],
               TOOL_TRACE=str(trace), TOOL_REPORT=report, SCAN_INDEX_SNAPSHOT='1',
               SCAN_PUSH_SNAPSHOT='1', SCAN_TFLINT_CONFIG=str(config), SCAN_TFLINT_PLUGIN_DIR=str(plugins))
    wrapper = package / f'hooks/{name}.{shell}'
    command = (f"{tool}() {{ echo SHADOW >&2; return 9; }}; source {quote(wrapper.as_posix())}" if shell == 'sh' else
               f"function {tool} {{ throw 'SHADOW' }}; & {quote(wrapper)}")
    result = run_library(package, shell, command, consumer, env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert trace.exists(), result.stdout + result.stderr
    assert set(trace.read_text().splitlines()) == {'invoked'}
    assert 'SHADOW' not in result.stdout + result.stderr


@pytest.mark.skipif(os.name != 'nt', reason='Windows launcher selection')
@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('scope', ['checkout', 'external', 'unknown', 'default-checkout', 'default-external', 'ambiguous'])
def test_hook_py_only_checks_selection_without_running_launcher(consumer, package, tmp_path, shell, scope):
    trace = tmp_path / 'trace'
    binary = tmp_path / 'launcher'
    stub(binary, 'py', trace)
    env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ['PATH'])
    env.pop('VIRTUAL_ENV', None)
    venv = (consumer if 'checkout' in scope else tmp_path) / 'environment'
    if scope not in ('unknown', 'ambiguous'):
        subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(venv)], check=True)
    if scope in ('checkout', 'external'):
        env['VIRTUAL_ENV'] = str(venv)
    else:
        selected = str(venv / 'Scripts/python.exe')
        listing = (' -V:3.13 * ' + selected if scope.startswith('default-') else
                   ' -V:3.13 * ' + sys.executable + '\n -V:3.12 * ' + sys.executable if scope == 'ambiguous' else '')
        # Listing metadata is safe; the marker records interpreter/probe execution.
        application(binary, 'py', 'import pathlib,sys\n'
                    f'if sys.argv[1:] == ["-0p"]: print({listing!r}); sys.exit(0)\n'
                    f'pathlib.Path({str(trace)!r}).touch()\n')
    if shell == 'sh':
        # Hide other real interpreters while retaining standard shell utilities.
        command = ('type() { case "${*: -1}" in python|python3) return 1;; '
                   '*) builtin type "$@";; esac; }; '
                   'py="$(find_python)" || exit 1; "$py" -E -P -c "import sys; print(sys.prefix)"')
    else:
        command = ('function Get-Command { param($Name, $CommandType, $ErrorAction) '
                   'if ($Name -notin @("python", "python3")) { Microsoft.PowerShell.Core\\Get-Command @PSBoundParameters } }; '
                   '$py=Find-WorkingPython; & $py -E -P -c "import sys; print(sys.prefix)"')
    result = run_library(package, shell, command, consumer, env)
    assert not trace.exists(), 'launcher was probed before checking its interpreter'
    if scope in ('external', 'default-external'):
        assert result.returncode == 0, result.stdout + result.stderr
        assert Path(result.stdout.strip()).resolve() == venv.resolve()
    else:
        assert result.returncode != 0, result.stdout + result.stderr
        assert ('outside' if 'checkout' in scope else 'Cannot verify py selection') in result.stderr


def test_gitleaks_report_parser_never_probes_checkout_python3(consumer, package, tmp_path):
    (consumer / 'file.txt').write_text('fixture\n')
    git(consumer, 'add', '.')
    trace = tmp_path / 'python3-trace'
    inside = consumer / 'bin'
    stub(inside, 'python3', trace)
    outside = tmp_path / 'scanner'
    application(outside, 'gitleaks', 'print("[]")\n')
    env = dict(os.environ, PATH=str(inside)+os.pathsep+str(outside)+os.pathsep+os.environ['PATH'])
    result = run_library(package, 'sh', f'source {quote((package / "hooks/gitleaks.sh").as_posix())}',
                         consumer, env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not trace.exists(), 'report parser probed an unchecked interpreter'


def test_baseline_uses_resolver_from_vendored_hooks(consumer, package, tmp_path):
    pwsh = shutil.which('pwsh')
    if not pwsh:
        pytest.skip('PowerShell unavailable')
    # Onboarding vendors the hook library and baseline script, not setup helpers.
    (package / 'scripts/setup-paths.ps1').unlink()
    (consumer / 'main.tf').write_text('# fixture\n')
    git(consumer, 'add', '.')
    git(consumer, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test',
        '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'fixture')
    env = dict(os.environ)
    scanner_stub(tmp_path / 'scanner', 'checkov', env)
    result = subprocess.run([pwsh, '-NoProfile', '-File',
                             str(package / 'scripts/create-baseline.ps1'), '-Tool', 'checkov',
                             '-CloudProvider', 'aws', '-Force'], cwd=consumer, env=env,
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (consumer / '.scan-baseline/baseline.json').exists()


@pytest.mark.parametrize('shell', ['pwsh', 'powershell'])
@pytest.mark.parametrize('inside', [False, True])
def test_verified_tool_keeps_boundary_when_git_checkout_discovery_fails(package, tmp_path, shell, inside):
    executable = shutil.which(shell)
    if not executable:
        pytest.skip(shell + ' unavailable')
    cwd = tmp_path / 'scanned directory'
    cwd.mkdir()
    trace = tmp_path / 'trace'
    tool = stub((cwd if inside else tmp_path) / 'bin', 'trivy', trace)
    command = (f'. {quote(package / "hooks/lib/common.ps1")}; '
               f'. {quote(package / "scripts/setup-paths.ps1")}; '
               f'Resolve-VerifiedTool -Name {quote(tool)} -Label Fixture')
    result = subprocess.run([executable, '-NoProfile', '-Command', command],
                            cwd=cwd, capture_output=True, text=True, timeout=45)
    assert not trace.exists()
    if inside:
        assert result.returncode != 0, result.stdout + result.stderr
        assert 'must resolve outside' in result.stderr
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert Path(result.stdout.strip()) == tool
        assert result.stderr == ''


@pytest.mark.parametrize('shell', ['pwsh', 'powershell'])
@pytest.mark.parametrize('inside', [False, True])
@pytest.mark.parametrize('target', ['missing', 'null-method'])
def test_python_skips_only_external_opaque_aliases(consumer, package, tmp_path, shell, inside, target):
    executable = shutil.which(shell)
    if not executable:
        pytest.skip(shell + ' unavailable')
    trace = tmp_path / 'trace'
    alias = stub((consumer if inside else tmp_path) / 'alias', 'python', trace)
    env = dict(os.environ, OPAQUE_ALIAS=str(alias), SAFE_PYTHON=sys.executable)
    command = (f'. {quote(package / "hooks/lib/common.ps1")}; '
               'function Get-Command { param($Name,$CommandType,$ErrorAction) '
               'if ($Name -eq "python") { [pscustomobject]@{Source=$env:OPAQUE_ALIAS} } '
               'elseif ($Name -eq "python3") { [pscustomobject]@{Source=$env:SAFE_PYTHON} } '
               'elseif ($Name -ne "py") { Microsoft.PowerShell.Core\\Get-Command @PSBoundParameters } }; '
               'function Get-Item { param($LiteralPath,[switch]$Force,$ErrorAction) '
               'if ($LiteralPath -eq $env:OPAQUE_ALIAS) { '
               '$item=[pscustomobject]@{Attributes=[IO.FileAttributes]::ReparsePoint;Target=@()}; '
               + ('$item | Add-Member ScriptMethod ResolveLinkTarget { param($final) return $null }; '
                  if target == 'null-method' else '') +
               '$item } else { Microsoft.PowerShell.Management\\Get-Item @PSBoundParameters } }; '
               '$py=Find-WorkingPython; if ($py) { Write-Output $py } else { exit 1 }')
    result = subprocess.run([executable, '-NoProfile', '-Command', command], cwd=consumer,
                            env=env, text=True, capture_output=True, timeout=60)
    assert not trace.exists(), 'Opaque alias was executed'
    if inside:
        assert result.returncode != 0, result.stdout + result.stderr
        assert 'must resolve outside' in result.stderr
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert Path(result.stdout.strip()) == Path(sys.executable)


@pytest.mark.parametrize('inside', [False, True])
def test_bash_converts_windows_path_before_deriving_invoked_parent(consumer, package, tmp_path, inside):
    trace = tmp_path / 'trace'
    tool = stub((consumer if inside else tmp_path) / 'bin', 'python', trace)
    raw = r'C:\external\python.exe'
    env = dict(os.environ, RAW_TOOL=raw, REAL_TOOL=tool.as_posix())
    command = ('real_cygpath="$(type -P cygpath || true)"; '
               'cygpath() { local p="${*: -1}"; [[ "$p" != "$RAW_TOOL" ]] || p="$REAL_TOOL"; '
               'if [[ -n "$real_cygpath" ]]; then "$real_cygpath" "$1" -- "$p"; else printf "%s\\n" "$p"; fi; }; '
               # Model a POSIX dirname implementation that treats backslashes literally.
               'dirname() { if [[ "${*: -1}" == "$RAW_TOOL" ]]; then printf ".\\n"; '
               'else command dirname "$@"; fi; }; verify_tool_path "$RAW_TOOL"')
    result = run_library(package, 'sh', command, consumer, env)
    assert not trace.exists()
    if inside:
        assert result.returncode != 0, result.stdout + result.stderr
        assert 'outside' in result.stderr
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.strip() == raw


@pytest.mark.parametrize('mode', ['default', 'venv', 'conversion-error'])
@pytest.mark.parametrize('inside', [False, True])
def test_cygwin_launcher_selection_uses_posix_interpreter_paths(consumer, package, tmp_path, mode, inside):
    trace = tmp_path / 'interpreter-trace'
    launcher_trace = tmp_path / 'launcher-trace'
    binary = tmp_path / 'launcher'
    actual = (consumer if inside else tmp_path) / 'environment' / 'effective-python'
    application(actual.parent, actual.name, 'import pathlib,sys\n'
                f'pathlib.Path({str(trace)!r}).touch()\n'
                'if sys.argv[-1] != "": print("EFFECTIVE_INTERPRETER")\n')
    raw = r'C:\fixture\python.exe'
    application(binary, 'py', 'import pathlib,sys\n'
                f'if sys.argv[1:] == ["-0p"]: print(" -V:3.13 * " + {raw!r}); sys.exit(0)\n'
                f'pathlib.Path({str(launcher_trace)!r}).touch()\n')
    env = dict(os.environ, PATH=str(binary)+os.pathsep+os.environ['PATH'], RAW_DEFAULT=raw,
               RAW_VENV=r'C:\fixture/Scripts/python.exe', REAL_INTERPRETER=actual.as_posix(),
               FAIL_CONVERSION='1' if mode == 'conversion-error' else '0')
    env.pop('VIRTUAL_ENV', None)
    if mode == 'venv':
        env['VIRTUAL_ENV'] = r'C:\fixture'
    command = ('OSTYPE=cygwin; real_cygpath="$(builtin type -P cygpath || true)"; '
               'type() { case "${*: -1}" in python|python3) return 1;; *) builtin type "$@";; esac; }; '
               'cygpath() { local p="${*: -1}"; '
               'if [[ "$p" == "$RAW_DEFAULT" || "$p" == "$RAW_VENV" ]]; then '
               '[[ "$1" != -u || "$FAIL_CONVERSION" != 1 ]] || return 1; p="$REAL_INTERPRETER"; fi; '
               'if [[ -n "$real_cygpath" ]]; then "$real_cygpath" "$1" -- "$p"; else printf "%s\\n" "$p"; fi; }; '
               'selected="$(find_python)" || exit 1; "$selected" -c inspect')
    result = run_library(package, 'sh', command, consumer, env)
    assert not launcher_trace.exists(), 'Launcher ran an interpreter probe'
    if mode == 'conversion-error':
        assert result.returncode != 0, result.stdout + result.stderr
        assert 'Cannot convert py interpreter path' in result.stderr
        assert not trace.exists()
    elif inside:
        assert result.returncode != 0, result.stdout + result.stderr
        assert 'outside' in result.stderr
        assert not trace.exists()
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.strip() == 'EFFECTIVE_INTERPRETER'
        assert trace.exists()


@pytest.mark.skipif(os.name != 'nt', reason='Windows launcher selection')
@pytest.mark.parametrize('scope', ['source', 'scan', 'external'])
@pytest.mark.parametrize('active', [True, False])
def test_baseline_py_only_verifies_effective_venv_before_execution(consumer, package, tmp_path, scope, active):
    scan = tmp_path / 'scan'
    scan.mkdir()
    venv = {'source': consumer / 'venv', 'scan': scan / 'venv',
            'external': tmp_path / 'external environment'}[scope]
    subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(venv)], check=True)
    tools = tmp_path / 'launcher'
    tools.mkdir()
    trace = tmp_path / 'launcher-trace'
    interpreter = venv / 'Scripts/python.exe'
    launcher = application(tools, 'py', 'import pathlib,subprocess,sys\n'
                           f'if sys.argv[1:] == ["-0p"]: print(" -V:3.13 * " + {str(interpreter)!r}); sys.exit(0)\n'
                           f'pathlib.Path({str(trace)!r}).touch()\n'
                           f'sys.exit(subprocess.call([{str(interpreter)!r}, *sys.argv[1:]]))\n')
    env = dict(os.environ, PY_ONLY=str(launcher))
    env.pop('VIRTUAL_ENV', None)
    if active:
        env['VIRTUAL_ENV'] = str(venv)
    command = (f'. {quote(package / "hooks/lib/common.ps1")}; '
               'function Get-Command { param($Name, $CommandType, $ErrorAction) '
               'if ($Name -eq "py") { [pscustomobject]@{ Source=$env:PY_ONLY } } '
               'elseif ($Name -notin @("python", "python3")) { Microsoft.PowerShell.Core\\Get-Command @PSBoundParameters } }; '
               f'$sourceRoot={quote(consumer)}; $TerraformDir={quote(scan)}; $scopedDirs=@(); '
               f'$text=Get-Content {quote(package / "scripts/create-baseline.ps1")} -Raw; '
               '$tokens=$null; $errors=$null; '
               '$ast=[Management.Automation.Language.Parser]::ParseInput($text,[ref]$tokens,[ref]$errors); '
               '$function=$ast.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq "Find-BaselinePython"},$true); '
               f'. {quote(package / "scripts/setup-paths.ps1")}; '
               '. ([scriptblock]::Create($function.Extent.Text)); '
               '$py=Find-BaselinePython; & $py -E -P -c "import sys; print(sys.prefix)"')
    result = subprocess.run([shutil.which('pwsh'), '-NoProfile', '-Command', command],
                            cwd=consumer, env=env, text=True, capture_output=True, timeout=60)
    assert not trace.exists(), 'launcher executed before its selected interpreter was verified'
    if scope == 'external':
        assert result.returncode == 0, result.stdout + result.stderr
        assert Path(result.stdout.strip()).resolve() == venv.resolve()
    else:
        assert result.returncode != 0, result.stdout + result.stderr
        assert 'outside' in result.stderr
