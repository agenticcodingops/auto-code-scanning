# eslint.ps1 — ESLint for staged TS/JS (auto-fix + gate on remaining errors)
# Stage: pre-commit | Mode: staged ts/tsx/js/jsx only
#
# Working dir comes from scan-config.yaml (languages.typescript.build.working_dir).
param([Parameter(ValueFromRemainingArguments)]$ExtraArgs)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\lib\common.ps1"

$allTs = Get-StagedFiles -Extensions @('ts', 'tsx', 'js', 'jsx')
if (@($allTs).Count -eq 0) {
    Write-HookLog "PASS: No TS/JS files staged"
    exit 0
}

$workingDir = Read-ScanConfigValue -Key 'languages.typescript.build.working_dir' -Default '.'
$wdPrefix = ($workingDir.TrimEnd('/', '\') + '/')

$files = @()
foreach ($f in $allTs) {
    $norm = $f -replace '\\', '/'
    if ($workingDir -eq '.') { $files += $norm }
    elseif ($norm.StartsWith($wdPrefix)) { $files += $norm.Substring($wdPrefix.Length) }
}
if ($files.Count -eq 0) {
    Write-HookLog "PASS: No staged TS/JS under '$workingDir'"
    exit 0
}

# Resolve an eslint runner; fail-open (skip) if no eslint is set up.
$localBin = Join-Path $workingDir 'node_modules/.bin/eslint.cmd'
$runner = $null; $runnerArgs = @()
if (Test-Path $localBin) { $runner = $localBin }
elseif (Get-Command eslint -ErrorAction SilentlyContinue) { $runner = 'eslint' }
elseif (Get-Command npx -ErrorAction SilentlyContinue) { $runner = 'npx'; $runnerArgs = @('--no-install', 'eslint') }
else {
    Write-HookWarn "eslint not found (no node_modules, eslint, or npx) - allowing commit (fail-open)"
    exit 0
}

Start-ScanTimer
Write-HookLog "Linting... ($($files.Count) TS/JS files in $workingDir)"

$eslintArgs = $runnerArgs + @('--fix')
if ($ExtraArgs) { $eslintArgs += $ExtraArgs }
$eslintArgs += $files

Push-Location $workingDir
try {
    $output = & $runner @eslintArgs 2>&1
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
$durationMs = Stop-ScanTimer

if ($exitCode -eq 0) {
    Write-HookLog "PASS: ESLint clean (${durationMs}ms)"
    Write-ScanJson (Build-PassJson -Tool 'eslint' -ScanDirectory $workingDir -DurationMs $durationMs)
    exit 0
} elseif ($exitCode -eq 1) {
    $output | ForEach-Object { Write-Host $_ }
    Write-HookLog "FAIL: ESLint errors remain (some may have been auto-fixed; re-stage)"
    Write-ScanJson (Build-FindingsJson -Tool 'eslint' -ScanDirectory $workingDir -DurationMs $durationMs -High 1)
    exit 1
} else {
    $null = Get-HookExitCode -ToolExitCode $exitCode
    exit 0
}
