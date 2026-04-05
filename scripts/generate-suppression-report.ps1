<#
.SYNOPSIS
    Generates a comprehensive suppression audit report.

.DESCRIPTION
    This script analyzes the centralized suppression registry and generates
    reports for quarterly reviews and ongoing governance.

    Report includes:
    - Active suppressions by severity and tool
    - Suppressions expiring within specified days
    - Suppressions by owner
    - Historical trends (if data available)
    - Recommendations for review

.PARAMETER SuppressionFile
    Path to the suppression registry. Default: .scan-suppressions.yaml

.PARAMETER WarningDays
    Days before expiry to flag as "expiring soon". Default: 30

.PARAMETER OutputPath
    Directory to save reports. Default: .scan-results/reports

.PARAMETER Format
    Output format: text, json, or both. Default: both

.EXAMPLE
    .\generate-suppression-report.ps1
    Generates report with default settings.

.EXAMPLE
    .\generate-suppression-report.ps1 -WarningDays 60 -Format json
    Generates JSON report with 60-day warning threshold.

.NOTES
    Part of auto-code-scanning suppression governance framework.
    Run quarterly (every 90 days) for formal reviews, or monthly for monitoring.
    Conforms to suppression-format.md contract (schema v1.0).
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$SuppressionFile = ".scan-suppressions.yaml",

    [Parameter()]
    [int]$WarningDays = 30,

    [Parameter()]
    [string]$OutputPath = ".scan-results/reports",

    [Parameter()]
    [ValidateSet("text", "json", "both")]
    [string]$Format = "both"
)

# Ensure output directory exists
if (-not (Test-Path $OutputPath)) {
    New-Item -ItemType Directory -Path $OutputPath -Force | Out-Null
}

$timestamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ"
$dateStamp = Get-Date -Format "yyyy-MM-dd"
$today = Get-Date

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Suppression Report Generator" -ForegroundColor Cyan
Write-Host "  Date: $dateStamp" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Check file exists
if (-not (Test-Path $SuppressionFile)) {
    Write-Error "Suppression file not found: $SuppressionFile"
    exit 1
}

# Initialize report structure
$report = @{
    generated_at = $timestamp
    suppression_file = $SuppressionFile
    warning_days = $WarningDays

    summary = @{
        total_active = 0
        by_severity = @{
            CRITICAL = 0
            HIGH = 0
            MEDIUM = 0
            LOW = 0
        }
        by_tool = @{
            trivy = 0
            checkov = 0
            tflint = 0
        }
        expiring_soon = 0
        expired = 0
        history_count = 0
    }

    settings = @{
        max_expiry_days = 180
        review_frequency_days = 90
        require_security_approval = @("CRITICAL", "HIGH")
    }

    suppressions = @{
        active = @()
        expiring_soon = @()
        expired = @()
    }

    history = @()

    by_owner = @{}

    quarterly_review = @{
        last_review_due = ""
        next_review_due = ""
        overdue = $false
    }

    recommendations = @()
}

# Parse YAML (basic parsing)
Write-Host "Reading suppression file..." -ForegroundColor Yellow
$yamlContent = Get-Content $SuppressionFile -Raw

# Try using powershell-yaml if available
$suppressions = $null
if (Get-Module -ListAvailable -Name powershell-yaml) {
    Import-Module powershell-yaml
    $suppressions = ConvertFrom-Yaml $yamlContent
}

# Extract settings if available
if ($suppressions -and $suppressions["settings"]) {
    $settings = $suppressions["settings"]
    if ($settings.max_expiry_days) { $report.settings.max_expiry_days = $settings.max_expiry_days }
    if ($settings.review_frequency_days) { $report.settings.review_frequency_days = $settings.review_frequency_days }
    if ($settings.require_security_approval) { $report.settings.require_security_approval = $settings.require_security_approval }
}

# Calculate quarterly review dates
$reviewFrequency = $report.settings.review_frequency_days
$report.quarterly_review.next_review_due = $today.AddDays($reviewFrequency).ToString("yyyy-MM-dd")
$report.quarterly_review.last_review_due = $today.AddDays(-$reviewFrequency).ToString("yyyy-MM-dd")

# Process suppression history
if ($suppressions -and $suppressions["suppression_history"]) {
    foreach ($histEntry in $suppressions["suppression_history"]) {
        if ($histEntry -is [hashtable] -and $histEntry.rule_id) {
            $report.history += @{
                rule_id = $histEntry.rule_id
                tool = $histEntry.tool
                removed_date = $histEntry.removed_date
                removal_reason = $histEntry.removal_reason
                original_approved_date = $histEntry.original_approved_date
            }
            $report.summary.history_count++
        }
    }
}

# Process each suppression section
$allSuppressions = @()

foreach ($section in @("trivy_suppressions", "checkov_suppressions", "tflint_suppressions")) {
    $toolName = $section -replace "_suppressions", ""

    if ($suppressions -and $suppressions[$section]) {
        foreach ($supp in $suppressions[$section]) {
            if ($supp -is [hashtable] -and $supp.rule_id) {
                $suppEntry = @{
                    rule_id = $supp.rule_id
                    tool = $toolName
                    severity = $supp.severity ?? "MEDIUM"
                    reason = $supp.reason
                    owner = $supp.owner
                    approved_date = $supp.approved_date
                    expires_date = $supp.expires_date
                    file_pattern = $supp.file_pattern
                    approved_by = $supp.approved_by
                    ticket = $supp.ticket
                }

                # Determine status
                $status = "active"
                $daysUntilExpiry = $null

                if ($supp.expires_date) {
                    try {
                        $expiresDate = [DateTime]::Parse($supp.expires_date)
                        $daysUntilExpiry = ($expiresDate - $today).Days

                        if ($daysUntilExpiry -lt 0) {
                            $status = "expired"
                            $report.summary.expired++
                        }
                        elseif ($daysUntilExpiry -le $WarningDays) {
                            $status = "expiring_soon"
                            $report.summary.expiring_soon++
                        }
                    }
                    catch {
                        # Invalid date
                    }
                }

                $suppEntry.status = $status
                $suppEntry.days_until_expiry = $daysUntilExpiry

                $allSuppressions += $suppEntry

                # Update summary
                $report.summary.total_active++
                if ($report.summary.by_severity.ContainsKey($suppEntry.severity)) {
                    $report.summary.by_severity[$suppEntry.severity]++
                }
                $report.summary.by_tool[$toolName]++

                # Track by owner
                $owner = $suppEntry.owner ?? "unknown"
                if (-not $report.by_owner.ContainsKey($owner)) {
                    $report.by_owner[$owner] = 0
                }
                $report.by_owner[$owner]++

                # Categorize
                $report.suppressions[$status] += $suppEntry
            }
        }
    }
}

# Generate recommendations
if ($report.summary.expired -gt 0) {
    $report.recommendations += "URGENT: $($report.summary.expired) suppression(s) have expired and require immediate review"
}

if ($report.summary.expiring_soon -gt 0) {
    $report.recommendations += "WARNING: $($report.summary.expiring_soon) suppression(s) expire within $WarningDays days"
}

if ($report.summary.by_severity.CRITICAL -gt 0) {
    $report.recommendations += "REVIEW: $($report.summary.by_severity.CRITICAL) CRITICAL severity suppression(s) require weekly review"
}

if ($report.summary.by_severity.HIGH -gt 0) {
    $report.recommendations += "REVIEW: $($report.summary.by_severity.HIGH) HIGH severity suppression(s) require monthly review"
}

if ($report.summary.total_active -gt 20) {
    $report.recommendations += "GOVERNANCE: High suppression count ($($report.summary.total_active)). Consider addressing root causes."
}

if ($report.summary.history_count -gt 0) {
    $report.recommendations += "AUDIT: $($report.summary.history_count) historical suppression(s) on record"
}

# Check for missing approved_by on HIGH/CRITICAL
foreach ($supp in $allSuppressions) {
    $sev = $supp.severity
    if ($sev -in $report.settings.require_security_approval -and -not $supp.approved_by) {
        $report.recommendations += "COMPLIANCE: $($supp.rule_id) ($sev) is missing required 'approved_by' field"
    }
}

# Output text report
if ($Format -in @("text", "both")) {
    $textReport = @"
================================================================================
                        SUPPRESSION AUDIT REPORT
                        Generated: $dateStamp
================================================================================

SUMMARY
--------------------------------------------------------------------------------
Total Active Suppressions: $($report.summary.total_active)

By Severity:
  CRITICAL: $($report.summary.by_severity.CRITICAL)
  HIGH:     $($report.summary.by_severity.HIGH)
  MEDIUM:   $($report.summary.by_severity.MEDIUM)
  LOW:      $($report.summary.by_severity.LOW)

By Tool:
  Trivy:    $($report.summary.by_tool.trivy)
  Checkov:  $($report.summary.by_tool.checkov)
  tflint:   $($report.summary.by_tool.tflint)

Status:
  Expired:       $($report.summary.expired)
  Expiring Soon: $($report.summary.expiring_soon) (within $WarningDays days)

History:
  Removed suppressions: $($report.summary.history_count)

Quarterly Review:
  Review frequency: $($report.settings.review_frequency_days) days
  Next review due: $($report.quarterly_review.next_review_due)

By Owner:
"@

    foreach ($owner in $report.by_owner.Keys | Sort-Object) {
        $textReport += "`n  $owner`: $($report.by_owner[$owner])"
    }

    if ($report.suppressions.expired.Count -gt 0) {
        $textReport += @"


EXPIRED SUPPRESSIONS (IMMEDIATE ACTION REQUIRED)
--------------------------------------------------------------------------------
"@
        foreach ($supp in $report.suppressions.expired) {
            $textReport += "`n- $($supp.rule_id) ($($supp.tool)) - Expired: $($supp.expires_date)"
            $textReport += "`n  Owner: $($supp.owner)"
            $textReport += "`n  Reason: $($supp.reason)"
            $textReport += "`n"
        }
    }

    if ($report.suppressions.expiring_soon.Count -gt 0) {
        $textReport += @"


EXPIRING SOON (WITHIN $WarningDays DAYS)
--------------------------------------------------------------------------------
"@
        foreach ($supp in $report.suppressions.expiring_soon) {
            $textReport += "`n- $($supp.rule_id) ($($supp.tool)) - Expires: $($supp.expires_date) ($($supp.days_until_expiry) days)"
            $textReport += "`n  Owner: $($supp.owner)"
            $textReport += "`n  Reason: $($supp.reason)"
            $textReport += "`n"
        }
    }

    if ($report.recommendations.Count -gt 0) {
        $textReport += @"


RECOMMENDATIONS
--------------------------------------------------------------------------------
"@
        foreach ($rec in $report.recommendations) {
            $textReport += "`n- $rec"
        }
    }

    $textReport += @"


================================================================================
                              END OF REPORT
================================================================================
"@

    # Display to console
    Write-Host $textReport

    # Save to file
    $textFile = Join-Path $OutputPath "suppression-report-$dateStamp.txt"
    $textReport | Set-Content $textFile -Encoding UTF8
    Write-Host "`nText report saved: $textFile" -ForegroundColor Green
}

# Output JSON report
if ($Format -in @("json", "both")) {
    $jsonFile = Join-Path $OutputPath "suppression-report-$dateStamp.json"
    $report | ConvertTo-Json -Depth 10 | Set-Content $jsonFile -Encoding UTF8
    Write-Host "JSON report saved: $jsonFile" -ForegroundColor Green

    # Also save as latest
    $latestFile = Join-Path $OutputPath "suppression-report-latest.json"
    $report | ConvertTo-Json -Depth 10 | Set-Content $latestFile -Encoding UTF8
}

Write-Host ""

# Return report object for programmatic use
return $report
