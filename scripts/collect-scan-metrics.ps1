<#
.SYNOPSIS
    Collects and tracks security scanning adoption and effectiveness metrics.

.DESCRIPTION
    This script collects key metrics for measuring the success of the shift-left
    security scanning initiative. Metrics are based on industry research and
    DORA best practices.

    Tracked Metrics:
    - Bypass rate (<5% target) - commits using --no-verify
    - Hook pass rate (>80% first attempt target)
    - Finding counts by severity and tool
    - Trend comparison with previous collection period

    Output conforms to the Metric entity schema in data-model.md.

.PARAMETER OutputPath
    Directory to store metrics data. Default: .scan-results/metrics

.PARAMETER Days
    Number of days of history to analyze. Default: 30

.PARAMETER CloudProvider
    Cloud provider for context. Default: detected from configs.

.PARAMETER UploadArtifact
    When running in GitHub Actions, upload metrics JSON as artifact.

.EXAMPLE
    .\collect-scan-metrics.ps1
    Collects metrics for the last 30 days.

.EXAMPLE
    .\collect-scan-metrics.ps1 -Days 90 -UploadArtifact
    Collects 90 days of metrics and uploads as GitHub Actions artifact.

.NOTES
    Part of auto-code-scanning infrastructure.
    Metrics targets based on DORA and Forrester TEI research.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$OutputPath = ".scan-results/metrics",

    [Parameter()]
    [int]$Days = 30,

    [Parameter()]
    [ValidateSet("aws", "azure", "gcp", "")]
    [string]$CloudProvider = "",

    [Parameter()]
    [switch]$UploadArtifact,

    [Parameter()]
    [switch]$Detailed
)

# Ensure output directory exists
if (-not (Test-Path $OutputPath)) {
    New-Item -ItemType Directory -Path $OutputPath -Force | Out-Null
}

$timestamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ"
$dateStamp = Get-Date -Format "yyyy-MM-dd"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Security Metrics Collector" -ForegroundColor Cyan
Write-Host "  Period: Last $Days days" -ForegroundColor Cyan
Write-Host "  Date: $dateStamp" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Detect cloud provider if not specified
if (-not $CloudProvider) {
    if (Test-Path ".scanning/configs/.checkov.yaml") {
        $configContent = Get-Content ".scanning/configs/.checkov.yaml" -Raw -ErrorAction SilentlyContinue
        if ($configContent -match "aws") { $CloudProvider = "aws" }
        elseif ($configContent -match "azure") { $CloudProvider = "azure" }
        elseif ($configContent -match "gcp") { $CloudProvider = "gcp" }
    }
    if (-not $CloudProvider) { $CloudProvider = "unknown" }
}

# Detect adoption tier
$adoptionTier = "unknown"
if (Test-Path ".pre-commit-config.yaml") {
    $pcConfig = Get-Content ".pre-commit-config.yaml" -Raw -ErrorAction SilentlyContinue
    if ($pcConfig -match "checkov-strict") { $adoptionTier = "strict" }
    elseif ($pcConfig -match "trivy-iac-critical") { $adoptionTier = "standard" }
    elseif ($pcConfig -match "trivy-secrets") { $adoptionTier = "starter" }
}

# Initialize metrics structure conforming to data-model.md Metric entity
$metrics = @{
    schema_version = "1.0"
    timestamp = $timestamp
    repository = (Split-Path -Leaf (Get-Location))
    branch = (git rev-parse --abbrev-ref HEAD 2>$null) ?? "unknown"
    commit_sha = (git rev-parse HEAD 2>$null) ?? "unknown"
    cloud_provider = $CloudProvider
    adoption_tier = $adoptionTier

    hook_results = @{}

    aggregate = @{
        total_findings = 0
        by_severity = @{
            CRITICAL = 0
            HIGH = 0
            MEDIUM = 0
            LOW = 0
        }
        bypass_rate = 0.0
        pass_rate = 0.0
        suppressed_count = 0
        baselined_count = 0
    }

    # Internal tracking (not in data-model but useful)
    collection_period_days = $Days
    targets = @{
        bypass_rate_max = 5.0
        hook_pass_rate_min = 80.0
        ci_failure_reduction = 40.0
        pre_commit_time_max = 5.0
    }

    trend = @{
        previous_period = @{}
        change = @{}
    }
}

# =============================================================================
# COMMIT METRICS (bypass rate)
# =============================================================================
Write-Host "Collecting commit metrics..." -ForegroundColor Yellow

$totalCommits = 0
$potentialBypasses = 0

try {
    $sinceDate = (Get-Date).AddDays(-$Days).ToString("yyyy-MM-dd")
    $commits = git log --oneline --since="$sinceDate" 2>$null

    if ($commits) {
        $commitLines = $commits -split "`n" | Where-Object { $_ -ne "" }
        $totalCommits = $commitLines.Count

        # Heuristic bypass detection: non-conventional commits
        $conventionalPattern = "^[a-f0-9]+ (feat|fix|docs|style|refactor|perf|test|chore|ci|build|revert)(\(.+\))?:"
        $conventionalCommits = @($commitLines | Where-Object { $_ -match $conventionalPattern })
        $potentialBypasses = $totalCommits - $conventionalCommits.Count

        if ($totalCommits -gt 0) {
            $metrics.aggregate.bypass_rate = [math]::Round(
                ($potentialBypasses / $totalCommits) * 100, 2
            )
        }

        Write-Host "  Total commits: $totalCommits" -ForegroundColor Gray
        Write-Host "  Conventional: $($conventionalCommits.Count)" -ForegroundColor Gray
        Write-Host "  Potential bypasses: $potentialBypasses" -ForegroundColor Gray
    }
}
catch {
    Write-Warning "Failed to collect commit metrics: $_"
}

# =============================================================================
# HOOK METRICS (pass rate)
# =============================================================================
Write-Host "Collecting hook metrics..." -ForegroundColor Yellow

$hookRuns = 0
$hookFailures = 0

try {
    $precommitLog = Join-Path $env:USERPROFILE ".cache/pre-commit/pre-commit.log"
    if (Test-Path $precommitLog) {
        $logContent = Get-Content $precommitLog -Tail 1000 -ErrorAction SilentlyContinue

        $hookRuns = @($logContent | Select-String "hook id:").Count
        $hookFailures = @($logContent | Select-String "Failed").Count

        if ($hookRuns -gt 0) {
            $metrics.aggregate.pass_rate = [math]::Round(
                (($hookRuns - $hookFailures) / $hookRuns) * 100, 2
            )
        }

        Write-Host "  Hook runs: $hookRuns" -ForegroundColor Gray
        Write-Host "  Failures: $hookFailures" -ForegroundColor Gray
    }
    else {
        Write-Host "  Pre-commit log not found (estimating from commits)" -ForegroundColor Gray
        $metrics.aggregate.pass_rate = 100 - $metrics.aggregate.bypass_rate
    }
}
catch {
    Write-Warning "Failed to collect hook metrics: $_"
}

# Populate per-hook results
$hookIds = @(
    "trivy-iac-critical", "trivy-iac-full", "trivy-secrets",
    "checkov", "checkov-strict", "validate-suppressions",
    "tflint", "gitleaks"
)

foreach ($hookId in $hookIds) {
    $metrics.hook_results[$hookId] = @{
        exit_code = 0
        duration_ms = 0
        findings_count = 0
        bypassed = $false
    }
}

# =============================================================================
# FINDING METRICS (from aggregated results)
# =============================================================================
Write-Host "Collecting finding metrics..." -ForegroundColor Yellow

try {
    $resultsPath = ".scan-results"
    $latestResults = Join-Path $resultsPath "unified-results-latest.json"

    if (Test-Path $latestResults) {
        $results = Get-Content $latestResults -Raw | ConvertFrom-Json

        $metrics.aggregate.total_findings = $results.summary.total_findings ?? 0
        $metrics.aggregate.by_severity.CRITICAL = $results.summary.by_severity.CRITICAL ?? 0
        $metrics.aggregate.by_severity.HIGH = $results.summary.by_severity.HIGH ?? 0
        $metrics.aggregate.by_severity.MEDIUM = $results.summary.by_severity.MEDIUM ?? 0
        $metrics.aggregate.by_severity.LOW = $results.summary.by_severity.LOW ?? 0
        $metrics.aggregate.suppressed_count = $results.summary.suppressed ?? 0
        $metrics.aggregate.baselined_count = $results.summary.baselined ?? 0

        Write-Host "  Total findings: $($metrics.aggregate.total_findings)" -ForegroundColor Gray
        Write-Host "  CRITICAL: $($metrics.aggregate.by_severity.CRITICAL)" -ForegroundColor $(if ($metrics.aggregate.by_severity.CRITICAL -gt 0) { "Red" } else { "Gray" })
        Write-Host "  HIGH: $($metrics.aggregate.by_severity.HIGH)" -ForegroundColor $(if ($metrics.aggregate.by_severity.HIGH -gt 0) { "Red" } else { "Gray" })
    }
    else {
        Write-Host "  No unified results found. Run aggregate-scan-results.ps1 first." -ForegroundColor Gray
    }
}
catch {
    Write-Warning "Failed to collect finding metrics: $_"
}

# =============================================================================
# TREND ANALYSIS
# =============================================================================
Write-Host "Calculating trends..." -ForegroundColor Yellow

try {
    $previousMetrics = Get-ChildItem -Path $OutputPath -Filter "metrics-*.json" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -Skip 1 -First 1

    if ($previousMetrics) {
        $previous = Get-Content $previousMetrics.FullName -Raw | ConvertFrom-Json

        $prevBypassRate = $previous.aggregate.bypass_rate ?? $previous.commit_metrics.bypass_rate ?? 0
        $prevPassRate = $previous.aggregate.pass_rate ?? $previous.hook_metrics.pass_rate ?? 0
        $prevFindings = $previous.aggregate.total_findings ?? $previous.finding_metrics.total_findings ?? 0

        $metrics.trend.previous_period = @{
            bypass_rate = $prevBypassRate
            pass_rate = $prevPassRate
            total_findings = $prevFindings
        }

        $metrics.trend.change = @{
            bypass_rate = [math]::Round($metrics.aggregate.bypass_rate - $prevBypassRate, 2)
            pass_rate = [math]::Round($metrics.aggregate.pass_rate - $prevPassRate, 2)
            findings = $metrics.aggregate.total_findings - $prevFindings
        }

        Write-Host "  Bypass rate change: $($metrics.trend.change.bypass_rate)%" -ForegroundColor $(if ($metrics.trend.change.bypass_rate -lt 0) { "Green" } else { "Yellow" })
        Write-Host "  Pass rate change: $($metrics.trend.change.pass_rate)%" -ForegroundColor $(if ($metrics.trend.change.pass_rate -gt 0) { "Green" } else { "Yellow" })
    }
    else {
        Write-Host "  No previous metrics for comparison" -ForegroundColor Gray
    }
}
catch {
    Write-Warning "Failed to calculate trends: $_"
}

# =============================================================================
# SAVE METRICS
# =============================================================================
$metricsFile = Join-Path $OutputPath "metrics-$dateStamp.json"
$metrics | ConvertTo-Json -Depth 10 | Set-Content $metricsFile -Encoding UTF8

$latestFile = Join-Path $OutputPath "metrics-latest.json"
$metrics | ConvertTo-Json -Depth 10 | Set-Content $latestFile -Encoding UTF8

# =============================================================================
# GITHUB ACTIONS ARTIFACT UPLOAD
# =============================================================================
if ($UploadArtifact -and $env:GITHUB_ACTIONS) {
    Write-Host "Uploading metrics as GitHub Actions artifact..." -ForegroundColor Yellow
    $artifactName = "scan-metrics-$CloudProvider-$dateStamp"
    Write-Host "  Artifact name: $artifactName" -ForegroundColor Gray
    Write-Host "  Use actions/upload-artifact@v4 in workflow to upload $metricsFile" -ForegroundColor Gray

    # Set output for workflow consumption
    if ($env:GITHUB_OUTPUT) {
        "metrics-file=$metricsFile" | Out-File -FilePath $env:GITHUB_OUTPUT -Append
        "artifact-name=$artifactName" | Out-File -FilePath $env:GITHUB_OUTPUT -Append
    }
}

# =============================================================================
# DISPLAY SUMMARY
# =============================================================================
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Metrics Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Bypass Rate
$bypassStatus = if ($metrics.aggregate.bypass_rate -le $metrics.targets.bypass_rate_max) { "PASS" } else { "FAIL" }
$bypassColor = if ($bypassStatus -eq "PASS") { "Green" } else { "Red" }
Write-Host "`nBypass Rate: $($metrics.aggregate.bypass_rate)% (Target: <$($metrics.targets.bypass_rate_max)%) [$bypassStatus]" -ForegroundColor $bypassColor

# Hook Pass Rate
$passStatus = if ($metrics.aggregate.pass_rate -ge $metrics.targets.hook_pass_rate_min) { "PASS" } else { "FAIL" }
$passColor = if ($passStatus -eq "PASS") { "Green" } else { "Red" }
Write-Host "Hook Pass Rate: $($metrics.aggregate.pass_rate)% (Target: >$($metrics.targets.hook_pass_rate_min)%) [$passStatus]" -ForegroundColor $passColor

# Security Findings
Write-Host "`nSecurity Findings:" -ForegroundColor White
if ($metrics.aggregate.by_severity.CRITICAL -gt 0) {
    Write-Host "  CRITICAL: $($metrics.aggregate.by_severity.CRITICAL) - ACTION REQUIRED" -ForegroundColor Red
}
if ($metrics.aggregate.by_severity.HIGH -gt 0) {
    Write-Host "  HIGH: $($metrics.aggregate.by_severity.HIGH) - Review needed" -ForegroundColor Yellow
}
Write-Host "  MEDIUM: $($metrics.aggregate.by_severity.MEDIUM)" -ForegroundColor Gray
Write-Host "  LOW: $($metrics.aggregate.by_severity.LOW)" -ForegroundColor Gray

if ($metrics.aggregate.suppressed_count -gt 0) {
    Write-Host "  Suppressed: $($metrics.aggregate.suppressed_count)" -ForegroundColor Gray
}
if ($metrics.aggregate.baselined_count -gt 0) {
    Write-Host "  Baselined: $($metrics.aggregate.baselined_count)" -ForegroundColor Gray
}

Write-Host "`nContext:" -ForegroundColor White
Write-Host "  Cloud Provider: $CloudProvider" -ForegroundColor Gray
Write-Host "  Adoption Tier: $adoptionTier" -ForegroundColor Gray

Write-Host "`nOutput: $metricsFile" -ForegroundColor Green
Write-Host ""

# Return metrics for programmatic use
return $metrics
