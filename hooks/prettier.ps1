# prettier.ps1 — Prettier formatting for staged TS/JS/CSS/JSON/MD
# Stage: pre-commit | Mode: staged files only
#
# Runs --write (auto-format). Under Lefthook use stage_fixed:true to re-stage.
# Working dir comes from scan-config.yaml (languages.typescript.build.working_dir).
param([Parameter(ValueFromRemainingArguments)]$ExtraArgs)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\lib\common.ps1"

$allFiles = Get-StagedFiles -Extensions @('ts', 'tsx', 'js', 'jsx', 'json', 'css', 'scss', 'md')
if (@($allFiles).Count -eq 0) {
    Write-HookLog "PASS: No formattable files staged"
    exit 0
}

$workingDir = Read-ScanConfigValue -Key 'languages.typescript.build.working_dir' -Default '.'
$wdPrefix = ($workingDir.TrimEnd('/', '\') + '/')

$files = @()
foreach ($f in $allFiles) {
    $norm = $f -replace '\\', '/'
    if ($workingDir -eq '.') { $files += $norm }
    elseif ($norm.StartsWith($wdPrefix)) { $files += $norm.Substring($wdPrefix.Length) }
}
if ($files.Count -eq 0) {
    Write-HookLog "PASS: No staged files under '$workingDir'"
    exit 0
}

$localBin = Join-Path $workingDir 'node_modules/.bin/prettier.cmd'
$runner = $null; $runnerArgs = @()
if (Test-Path $localBin) { $runner = $localBin }
elseif (Get-Command prettier -ErrorAction SilentlyContinue) { $runner = 'prettier' }
elseif (Get-Command npx -ErrorAction SilentlyContinue) { $runner = 'npx'; $runnerArgs = @('--no-install', 'prettier') }
else {
    Write-HookWarn "prettier not found - allowing commit (fail-open)"
    exit 0
}

Start-ScanTimer
Write-HookLog "Formatting... ($($files.Count) files in $workingDir)"

$prettierArgs = $runnerArgs + @('--write', '--ignore-unknown')
if ($ExtraArgs) { $prettierArgs += $ExtraArgs }
$prettierArgs += $files

Push-Location $workingDir
try {
    $output = & $runner @prettierArgs 2>&1
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
$durationMs = Stop-ScanTimer

if ($exitCode -eq 0) {
    Write-HookLog "PASS: Prettier formatted (${durationMs}ms)"
    Write-ScanJson (Build-PassJson -Tool 'prettier' -ScanDirectory $workingDir -DurationMs $durationMs)
    exit 0
} else {
    $output | ForEach-Object { Write-Host $_ }
    Write-HookLog "FAIL: Prettier error (syntax?)"
    Write-ScanJson (Build-FindingsJson -Tool 'prettier' -ScanDirectory $workingDir -DurationMs $durationMs -Medium 1)
    exit 1
}
