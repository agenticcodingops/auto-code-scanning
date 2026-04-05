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

.PARAMETER FixtureDir
    Directory containing test fixtures to scan. Default: tests/fixtures/terraform-valid

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
    [int]$Iterations = 3,

    [Parameter()]
    [string]$OutputPath = ".scan-results/performance",

    [Parameter()]
    [string]$FixtureDir = "tests/fixtures/terraform-valid",

    [Parameter()]
    [switch]$ShowVerbose
)

# Ensure output directory exists
if (-not (Test-Path $OutputPath)) {
    New-Item -ItemType Directory -Path $OutputPath -Force | Out-Null
}

$timestamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ"
$dateStamp = Get-Date -Format "yyyy-MM-dd"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Hook Performance Profiler" -ForegroundColor Cyan
Write-Host "  Iterations: $Iterations" -ForegroundColor Cyan
Write-Host "  Fixture: $FixtureDir" -ForegroundColor Cyan
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
    fixture_directory = $FixtureDir
    targets = $targets
    hooks = @()
    summary = @{
        total_hooks = 0
        hooks_within_target = 0
        hooks_over_target = 0
        slowest_hook = ""
        pre_commit_total = 0.0
        pre_push_total = 0.0
        pre_commit_within_target = $false
        pre_push_within_target = $false
    }
    recommendations = @()
}

# All 8 security scanning hooks per spec (FR-001 through FR-009)
$hooks = @(
    # Pre-commit stage hooks
    @{ id = "trivy-iac-critical"; stage = "pre-commit"; command = "pre-commit run trivy-iac-critical --all-files" }
    @{ id = "trivy-secrets"; stage = "pre-commit"; command = "pre-commit run trivy-secrets --all-files" }
    @{ id = "validate-suppressions"; stage = "pre-commit"; command = "pre-commit run validate-suppressions --all-files" }
    @{ id = "gitleaks"; stage = "pre-commit"; command = "pre-commit run gitleaks --all-files" }

    # Pre-push stage hooks
    @{ id = "trivy-iac-full"; stage = "pre-push"; command = "pre-commit run trivy-iac-full --all-files" }
    @{ id = "checkov"; stage = "pre-push"; command = "pre-commit run checkov --all-files" }
    @{ id = "checkov-strict"; stage = "pre-push"; command = "pre-commit run checkov-strict --all-files" }
    @{ id = "tflint"; stage = "pre-push"; command = "pre-commit run tflint --all-files" }
)

Write-Host "Profiling $($hooks.Count) hooks..." -ForegroundColor Yellow
Write-Host "(This may take several minutes)`n" -ForegroundColor Gray

$preCommitTime = 0.0
$prePushTime = 0.0
$hookResults = @()

foreach ($hook in $hooks) {
    Write-Host "  Testing: $($hook.id) [$($hook.stage)]" -ForegroundColor Gray -NoNewline

    $times = @()

    for ($i = 1; $i -le $Iterations; $i++) {
        if ($ShowVerbose) {
            Write-Host " [$i/$Iterations]" -ForegroundColor DarkGray -NoNewline
        }

        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        try {
            $null = Invoke-Expression "$($hook.command) 2>&1" -ErrorAction SilentlyContinue
        }
        catch {
            # Hook may fail on findings - we still want the timing
        }
        $sw.Stop()

        $times += $sw.Elapsed.TotalSeconds
    }

    $avgTime = ($times | Measure-Object -Average).Average
    $minTime = ($times | Measure-Object -Minimum).Minimum
    $maxTime = ($times | Measure-Object -Maximum).Maximum

    $status = if ($avgTime -le $targets.per_hook) { "OK" } else { "SLOW" }
    $statusColor = if ($status -eq "OK") { "Green" } else { "Red" }

    Write-Host " - $([math]::Round($avgTime, 2))s " -NoNewline -ForegroundColor $statusColor
    Write-Host "[$status]" -ForegroundColor $statusColor

    $hookResult = @{
        id = $hook.id
        stage = $hook.stage
        average_seconds = [math]::Round($avgTime, 3)
        min_seconds = [math]::Round($minTime, 3)
        max_seconds = [math]::Round($maxTime, 3)
        within_target = ($avgTime -le $targets.per_hook)
        iterations = $times
    }

    $hookResults += $hookResult

    # Accumulate stage totals
    if ($hook.stage -eq "pre-commit") {
        $preCommitTime += $avgTime
    }
    else {
        $prePushTime += $avgTime
    }
}

$results.hooks = $hookResults
$results.summary.total_hooks = $hookResults.Count
$results.summary.hooks_within_target = ($hookResults | Where-Object { $_.within_target }).Count
$results.summary.hooks_over_target = ($hookResults | Where-Object { -not $_.within_target }).Count
$results.summary.pre_commit_total = [math]::Round($preCommitTime, 2)
$results.summary.pre_push_total = [math]::Round($prePushTime, 2)
$results.summary.pre_commit_within_target = ($preCommitTime -le $targets.pre_commit_total)
$results.summary.pre_push_within_target = ($prePushTime -le $targets.pre_push_total)

# Find slowest hook
$slowest = $hookResults | Sort-Object average_seconds -Descending | Select-Object -First 1
$results.summary.slowest_hook = $slowest.id

# Generate recommendations
$slowHooks = $hookResults | Where-Object { -not $_.within_target }
foreach ($slow in $slowHooks) {
    if ($slow.stage -eq "pre-commit" -and $slow.average_seconds -gt 10) {
        $results.recommendations += "MIGRATE: Move '$($slow.id)' to pre-push stage (avg: $($slow.average_seconds)s)"
    }
    elseif ($slow.average_seconds -gt 5) {
        $results.recommendations += "OPTIMIZE: '$($slow.id)' exceeds 5s target (avg: $($slow.average_seconds)s)"
    }
}

if (-not $results.summary.pre_commit_within_target) {
    $results.recommendations += "TOTAL TIME: Pre-commit stage ($($results.summary.pre_commit_total)s) exceeds $($targets.pre_commit_total)s target"
}

if (-not $results.summary.pre_push_within_target) {
    $results.recommendations += "TOTAL TIME: Pre-push stage ($($results.summary.pre_push_total)s) exceeds $($targets.pre_push_total)s target"
}

# Save results
$resultsFile = Join-Path $OutputPath "performance-$dateStamp.json"
$results | ConvertTo-Json -Depth 10 | Set-Content $resultsFile -Encoding UTF8

$latestFile = Join-Path $OutputPath "performance-latest.json"
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
$preCommitStatus = if ($results.summary.pre_commit_within_target) { "OK" } else { "SLOW" }
$prePushStatus = if ($results.summary.pre_push_within_target) { "OK" } else { "SLOW" }

Write-Host ("{0,-30} {1,7:N2}s (target: <{2}s) [{3}]" -f "Pre-commit total:", $results.summary.pre_commit_total, $targets.pre_commit_total, $preCommitStatus) -ForegroundColor $preCommitColor
Write-Host ("{0,-30} {1,7:N2}s (target: <{2}s) [{3}]" -f "Pre-push total:", $results.summary.pre_push_total, $targets.pre_push_total, $prePushStatus) -ForegroundColor $prePushColor

Write-Host "`nResults:" -ForegroundColor White
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
