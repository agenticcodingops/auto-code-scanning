# semgrep-typescript.ps1 — Semgrep SAST for TypeScript/JavaScript (p/typescript)
# Stage: pre-commit | Mode: scan ONLY staged ts/tsx/js/jsx files
param([Parameter(ValueFromRemainingArguments)]$ExtraArgs)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\lib\common.ps1"

if (-not (Test-ToolAvailable 'semgrep')) { exit 0 }

$env:PYTHONUTF8 = '1'
$env:SEMGREP_SEND_METRICS = 'off'

$files = Get-StagedFiles -Extensions @('ts', 'tsx', 'js', 'jsx')
if (@($files).Count -eq 0) {
    Write-HookLog "PASS: No TypeScript/JavaScript files staged"
    exit 0
}

$ruleset = if ($env:SEMGREP_RULESET_TYPESCRIPT) { $env:SEMGREP_RULESET_TYPESCRIPT } else { 'p/typescript' }

Start-ScanTimer
Write-HookLog "Scanning... ($(@($files).Count) TS/JS files, $ruleset)"

$semgrepArgs = @('scan', '--config', $ruleset, '--error', '--metrics', 'off', '--quiet')
if ($ExtraArgs) { $semgrepArgs += $ExtraArgs }
$semgrepArgs += $files

$output = & semgrep @semgrepArgs 2>&1
$exitCode = $LASTEXITCODE
$durationMs = Stop-ScanTimer

if ($exitCode -eq 0) {
    Write-HookLog "PASS: No findings (${durationMs}ms)"
    Write-ScanJson (Build-PassJson -Tool 'semgrep-typescript' -DurationMs $durationMs)
    exit 0
} elseif ($exitCode -eq 1) {
    $output | ForEach-Object { Write-Host $_ }
    Write-HookLog "FAIL: Semgrep (p/typescript) found issues"
    Write-ScanJson (Build-FindingsJson -Tool 'semgrep-typescript' -DurationMs $durationMs -High 1)
    exit 1
} else {
    $null = Get-HookExitCode -ToolExitCode $exitCode
    exit 0
}
