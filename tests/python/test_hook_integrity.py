"""Shared hook paths preserve operand boundaries and scanner status."""
import json
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

