"""Shared hook paths preserve operand boundaries and scanner status."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import pytest
ROOT = Path(__file__).resolve().parents[2]

@pytest.fixture
def bash_common(tmp_path):
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash unavailable")
    common = tmp_path / "common.sh"
    common.write_text((ROOT / "hooks/lib/common.sh").read_text(), encoding="utf-8", newline="\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    # MSYS understands a forward-slash Windows absolute path in a shell string.
    return bash, f'source "{common.as_posix()}"; '


def test_bash_directory_paths_are_nul_delimited(tmp_path, bash_common):
    bash, prefix = bash_common
    (tmp_path / "-module.tf").write_text("# fixture\n")
    subprocess.run(["git", "add", "--", "-module.tf"], cwd=tmp_path, check=True)
    result = subprocess.run([bash, "-c", prefix + "detect_changed_dirs"], cwd=tmp_path, capture_output=True)
    assert result.returncode == 0
    assert result.stdout == b".\0"


def test_bash_staged_paths_are_nul_delimited(tmp_path, bash_common):
    bash, prefix = bash_common
    name = "module space.ts"
    (tmp_path / name).write_text("// fixture\n")
    subprocess.run(["git", "add", "--", name], cwd=tmp_path, check=True)
    result = subprocess.run([bash, "-c", prefix + "get_staged_files ts"], cwd=tmp_path, capture_output=True)
    assert result.stdout == name.encode() + b"\0"


def test_trivy_retry_preserves_findings_status(tmp_path, bash_common):
    bash, prefix = bash_common
    result = subprocess.run([bash, "-c", prefix +
        "fake_trivy() { printf '%s' '{\"Target\":\"database locked\"}'; return 1; }; "
        "run_trivy_with_retry fake_trivy"], cwd=tmp_path, capture_output=True)
    assert result.returncode == 1


def test_semgrep_paths_follow_operand_delimiter():
    for language in ("csharp", "typescript"):
        sh = (ROOT / f"hooks/semgrep-{language}.sh").read_text()
        ps = (ROOT / f"hooks/semgrep-{language}.ps1").read_text()
        assert 'semgrep_cmd+=(-- "${files[@]}")' in sh
        assert "$semgrepArgs += '--'" in ps


def test_powershell_reads_nul_paths_without_native_line_splitting(tmp_path):
    pwsh = shutil.which('pwsh')
    if not pwsh:
        pytest.skip('PowerShell unavailable')
    subprocess.run(['git', 'init', '-q'], cwd=tmp_path, check=True)
    names = ['module space.ts', 'module-\u00e9.ts', '-module.tf']
    for name in names:
        (tmp_path / name).write_text('// fixture\n')
    subprocess.run(['git', 'add', '--', *names], cwd=tmp_path, check=True)
    common = (ROOT / 'hooks/lib/common.ps1').as_posix()
    result = subprocess.run([pwsh, '-NoProfile', '-Command',
        f". '{common}'; @{{files=@(Get-StagedFiles -Extensions @('ts')); dirs=@(Get-ChangedDirs)}} | ConvertTo-Json -Compress"],
        cwd=tmp_path, capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert set(data['files']) == set(names[:2])
    assert data['dirs'] == ['.']


def test_distinct_git_directory_names_survive_ordinal_deduplication(tmp_path):
    pwsh = shutil.which('pwsh')
    if not pwsh:
        pytest.skip('PowerShell unavailable')
    subprocess.run(['git','init','-q'], cwd=tmp_path, check=True)
    common = (ROOT / 'hooks/lib/common.ps1').as_posix()
    command = f". '{common}'; function Get-ChangedFilesForDetect {{ @('Module/main.tf','module/main.tf',('caf'+[char]0xE9+'/main.tf'),('cafe'+[char]0x301+'/main.tf')) }}; @(Get-ChangedDirs) | ConvertTo-Json -Compress"
    result = subprocess.run([pwsh,'-NoProfile','-Command',command],cwd=tmp_path,capture_output=True,text=True,encoding='utf-8')
    assert result.returncode == 0, result.stderr
    assert len(json.loads(result.stdout)) == 4


def test_powershell_retry_preserves_findings_exit_status(tmp_path):
    pwsh = shutil.which('pwsh')
    if not pwsh:
        pytest.skip('PowerShell unavailable')
    common = (ROOT / 'hooks/lib/common.ps1').as_posix()
    result = subprocess.run([pwsh, '-NoProfile', '-Command',
        f". '{common}'; function trivy {{ $global:LASTEXITCODE=1; '{{\"Target\":\"database locked\"}}' }}; "
        "(Invoke-TrivyWithRetry -ArgumentList @('config', '--', '.')).ExitCode"],
        cwd=tmp_path, capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == '1'


@pytest.mark.parametrize('diagnostic', ['database locked', 'cache may be in use by another process'])
def test_bash_retries_exit_one_lock_diagnostics(tmp_path, bash_common, diagnostic):
    bash, prefix = bash_common
    result = subprocess.run([bash, '-c', prefix +
        f"sleep() {{ :; }}; fake_trivy() {{ echo '{diagnostic}' >&2; return 1; }}; "
        "run_trivy_with_retry fake_trivy"], cwd=tmp_path, capture_output=True)
    assert result.returncode == 2
    assert result.stderr.count(b'retrying') == 1


def test_empty_push_diff_falls_back_to_upstream(tmp_path, bash_common):
    bash, prefix = bash_common
    command = "git() { if [[ \"$*\" == *'@{upstream}'* && \"$1\" == diff ]]; then printf 'module/main.tf\\0'; fi; return 0; }; _changed_files_for_detect"
    result = subprocess.run([bash, '-c', prefix + command], cwd=tmp_path, capture_output=True)
    assert result.returncode == 0
    assert result.stdout == b'module/main.tf\0'


def test_powershell_retries_exit_one_lock_diagnostics(tmp_path):
    pwsh = shutil.which('pwsh')
    if not pwsh:
        pytest.skip('PowerShell unavailable')
    common = (ROOT / 'hooks/lib/common.ps1').as_posix()
    result = subprocess.run([pwsh, '-NoProfile', '-Command',
        f". '{common}'; $global:attempts=0; function Start-Sleep {{ }}; "
        "function trivy { $global:attempts++; Write-Error 'database locked' -ErrorAction Continue; $global:LASTEXITCODE=1 }; "
        "$result=Invoke-TrivyWithRetry -ArgumentList @('config', '--', '.'); "
        "@{code=$result.ExitCode;attempts=$global:attempts} | ConvertTo-Json -Compress"],
        cwd=tmp_path, capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout[result.stdout.index('{'):])
    assert data == {'code': 2, 'attempts': 2}


@pytest.fixture
def hook_bundle(tmp_path):
    bundle = tmp_path / 'bundle'
    for source in (ROOT / 'hooks').rglob('*'):
        if source.is_file() and source.suffix in ('.sh', '.ps1'):
            target = bundle / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source.read_text(encoding='utf-8'), encoding='utf-8', newline='\n')
    subprocess.run(['git', 'init', '-q'], cwd=tmp_path, check=True)
    return bundle


@pytest.mark.parametrize('language,extension', [('csharp','cs'), ('typescript','ts')])
def test_powershell_semgrep_error_option_still_blocks_findings(tmp_path, hook_bundle, language, extension):
    pwsh = shutil.which('pwsh')
    if not pwsh:
        pytest.skip('PowerShell unavailable')
    name = f'main.{extension}'
    (tmp_path / name).write_text('// fixture\n')
    subprocess.run(['git', 'add', '--', name], cwd=tmp_path, check=True)
    hook = (hook_bundle / f'hooks/semgrep-{language}.ps1').as_posix()
    command = """function semgrep {
        $index=[Array]::IndexOf($args, '--output')
        '{"results":[{"check_id":"sample","extra":{"severity":"ERROR","message":"fixture"},"path":"main","start":{"line":1}}],"errors":[]}' | Set-Content -LiteralPath $args[$index+1]
        $global:LASTEXITCODE=1
    }; & '""" + hook + "' '--error'; exit $LASTEXITCODE"
    result = subprocess.run([pwsh, '-NoProfile', '-Command', command], cwd=tmp_path,
                            capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'FAIL:' in result.stdout


@pytest.mark.parametrize('shell', ['sh','ps1'])
@pytest.mark.parametrize('status', [1,3])
@pytest.mark.parametrize('opt_in', [False,True])
def test_tflint_runtime_errors_use_explicit_compatibility_only(tmp_path, hook_bundle, shell, status, opt_in):
    executable = shutil.which('bash' if shell == 'sh' else 'pwsh')
    if not executable:
        pytest.skip('Shell unavailable')
    (tmp_path / 'main.tf').write_text('# fixture\n')
    subprocess.run(['git', 'add', '--', 'main.tf'], cwd=tmp_path, check=True)
    hook = (hook_bundle / f'hooks/tflint.{shell}').as_posix()
    if shell == 'sh':
        command = f'tflint() {{ for arg in "$@"; do [[ "$arg" == --init ]] && return 0; done; return {status}; }}; export -f tflint; bash "{hook}"'
        args = [executable, '-c', command]
    else:
        command = f"function tflint {{ $global:LASTEXITCODE=0; if ($args -notcontains '--init') {{ $global:LASTEXITCODE={status} }} }}; & '{hook}'; exit $LASTEXITCODE"
        args = [executable, '-NoProfile', '-Command', command]
    trusted = tmp_path.parent / (tmp_path.name + '-trusted.hcl')
    trusted.write_text('# trusted fixture\n')
    result = subprocess.run(args, cwd=tmp_path, env=dict(os.environ,
                            SCAN_TFLINT_CONFIG=str(trusted),
                            SCAN_TFLINT_PLUGIN_DIR=str(tmp_path.parent / 'trusted-plugins'),
                            SCAN_ALLOW_TOOL_ERRORS='1' if opt_in else '0'),
                            capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == (0 if opt_in else 1), result.stdout + result.stderr


@pytest.mark.parametrize('shell', ['sh','ps1'])
def test_optional_scanner_runs_in_each_selected_directory(tmp_path, hook_bundle, shell):
    executable = shutil.which('bash' if shell == 'sh' else 'pwsh')
    if not executable:
        pytest.skip('Shell unavailable')
    folder = tmp_path / 'module space'
    folder.mkdir()
    (folder / 'main.tf').write_text('# fixture\n')
    subprocess.run(['git', 'add', '--', 'module space/main.tf'], cwd=tmp_path, check=True)
    trace = tmp_path / 'trace'
    hook = (hook_bundle / f'hooks/snyk-iac.{shell}').as_posix()
    if shell == 'sh':
        command = f'snyk() {{ pwd > "$TRACE"; printf \'{{"infrastructureAsCodeIssues":[]}}\'; }}; export -f snyk; bash "{hook}"'
        args = [executable, '-c', command]
    else:
        command = "function snyk { (Get-Location).Path | Set-Content -LiteralPath $env:TRACE; $global:LASTEXITCODE=0; '{\"infrastructureAsCodeIssues\":[]}' }; & '" + hook + "'; exit $LASTEXITCODE"
        args = [executable, '-NoProfile', '-Command', command]
    result = subprocess.run(args, cwd=tmp_path, env=dict(os.environ, TRACE=str(trace), SNYK_TOKEN='fixture'),
                            capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stdout + result.stderr
    actual = trace.read_text(encoding='utf-8-sig').strip().replace('\\','/')
    assert actual.lower().endswith('/module space')

