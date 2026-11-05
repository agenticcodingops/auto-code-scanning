"""Concurrent hook reports stay atomic and fail closed on lasting write errors."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def writers(tmp_path):
    """Use LF sources for the native Windows Bash runtime as well as POSIX."""
    # common.* load their sibling libraries, so copy every hook library they source.
    for name in ('common', 'tool-paths'):
        for suffix in ('ps1', 'sh'):
            (tmp_path / f'{name}.{suffix}').write_text(
                (ROOT / f'hooks/lib/{name}.{suffix}').read_text(encoding='utf-8'),
                encoding='utf-8', newline='\n')
    return tmp_path


def command(folder, shell, body):
    executable = shutil.which(shell)
    if not executable:
        pytest.skip(f'{shell} unavailable')
    if shell == 'bash':
        return [executable, '-c', f'set -euo pipefail; source "{folder.as_posix()}/common.sh"; {body}']
    return [executable, '-NoProfile', '-Command', f". '{folder.as_posix()}/common.ps1'; {body}"]


def wait_for(paths, processes):
    deadline = time.monotonic() + 20
    while not all(path.exists() for path in paths):
        assert time.monotonic() < deadline, 'writers did not reach the publication barrier'
        for process in processes:
            if process.poll() is not None:
                out, err = process.communicate()
                pytest.fail(f'writer exited before barrier: {out}\n{err}')
        time.sleep(0.01)


@pytest.mark.skipif(os.name != 'nt', reason='Windows denies rename while a reader omits delete sharing')
@pytest.mark.parametrize('shells', [('pwsh', 'pwsh'), ('bash', 'bash'), ('pwsh', 'bash')])
def test_two_writers_retry_windows_sharing_violation(writers, shells):
    """Hold a real Windows handle briefly to make the parallel rename race reproducible.

    Only the existing path checker is wrapped, after doing its real validation;
    neither the writer nor the filesystem publication operation is mocked.
    """
    report = writers / '.scanning/last-scan.json'
    report.parent.mkdir()
    report.write_text('{"previous":true}', encoding='utf-8')
    processes = []
    try:
        for index, shell in enumerate(shells):
            payload = json.dumps({'writer': index, 'body': str(index) * 65536})
            (writers / f'payload{index}').write_text(payload, encoding='utf-8')
            if shell == 'bash':
                body = f'''eval "$(declare -f assert_safe_write_path | sed '1s/assert_safe_write_path/check_original/')"
checks=0
assert_safe_write_path() {{
    check_original "$@"
    checks=$((checks + 1))
    if [[ $checks == 2 ]]; then
        touch ready{index}
        while [[ ! -f go ]]; do sleep 0.01; done
    fi
}}
write_scan_json "$(cat payload{index})"
'''
            else:
                body = f'''$originalCheck = ${{function:Assert-SafeWritePath}}
$script:checks = 0
function Assert-SafeWritePath {{
    param([string]$Path)
    & $originalCheck $Path
    $script:checks++
    if ($script:checks -eq 2) {{
        [IO.File]::WriteAllText('ready{index}', '')
        while (-not [IO.File]::Exists('go')) {{ Start-Sleep -Milliseconds 10 }}
    }}
}}
Write-ScanJson ([IO.File]::ReadAllText('payload{index}'))
'''
            processes.append(subprocess.Popen(command(writers, shell, body), cwd=writers,
                                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                               text=True, encoding='utf-8'))
        wait_for([writers / f'ready{i}' for i in range(2)], processes)
        with report.open('rb'):
            (writers / 'go').touch()
            time.sleep(0.4)
            assert json.loads(report.read_text()) == {'previous': True}
        for process in processes:
            out, err = process.communicate(timeout=20)
            assert process.returncode == 0, out + err
        assert json.loads(report.read_text()) in [
            {'writer': i, 'body': str(i) * 65536} for i in range(2)]
        assert not list(report.parent.glob('.scan-write-*'))
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate()


@pytest.mark.parametrize('shell', ['pwsh', 'bash'])
@pytest.mark.parametrize('existing', [False, True])
def test_concurrent_report_creation_and_replacement(writers, shell, existing):
    report = writers / '.scanning/last-scan.json'
    if existing:
        report.parent.mkdir()
        report.write_text('{}', encoding='utf-8')
    processes = []
    try:
        for index in range(2):
            if shell == 'bash':
                body = f'''touch ready{index}
while [[ ! -f go ]]; do sleep 0.01; done
# Each publication starts path-check interpreters; keep this a concurrency
# regression rather than a process-startup stress benchmark.
for ((i=0; i<10; i++)); do write_scan_json '{{"writer":{index}}}'; done'''
            else:
                body = f'''[IO.File]::WriteAllText('ready{index}', '')
while (-not [IO.File]::Exists('go')) {{ Start-Sleep -Milliseconds 10 }}
for ($i=0; $i -lt 100; $i++) {{ Write-ScanJson '{{"writer":{index}}}' }}'''
            processes.append(subprocess.Popen(command(writers, shell, body), cwd=writers,
                                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                               text=True, encoding='utf-8'))
        wait_for([writers / f'ready{i}' for i in range(2)], processes)
        (writers / 'go').touch()
        for process in processes:
            out, err = process.communicate(timeout=90)
            assert process.returncode == 0, out + err
        assert json.loads(report.read_text()) in [{'writer': 0}, {'writer': 1}]
        assert not list(report.parent.glob('.scan-write-*'))
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate()


@pytest.mark.parametrize('shell', ['pwsh', 'bash'])
def test_permanent_report_write_failure_is_bounded_and_cleans_temporary(writers, shell):
    report = writers / '.scanning/last-scan.json'
    report.mkdir(parents=True)  # A directory cannot be replaced by a report.
    result = subprocess.run(command(writers, shell,
        "write_scan_json '{}'" if shell == 'bash' else "Write-ScanJson '{}'"),
        cwd=writers, capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert result.returncode != 0, result.stdout + result.stderr
    assert report.is_dir()
    assert not list(report.parent.glob('.scan-write-*'))


@pytest.mark.parametrize('shell', ['pwsh', 'bash'])
@pytest.mark.parametrize('location', ['directory', 'report'])
def test_report_writer_refuses_linked_output(writers, shell, location):
    outside = writers / 'outside'
    outside.mkdir()
    report = outside / 'last-scan.json'
    report.write_text('{"previous":true}', encoding='utf-8')
    link = writers / '.scanning'
    if location == 'report':
        link.mkdir()
        link = link / 'last-scan.json'
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        if os.name != 'nt':
            pytest.skip('directory links unavailable')
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)], capture_output=True)
        if result.returncode:
            pytest.skip('junction unavailable')
    result = subprocess.run(command(writers, shell,
        "write_scan_json '{}'" if shell == 'bash' else "Write-ScanJson '{}'"),
        cwd=writers, capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert result.returncode != 0, result.stdout + result.stderr
    assert json.loads(report.read_text()) == {'previous': True}
    assert list(outside.iterdir()) == [report]


def test_bash_failed_payload_write_cannot_publish_partial_report(writers):
    report = writers / '.scanning/last-scan.json'
    report.parent.mkdir()
    report.write_text('{"previous":true}', encoding='utf-8')
    # Simulate an exhausted filesystem, in a conditional where errexit is disabled.
    body = '''printf() { builtin printf 'partial'; return 1; }
if write_scan_json '{"new":true}'; then exit 0; else exit 1; fi'''
    result = subprocess.run(command(writers, 'bash', body), cwd=writers,
                            capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert result.returncode != 0, result.stdout + result.stderr
    assert json.loads(report.read_text()) == {'previous': True}
    assert not list(report.parent.glob('.scan-write-*'))


@pytest.mark.skipif(os.name != 'nt', reason='requires Windows file sharing semantics')
@pytest.mark.parametrize('shell', ['pwsh', 'bash'])
def test_lasting_sharing_violation_fails_without_changing_report(writers, shell):
    report = writers / '.scanning/last-scan.json'
    report.parent.mkdir()
    report.write_text('{"previous":true}', encoding='utf-8')
    with report.open('rb'):
        result = subprocess.run(command(writers, shell,
            "write_scan_json '{}'" if shell == 'bash' else "Write-ScanJson '{}'"),
            cwd=writers, capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert result.returncode != 0, result.stdout + result.stderr
    assert json.loads(report.read_text()) == {'previous': True}
    assert not list(report.parent.glob('.scan-write-*'))


@pytest.mark.parametrize('shell', ['pwsh', 'bash'])
def test_fresh_path_safety_rejection_is_terminal(writers, shell):
    """A safety rejection after staging must never be swallowed by retry logic."""
    report = writers / '.scanning/last-scan.json'
    report.parent.mkdir()
    report.write_text('{"previous":true}', encoding='utf-8')
    outside = writers / 'outside'
    outside.mkdir()
    sentinel = outside / 'last-scan.json'
    sentinel.write_text('{"outside":true}', encoding='utf-8')
    link = writers / 'linked'
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        if os.name != 'nt':
            pytest.skip('directory links unavailable')
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)], capture_output=True)
        if result.returncode:
            pytest.skip('junction unavailable')
    # The second real validation observes a linked path once. Subsequent calls
    # would see the original safe path, modelling an attacker removing the link.
    if shell == 'bash':
        body = '''eval "$(declare -f assert_safe_write_path | sed '1s/assert_safe_write_path/check_original/')"
checks=0
assert_safe_write_path() {
    check_original "$@"
    checks=$((checks + 1))
    if [[ $checks == 2 ]]; then check_original linked/last-scan.json; fi
}
write_scan_json '{}'
'''
    else:
        body = '''$originalCheck = ${function:Assert-SafeWritePath}
$script:checks = 0
function Assert-SafeWritePath {
    param([string]$Path)
    & $originalCheck $Path
    $script:checks++
    if ($script:checks -eq 2) { & $originalCheck 'linked/last-scan.json' }
}
Write-ScanJson '{}'
'''
    result = subprocess.run(command(writers, shell, body), cwd=writers,
                            capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert result.returncode != 0, result.stdout + result.stderr
    assert json.loads(report.read_text(encoding='utf-8')) == {'previous': True}
    assert json.loads(sentinel.read_text(encoding='utf-8')) == {'outside': True}
    assert not list(report.parent.glob('.scan-write-*'))


def test_powershell_cleans_hidden_staging_file_on_failure(writers):
    """Dot files are hidden on POSIX; emulate that attribute on Windows too."""
    report = writers / '.scanning/last-scan.json'
    report.mkdir(parents=True)
    body = '''$originalCheck = ${function:Assert-SafeWritePath}
$script:checks = 0
function Assert-SafeWritePath {
    param([string]$Path)
    & $originalCheck $Path
    $script:checks++
    if ($script:checks -eq 2 -and [Environment]::OSVersion.Platform -eq 'Win32NT') {
        foreach ($item in Get-ChildItem -LiteralPath '.scanning' -Force -File) {
            $item.Attributes = $item.Attributes -bor [IO.FileAttributes]::Hidden
        }
    }
}
Write-ScanJson '{}'
'''
    result = subprocess.run(command(writers, 'pwsh', body), cwd=writers,
                            capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert result.returncode != 0, result.stdout + result.stderr
    assert report.is_dir()
    assert not list(report.parent.glob('.scan-write-*'))


@pytest.mark.parametrize('exception', ['IOException', 'UnauthorizedAccessException'])
@pytest.mark.parametrize('existing', [False, True])
@pytest.mark.parametrize('lasting', [False, True])
def test_powershell_publication_retries_filesystem_errors(writers, exception, existing, lasting):
    """Inject a publication fault, then use the real Move/Replace on recovery."""
    report = writers / '.scanning/last-scan.json'
    report.parent.mkdir()
    if existing:
        report.write_text('{"previous":true}', encoding='utf-8')
    exception_type = 'System.IO.IOException' if exception == 'IOException' else 'System.UnauthorizedAccessException'
    body = '''Add-Type @'
public static class RetryPublication {
    public static int Attempts;
    public static int Failures;
    public static void Publish(string source, string destination) {
        Attempts++;
        if (Attempts <= Failures) { throw new EXCEPTION("publication fault"); }
        if (System.IO.File.Exists(destination)) {
            System.IO.File.Replace(source, destination, null);
        } else {
            System.IO.File.Move(source, destination);
        }
    }
}
'@
[RetryPublication]::Failures = FAILURES
$writer = ${function:Write-ScanJson}.ToString().Replace(
    '[IO.File]::Replace($temporary, $destination, [NullString]::Value)',
    '[RetryPublication]::Publish($temporary, $destination)').Replace(
    '[IO.File]::Move($temporary, $destination)',
    '[RetryPublication]::Publish($temporary, $destination)')
Set-Item Function:Write-ScanJson ([scriptblock]::Create($writer))
$script:sleeps = 0
function Start-Sleep { param($Milliseconds) $script:sleeps++ }
$failed = $false
try { Write-ScanJson '{"new":true}' } catch { $failed = $true }
@{attempts=[RetryPublication]::Attempts; sleeps=$script:sleeps; failed=$failed} | ConvertTo-Json -Compress
'''.replace('EXCEPTION', exception_type).replace('FAILURES', '20' if lasting else '1')
    result = subprocess.run(command(writers, 'pwsh', body), cwd=writers,
                            capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {
        'attempts': 20 if lasting else 2, 'sleeps': 19 if lasting else 1, 'failed': lasting}
    if lasting:
        assert report.exists() == existing
        if existing:
            assert json.loads(report.read_text()) == {'previous': True}
    else:
        assert json.loads(report.read_text()) == {'new': True}
    assert not list(report.parent.glob('.scan-write-*'))


@pytest.mark.parametrize('exception', ['IO.IOException', 'UnauthorizedAccessException'])
def test_powershell_retryable_exception_during_path_check_is_terminal(writers, exception):
    report = writers / '.scanning/last-scan.json'
    report.parent.mkdir()
    report.write_text('{"previous":true}', encoding='utf-8')
    body = '''$originalCheck = ${function:Assert-SafeWritePath}
$script:checks = 0
$script:sleeps = 0
function Assert-SafeWritePath {
    param([string]$Path)
    & $originalCheck $Path
    $script:checks++
    if ($script:checks -eq 2) { throw [EXCEPTION]::new('path check fault') }
}
function Start-Sleep { param($Milliseconds) $script:sleeps++ }
$failed = $false
try { Write-ScanJson '{"new":true}' } catch { $failed = $true }
@{checks=$script:checks; sleeps=$script:sleeps; failed=$failed} | ConvertTo-Json -Compress
'''.replace('EXCEPTION', exception)
    result = subprocess.run(command(writers, 'pwsh', body), cwd=writers,
                            capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {'checks': 2, 'sleeps': 0, 'failed': True}
    assert json.loads(report.read_text()) == {'previous': True}
    assert not list(report.parent.glob('.scan-write-*'))
