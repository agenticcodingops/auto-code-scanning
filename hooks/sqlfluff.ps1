# sqlfluff.ps1 — SQLFluff linting for staged .sql files
# Stage: pre-commit | Mode: staged .sql only
param([Parameter(ValueFromRemainingArguments)]$ExtraArgs)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\lib\common.ps1"

Invoke-StagedSnapshot -HookPath $PSCommandPath -HookArguments $ExtraArgs

if (-not (Test-ToolAvailable 'sqlfluff')) { exit 0 }

$files = Get-StagedFiles -Extensions @('sql')
if (@($files).Count -eq 0) {
    Write-HookLog "PASS: No SQL files staged"
    exit 0
}

# CLI dialects override nested configs. Keep configured and default files apart.
$configuredFiles = @()
$defaultFiles = @()
foreach ($file in $files) {
    $directory = Split-Path -Parent $file
    $configured = $false
    while ($true) {
        if (-not $directory) { $directory = '.' }
        if (Test-Path -LiteralPath (Join-Path $directory '.sqlfluff') -PathType Leaf) {
            $configured = $true
            break
        }
        if ($directory -eq '.') { break }
        $directory = Split-Path -Parent $directory
    }
    if ($configured) { $configuredFiles += $file } else { $defaultFiles += $file }
}

Start-ScanTimer
Write-HookLog "Linting... ($(@($files).Count) SQL files, project dialects or ansi default)"
$output = @()
$exitCode = 0
foreach ($group in @('configured', 'default')) {
    $sqlfluffArgs = @('lint')
    $selectedFiles = @(if ($group -eq 'configured') { $configuredFiles } else { $defaultFiles })
    if ($selectedFiles.Count -eq 0) { continue }
    if ($group -eq 'default') { $sqlfluffArgs += @('--dialect', 'ansi') }
    if ($ExtraArgs) { $sqlfluffArgs += $ExtraArgs }
    $sqlfluffArgs += '--'
    $sqlfluffArgs += $selectedFiles
    $output += & sqlfluff @sqlfluffArgs 2>&1
    $groupExit = $LASTEXITCODE
    if ($groupExit -eq 1) { $exitCode = 1 }
    elseif ($groupExit -ne 0) { $null = Get-HookExitCode -ToolExitCode $groupExit }
}
$durationMs = Stop-ScanTimer

if ($exitCode -eq 0) {
    Write-HookLog "PASS: SQLFluff clean (${durationMs}ms)"
    Write-ScanJson (Build-PassJson -Tool 'sqlfluff' -DurationMs $durationMs)
    exit 0
} elseif ($exitCode -eq 1) {
    $output | ForEach-Object { Write-Host $_ }
    Write-HookLog "FAIL: SQLFluff lint issues"
    Write-ScanJson (Build-FindingsJson -Tool 'sqlfluff' -DurationMs $durationMs -Medium 1)
    exit 1
} else {
    $null = Get-HookExitCode -ToolExitCode $exitCode
    exit 0
}
