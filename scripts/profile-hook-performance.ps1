<#
.SYNOPSIS
    Profiles pre-commit hook execution times to identify optimization opportunities.

.DESCRIPTION
    This script measures the execution time of each pre-commit hook to ensure
    they meet performance targets. Hooks exceeding targets are flagged for
    optimization or migration to pre-push stage.

    Targets:
    - Per hook: <5 seconds (NFR-001)
    - Total pre-commit stage: <10 seconds (NFR-002)
    - Total pre-push stage: <60 seconds (NFR-003)

    Measures all 8 security scanning hooks:
    - Pre-commit: trivy-iac-critical, trivy-secrets, validate-suppressions, gitleaks
    - Pre-push: trivy-iac-full, checkov, checkov-strict, tflint

.PARAMETER Iterations
    Number of times to run each hook for averaging. Default: 3

.PARAMETER OutputPath
    Directory to store profiling results. Default: .scan-results/performance

.PARAMETER ShowVerbose
    Show detailed output for each iteration.

.EXAMPLE
    .\profile-hook-performance.ps1
    Profiles all hooks with default settings.

.EXAMPLE
    .\profile-hook-performance.ps1 -Iterations 5 -ShowVerbose
    Profiles with 5 iterations and verbose output.

.NOTES
    Part of auto-code-scanning infrastructure.
    Performance targets based on developer experience research.
    NFR-001: <5s per hook, NFR-002: <10s pre-commit, NFR-003: <60s pre-push.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [ValidateRange(1, 1000)]
    [int]$Iterations = 3,

    [Parameter()]
    [string]$OutputPath = ".scan-results/performance",

    [Parameter()]
    [switch]$ShowVerbose
)

. "$PSScriptRoot/../hooks/lib/common.ps1"
Assert-SafeTree $OutputPath

# Ensure output directory exists
if (-not (Test-Path $OutputPath)) {
    New-Item -ItemType Directory -Path $OutputPath -Force | Out-Null
}

$timestamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ"
$dateStamp = Get-Date -Format "yyyy-MM-dd"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Hook Performance Profiler" -ForegroundColor Cyan
Write-Host "  Iterations: $Iterations" -ForegroundColor Cyan
Write-Host "  Repository: $((Get-Location).Path)" -ForegroundColor Cyan
Write-Host "  Targets: <5s/hook, <10s pre-commit, <60s pre-push" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Performance targets (in seconds) per spec NFR-001, NFR-002, NFR-003
$targets = @{
    per_hook = 5.0
    pre_commit_total = 10.0
    pre_push_total = 60.0
}

# Initialize results
$results = @{
    timestamp = $timestamp
    iterations = $Iterations
    repository_directory = (Get-Location).Path
    targets = $targets
    hooks = @()
    summary = @{
        total_hooks = 0
        hooks_within_target = 0
        hooks_over_target = 0
        hooks_failed = 0
        slowest_hook = ""
        pre_commit_total = 0.0
        pre_push_total = 0.0
        pre_commit_within_target = $false
        pre_push_within_target = $false
        pre_commit_complete = $false
        pre_push_complete = $false
    }
    recommendations = @()
}

# All 8 security scanning hooks per spec (FR-001 through FR-009)
$hooks = @(
    # Pre-commit stage hooks
    @{ id = "trivy-iac-critical"; stage = "pre-commit" }
    @{ id = "trivy-secrets"; stage = "pre-commit" }
    @{ id = "validate-suppressions"; stage = "pre-commit" }
    @{ id = "gitleaks"; stage = "pre-commit" }

    # Pre-push stage hooks
    @{ id = "trivy-iac-full"; stage = "pre-push" }
    @{ id = "checkov"; stage = "pre-push" }
    @{ id = "checkov-strict"; stage = "pre-push" }
    @{ id = "tflint"; stage = "pre-push" }
)

Write-Host "Profiling $($hooks.Count) hooks..." -ForegroundColor Yellow
Write-Host "(This may take several minutes)`n" -ForegroundColor Gray

$preCommitTime = 0.0
$prePushTime = 0.0
$hookResults = @()
$runner = Get-Command pre-commit -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
# Native nonzero exits are data, even if the caller enables native error handling.
$PSNativeCommandUseErrorActionPreference = $false

foreach ($hook in $hooks) {
    Write-Host "  Testing: $($hook.id) [$($hook.stage)]" -ForegroundColor Gray -NoNewline

    $times = @()
    $exitCodes = @()
    $errors = @()

    for ($i = 1; $i -le $Iterations; $i++) {
        if ($ShowVerbose) {
            Write-Host " [$i/$Iterations]" -ForegroundColor DarkGray -NoNewline
        }

        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $exitCode = $null
        $iterationError = $null
        try {
            if (-not $runner) { throw 'pre-commit executable not found on PATH' }
            $hookOutput = & $runner.Source run $hook.id --all-files --hook-stage $hook.stage 2>&1
            $exitCode = $LASTEXITCODE
            if ($exitCode -ne 0) {
                $iterationError = "Exit ${exitCode}: $($hookOutput -join "`n")"
            }
        }
        catch {
            $iterationError = $_.Exception.Message
        }
        $sw.Stop()

        $times += $sw.Elapsed.TotalSeconds
        $exitCodes += $exitCode
        $errors += $iterationError
        if ($ShowVerbose) {
            Write-Host " exit=$exitCode $iterationError" -ForegroundColor DarkGray
        }
    }

    $succeeded = @($exitCodes | Where-Object { $null -eq $_ -or $_ -ne 0 }).Count -eq 0
    $avgTime = $null
    $minTime = $null
    $maxTime = $null
    if ($succeeded) {
        $avgTime = [math]::Round(($times | Measure-Object -Average).Average, 3)
        $minTime = [math]::Round(($times | Measure-Object -Minimum).Minimum, 3)
        $maxTime = [math]::Round(($times | Measure-Object -Maximum).Maximum, 3)
    }

    $status = if (-not $succeeded) { "FAILED" } elseif ($avgTime -le $targets.per_hook) { "OK" } else { "SLOW" }
    $statusColor = if ($status -eq "OK") { "Green" } else { "Red" }

    $timingLabel = if ($succeeded) { "$avgTime seconds" } else { 'excluded from timing' }
    Write-Host " - $timingLabel " -NoNewline -ForegroundColor $statusColor
    Write-Host "[$status]" -ForegroundColor $statusColor

    $hookResult = @{
        id = $hook.id
        stage = $hook.stage
        status = $status
        succeeded = $succeeded
        average_seconds = $avgTime
        min_seconds = $minTime
        max_seconds = $maxTime
        within_target = ($succeeded -and $avgTime -le $targets.per_hook)
        iterations = $times
        exit_codes = $exitCodes
        errors = $errors
    }

    $hookResults += $hookResult

    # Accumulate stage totals
    if (-not $succeeded) { continue }
    if ($hook.stage -eq "pre-commit") {
        $preCommitTime += $avgTime
    }
    else {
        $prePushTime += $avgTime
    }
}

$results.hooks = $hookResults
$results.summary.total_hooks = $hookResults.Count
$results.summary.hooks_within_target = @($hookResults | Where-Object { $_.within_target }).Count
$successfulHooks = @($hookResults | Where-Object { $_.succeeded })
$results.summary.hooks_over_target = @($successfulHooks | Where-Object { -not $_.within_target }).Count
$results.summary.hooks_failed = @($hookResults | Where-Object { -not $_.succeeded }).Count
$results.summary.pre_commit_total = [math]::Round($preCommitTime, 2)
$results.summary.pre_push_total = [math]::Round($prePushTime, 2)
$results.summary.pre_commit_complete = @($hookResults | Where-Object { $_.stage -eq 'pre-commit' -and -not $_.succeeded }).Count -eq 0
$results.summary.pre_push_complete = @($hookResults | Where-Object { $_.stage -eq 'pre-push' -and -not $_.succeeded }).Count -eq 0
$results.summary.pre_commit_within_target = ($results.summary.pre_commit_complete -and $preCommitTime -le $targets.pre_commit_total)
$results.summary.pre_push_within_target = ($results.summary.pre_push_complete -and $prePushTime -le $targets.pre_push_total)

# Find slowest hook
$slowest = $successfulHooks | Sort-Object average_seconds -Descending | Select-Object -First 1
$results.summary.slowest_hook = $slowest.id

# Generate recommendations
$slowHooks = $successfulHooks | Where-Object { -not $_.within_target }
foreach ($slow in $slowHooks) {
    if ($slow.stage -eq "pre-commit" -and $slow.average_seconds -gt 10) {
        $results.recommendations += "MIGRATE: Move '$($slow.id)' to pre-push stage (avg: $($slow.average_seconds)s)"
    }
    elseif ($slow.average_seconds -gt 5) {
        $results.recommendations += "OPTIMIZE: '$($slow.id)' exceeds 5s target (avg: $($slow.average_seconds)s)"
    }
}

if ($results.summary.pre_commit_complete -and -not $results.summary.pre_commit_within_target) {
    $results.recommendations += "TOTAL TIME: Pre-commit stage ($($results.summary.pre_commit_total)s) exceeds $($targets.pre_commit_total)s target"
}

if ($results.summary.pre_push_complete -and -not $results.summary.pre_push_within_target) {
    $results.recommendations += "TOTAL TIME: Pre-push stage ($($results.summary.pre_push_total)s) exceeds $($targets.pre_push_total)s target"
}

# Save results
$resultsFile = Join-Path $OutputPath "performance-$dateStamp.json"
Assert-SafeWritePath $resultsFile
$results | ConvertTo-Json -Depth 10 | Set-Content $resultsFile -Encoding UTF8

$latestFile = Join-Path $OutputPath "performance-latest.json"
Assert-SafeWritePath $latestFile
$results | ConvertTo-Json -Depth 10 | Set-Content $latestFile -Encoding UTF8

# Display summary
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Performance Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

Write-Host "`nPer-Hook Times (averaged over $Iterations iterations):" -ForegroundColor White
Write-Host "-----------------------------------------"

# Sort by stage then time
$sortedHooks = $hookResults | Sort-Object @{Expression={$_.stage}; Ascending=$true}, @{Expression={$_.average_seconds}; Ascending=$false}

$currentStage = ""
foreach ($hook in $sortedHooks) {
    if ($hook.stage -ne $currentStage) {
        $currentStage = $hook.stage
        Write-Host "`n  [$currentStage]" -ForegroundColor White
    }

    if (-not $hook.succeeded) {
        Write-Host ("    {0,-25} [FAILED] excluded from timing; exits: {1}" -f $hook.id, ($hook.exit_codes -join ', ')) -ForegroundColor Red
        continue
    }
    $statusIcon = if ($hook.within_target) { "[OK]  " } else { "[SLOW]" }
    $color = if ($hook.within_target) { "Green" } else { "Red" }

    $bar = ""
    $barLength = [math]::Min([int]($hook.average_seconds * 4), 40)
    $bar = "=" * $barLength

    Write-Host ("    {0,-25} {1,7:N2}s {2} {3}" -f $hook.id, $hook.average_seconds, $statusIcon, $bar) -ForegroundColor $color
}

Write-Host "`n-----------------------------------------"

# Stage totals
$preCommitColor = if ($results.summary.pre_commit_within_target) { "Green" } else { "Red" }
$prePushColor = if ($results.summary.pre_push_within_target) { "Green" } else { "Red" }
$preCommitStatus = if (-not $results.summary.pre_commit_complete) { "INCOMPLETE" } elseif ($results.summary.pre_commit_within_target) { "OK" } else { "SLOW" }
$prePushStatus = if (-not $results.summary.pre_push_complete) { "INCOMPLETE" } elseif ($results.summary.pre_push_within_target) { "OK" } else { "SLOW" }

Write-Host ("{0,-30} {1,7:N2}s (target: <{2}s) [{3}]" -f "Pre-commit total:", $results.summary.pre_commit_total, $targets.pre_commit_total, $preCommitStatus) -ForegroundColor $preCommitColor
Write-Host ("{0,-30} {1,7:N2}s (target: <{2}s) [{3}]" -f "Pre-push total:", $results.summary.pre_push_total, $targets.pre_push_total, $prePushStatus) -ForegroundColor $prePushColor

Write-Host "`nResults:" -ForegroundColor White
Write-Host "  Failed hooks: $($results.summary.hooks_failed) (excluded from timing totals)" -ForegroundColor $(if ($results.summary.hooks_failed) { 'Red' } else { 'Green' })
Write-Host "  Hooks within target: $($results.summary.hooks_within_target)/$($results.summary.total_hooks)" -ForegroundColor $(if ($results.summary.hooks_over_target -eq 0) { "Green" } else { "Yellow" })
Write-Host "  Slowest hook: $($results.summary.slowest_hook)"

if ($results.recommendations.Count -gt 0) {
    Write-Host "`nRecommendations:" -ForegroundColor Yellow
    foreach ($rec in $results.recommendations) {
        Write-Host "  - $rec" -ForegroundColor Yellow
    }
}

Write-Host "`nOutput: $resultsFile" -ForegroundColor Green
Write-Host ""

# Return results
return $results
