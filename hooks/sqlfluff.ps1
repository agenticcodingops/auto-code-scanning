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
        foreach ($config in @('setup.cfg', 'tox.ini', 'pep8.ini', 'pyproject.toml')) {
            $path = Join-Path $directory $config
            $section = if ($config -eq 'pyproject.toml') { '^\s*\[tool\.sqlfluff(\.|\])' } else { '^\s*\[sqlfluff(:|\])' }
            if ((Test-Path -LiteralPath $path -PathType Leaf) -and
                (Select-String -LiteralPath $path -Pattern $section -Quiet)) { $configured = $true }
        }
        if ($configured) { break }
        if ($directory -eq '.') { break }
        $directory = Split-Path -Parent $directory
    }
    if ($configured) { $configuredFiles += $file } else { $defaultFiles += $file }
}

Start-ScanTimer
Write-HookLog "Linting... ($(@($files).Count) SQL files, project dialects or ansi default)"
$exitCode = 0
$toolErrors = @()
$results = Join-Path ([IO.Path]::GetTempPath()) ('scan-sql-' + [guid]::NewGuid())
$null = New-Item -ItemType Directory -Path $results
try {
    foreach ($group in @('configured', 'default')) {
        $sqlfluffArgs = @('lint')
        $selectedFiles = @(if ($group -eq 'configured') { $configuredFiles } else { $defaultFiles })
        if ($selectedFiles.Count -eq 0) { continue }
        if ($group -eq 'default') { $sqlfluffArgs += @('--dialect', 'ansi') }
        if ($ExtraArgs) { $sqlfluffArgs += $ExtraArgs }
        $sqlfluffArgs += '--'
        $sqlfluffArgs += $selectedFiles
        $groupOutput = & sqlfluff @sqlfluffArgs 2>&1
        $groupExit = $LASTEXITCODE
        [IO.File]::WriteAllText((Join-Path $results "$group.output"), ($groupOutput -join "`n"))
        [IO.File]::WriteAllText((Join-Path $results "$group.exit"), [string]$groupExit)
        if ($groupExit -eq 1) { $exitCode = 1 }
        elseif ($groupExit -ne 0) { $toolErrors += $groupExit }
    }
    $durationMs = Stop-ScanTimer
    $py = Find-WorkingPython
    if (-not $py) { throw 'Python is required for SQL lint reports' }
    $report = & $py -I "$PSScriptRoot/lib/sqlfluff_report.py" $results $durationMs
    if ($LASTEXITCODE -ne 0) { throw 'SQL lint report failed; scan incomplete' }
    Write-ScanJson ($report -join "`n")
    foreach ($group in @('configured', 'default')) {
        $path = Join-Path $results "$group.output"
        if (Test-Path -LiteralPath $path) { Write-Host ([IO.File]::ReadAllText($path)) }
    }

    if ($exitCode -eq 1) {
        Write-HookLog "FAIL: SQLFluff lint issues"
    } elseif ($toolErrors.Count -eq 0) {
        Write-HookLog "PASS: SQLFluff clean (${durationMs}ms)"
    }
    foreach ($code in $toolErrors) {
        try { $null = Get-HookExitCode -ToolExitCode $code }
        catch {
            Write-HookError $_
            $exitCode = 1
        }
    }
} finally {
    Remove-Item -LiteralPath $results -Recurse -Force
}
exit $exitCode
