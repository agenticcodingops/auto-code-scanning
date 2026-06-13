# semgrep-csharp.ps1 — Semgrep SAST for C# (p/csharp ruleset)
# Stage: pre-commit | Mode: scan ONLY staged .cs files | native Windows, no WSL
param([Parameter(ValueFromRemainingArguments)]$ExtraArgs)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\lib\common.ps1"

if (-not (Test-ToolAvailable 'semgrep')) { exit 0 }

# Native Windows path (Fall-2025) + UTF-8 so Semgrep runs without WSL.
$env:PYTHONUTF8 = '1'
$env:SEMGREP_SEND_METRICS = 'off'

$files = Get-StagedFiles -Extensions @('cs')
if (@($files).Count -eq 0) {
    Write-HookLog "PASS: No C# files staged"
    exit 0
}

$ruleset = if ($env:SEMGREP_RULESET_CSHARP) { $env:SEMGREP_RULESET_CSHARP } else { 'p/csharp' }

Start-ScanTimer
Write-HookLog "Scanning... ($(@($files).Count) C# files, $ruleset)"

$semgrepArgs = @('scan', '--config', $ruleset, '--error', '--metrics', 'off', '--quiet')
if ($ExtraArgs) { $semgrepArgs += $ExtraArgs }
$semgrepArgs += $files

$output = & semgrep @semgrepArgs 2>&1
$exitCode = $LASTEXITCODE
$durationMs = Stop-ScanTimer

if ($exitCode -eq 0) {
    Write-HookLog "PASS: No findings (${durationMs}ms)"
    Write-ScanJson (Build-PassJson -Tool 'semgrep-csharp' -DurationMs $durationMs)
    exit 0
} elseif ($exitCode -eq 1) {
    $output | ForEach-Object { Write-Host $_ }
    Write-HookLog "FAIL: Semgrep (p/csharp) found issues"
    Write-ScanJson (Build-FindingsJson -Tool 'semgrep-csharp' -DurationMs $durationMs -High 1)
    exit 1
} else {
    $null = Get-HookExitCode -ToolExitCode $exitCode
    exit 0
}
