# gitleaks.ps1 — Gitleaks secret detection scanner
# Stage: pre-commit | Severity: HIGH (all secrets map to HIGH)
# Scans ONLY staged changes. `git --staged` is the supported form of the
# deprecated `protect --staged` command (hidden since Gitleaks 8.19.0).
# The JSON report is stdout (`--report-path -`). stderr is not part of the report.
# Do NOT print Match or Secret: those fields are the credential.
param([Parameter(ValueFromRemainingArguments)]$ExtraArgs)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\lib\common.ps1"

# A config error is text on stderr. PowerShell 7.4+ would otherwise turn that
# native stderr into a terminating error and hide the exit code.
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

# Verify tool availability
if (-not (Test-ToolAvailable 'gitleaks')) { exit 0 }

# Check if there are any staged files at all
$stagedFiles = git diff --cached --name-only --diff-filter=ACMR 2>$null
if (-not $stagedFiles -or @($stagedFiles).Count -eq 0) {
    Write-HookLog "PASS: No files staged"
    exit 0
}

Start-ScanTimer

$stagedCount = @($stagedFiles).Count
Write-HookLog "Scanning... ($stagedCount staged files)"

# `git --staged` with `--report-path -` writes the JSON array to stdout.
# `protect --staged` without `--report-path` writes no JSON, and Gitleaks uses
# exit 1 both for leaks and for a config it cannot load.
$gitleaksArgs = @(
    'git', '--staged',
    '--report-format', 'json',
    '--report-path', '-',
    '--redact',
    '--no-banner',
    '--exit-code', '1',
    '--log-level', 'error'
)

# Check for config file
$configFile = Resolve-ScanConfig -Filename '.gitleaks.toml'
if ($configFile) {
    $gitleaksArgs += @('--config', $configFile)
}

# Add extra args
if ($ExtraArgs) {
    $gitleaksArgs += $ExtraArgs
}

$stderrFile = New-TemporaryFile
try {
    $stdout = & gitleaks @gitleaksArgs 2>$stderrFile
    $exitCode = $LASTEXITCODE
} finally {
    Remove-Item -Force $stderrFile -ErrorAction SilentlyContinue
}

function ConvertFrom-GitleaksReport {
    param([string]$ReportText)

    if ([string]::IsNullOrWhiteSpace($ReportText)) {
        return @{ Ok = $false; Rows = @() }
    }
    $trim = $ReportText.Trim()
    if (-not $trim.StartsWith('[')) {
        return @{ Ok = $false; Rows = @() }
    }
    try {
        if ((Get-Command ConvertFrom-Json).Parameters.ContainsKey('NoEnumerate')) {
            $data = $trim | ConvertFrom-Json -NoEnumerate
        } else {
            $data = $trim | ConvertFrom-Json
        }
    } catch {
        return @{ Ok = $false; Rows = @() }
    }

    $rows = New-Object System.Collections.Generic.List[object]
    foreach ($item in @($data)) {
        if ($null -eq $item -or -not $item.RuleID) { continue }
        $start = 0
        if ($null -ne $item.StartLine) { $start = [int]$item.StartLine }
        $end = $start
        if ($null -ne $item.EndLine) { $end = [int]$item.EndLine }
        $desc = ''
        if ($null -ne $item.Description) { $desc = [string]$item.Description }
        $path = ''
        if ($null -ne $item.File) { $path = [string]$item.File }
        $rows.Add([pscustomobject]@{
            RuleId      = [string]$item.RuleID
            File        = $path
            Start       = $start
            End         = $end
            Description = $desc
        }) | Out-Null
    }
    return @{ Ok = $true; Rows = $rows }
}

function Write-GitleaksPass {
    param([int]$DurationMs)
    Write-HookLog "PASS: No findings above threshold"
    Write-ScanJson (Build-PassJson -Tool 'gitleaks' -DurationMs $DurationMs)
}

$text = ''
if ($null -ne $stdout) {
    $text = (@($stdout) -join "`n").Trim()
}
$parsed = ConvertFrom-GitleaksReport -ReportText $text

# Same fail-open as the bash hook: process exit 0, not 2. pre-commit blocks
# every non-zero status. Exit 1 is only a parsed findings array.
if (-not $parsed.Ok) {
    Write-HookWarn "gitleaks exited $exitCode without a JSON findings report - allowing commit (fail-open)"
    Write-GitleaksPass -DurationMs (Stop-ScanTimer)
    exit 0
}

$rows = @($parsed.Rows | Where-Object { $null -ne $_ })
$durationMs = Stop-ScanTimer
if ($rows.Count -eq 0) {
    Write-GitleaksPass -DurationMs $durationMs
    exit 0
}

Write-HookLog ""
foreach ($row in $rows) {
    Write-HookLog "  HIGH  $($row.RuleId)  $($row.File):$($row.Start)-$($row.End)"
    if ($row.Description) {
        Write-HookLog "    $($row.Description)"
    }
}
Write-HookLog ""
Write-HookLog "FAIL: $(Format-FindingSummary -High $rows.Count)"

$findingObjects = foreach ($row in $rows) {
    [pscustomobject]@{
        rule_id  = $row.RuleId
        tool     = 'gitleaks'
        severity = 'HIGH'
        file     = $row.File
        line     = $row.Start
        message  = $row.Description
        fixable  = $false
        fixed    = $false
    }
}
$findingsJson = ConvertTo-Json -InputObject @($findingObjects) -Depth 5 -Compress
if ($rows.Count -eq 1 -and -not $findingsJson.TrimStart().StartsWith('[')) {
    $findingsJson = '[' + $findingsJson + ']'
}
Write-ScanJson (Build-FindingsJson -Tool 'gitleaks' -DurationMs $durationMs -FindingsArray $findingsJson -High $rows.Count)
exit 1
