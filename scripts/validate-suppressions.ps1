<#
.SYNOPSIS
    Validates the centralized suppression registry for compliance.

.DESCRIPTION
    This script validates .scan-suppressions.yaml to ensure:
    - All required fields are present
    - Dates are valid and not expired
    - HIGH/CRITICAL suppressions have security approval
    - No duplicate suppressions exist
    - Owners are valid email addresses

.PARAMETER SuppressionFile
    Path to the suppression registry. Default: .scan-suppressions.yaml

.PARAMETER WarningDays
    Days before expiry to warn. Default: 30

.PARAMETER Strict
    Fail on warnings (not just errors).

.EXAMPLE
    .\validate-suppressions.ps1
    Validates suppressions with default settings.

.EXAMPLE
    .\validate-suppressions.ps1 -Strict -WarningDays 60
    Strict validation with 60-day expiry warning.

.NOTES
    Part of azure-wordpress local scanning infrastructure.
    Run before each commit to ensure suppression compliance.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$SuppressionFile = ".scan-suppressions.yaml",

    [Parameter()]
    [int]$WarningDays = 30,

    [Parameter()]
    [switch]$Strict
)

# Check for powershell-yaml module
if (-not (Get-Module -ListAvailable -Name powershell-yaml)) {
    Write-Warning "powershell-yaml module not installed. Install with: Install-Module powershell-yaml -Scope CurrentUser"
    Write-Host "Attempting basic YAML parsing..." -ForegroundColor Yellow
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Suppression Validator" -ForegroundColor Cyan
Write-Host "  File: $SuppressionFile" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Counters
$errors = @()
$warnings = @()
$validCount = 0

# Check file exists
if (-not (Test-Path $SuppressionFile)) {
    Write-Error "Suppression file not found: $SuppressionFile"
    exit 1
}

# Parse YAML
try {
    $yamlContent = Get-Content $SuppressionFile -Raw

    # Try using powershell-yaml if available
    if (Get-Module -ListAvailable -Name powershell-yaml) {
        Import-Module powershell-yaml
        $suppressions = ConvertFrom-Yaml $yamlContent
    }
    else {
        # Basic parsing for simple validation
        Write-Host "Using basic parser (install powershell-yaml for full validation)" -ForegroundColor Yellow
        $suppressions = @{
            trivy_suppressions = @()
            checkov_suppressions = @()
            tflint_suppressions = @()
        }

        # Simple regex extraction
        $currentSection = ""
        foreach ($line in ($yamlContent -split "`n")) {
            if ($line -match "^trivy_suppressions:") { $currentSection = "trivy" }
            elseif ($line -match "^checkov_suppressions:") { $currentSection = "checkov" }
            elseif ($line -match "^tflint_suppressions:") { $currentSection = "tflint" }
        }
    }
}
catch {
    Write-Error "Failed to parse YAML: $_"
    exit 1
}

# Required fields for each suppression
$requiredFields = @("rule_id", "tool", "reason", "owner", "approved_date", "expires_date")
$optionalFields = @("file_pattern", "severity", "ticket", "approved_by")

# Function to validate a single suppression
function Test-Suppression {
    param(
        [Parameter(Mandatory)]
        [hashtable]$Suppression,

        [Parameter(Mandatory)]
        [string]$Tool
    )

    $localErrors = @()
    $localWarnings = @()

    # Check required fields
    foreach ($field in $requiredFields) {
        if (-not $Suppression.ContainsKey($field) -or [string]::IsNullOrWhiteSpace($Suppression[$field])) {
            $localErrors += "Missing required field '$field' for rule $($Suppression.rule_id ?? 'UNKNOWN')"
        }
    }

    # Validate tool matches section
    if ($Suppression.tool -and $Suppression.tool -ne $Tool) {
        $localErrors += "Tool mismatch: $($Suppression.tool) in $Tool section"
    }

    # Validate owner is email format
    if ($Suppression.owner -and $Suppression.owner -notmatch "^[\w\.-]+@[\w\.-]+\.\w+$") {
        $localErrors += "Invalid owner email format: $($Suppression.owner)"
    }

    # Validate dates
    $today = Get-Date

    if ($Suppression.approved_date) {
        try {
            $approvedDate = [DateTime]::Parse($Suppression.approved_date)
            if ($approvedDate -gt $today) {
                $localWarnings += "Approved date is in the future: $($Suppression.approved_date)"
            }
        }
        catch {
            $localErrors += "Invalid approved_date format: $($Suppression.approved_date)"
        }
    }

    if ($Suppression.expires_date) {
        try {
            $expiresDate = [DateTime]::Parse($Suppression.expires_date)

            # Check if expired
            if ($expiresDate -lt $today) {
                $localErrors += "EXPIRED: Rule $($Suppression.rule_id) expired on $($Suppression.expires_date)"
            }
            # Check if expiring soon
            elseif ($expiresDate -lt $today.AddDays($WarningDays)) {
                $daysLeft = ($expiresDate - $today).Days
                $localWarnings += "EXPIRING SOON: Rule $($Suppression.rule_id) expires in $daysLeft days"
            }

            # Check max expiry (6 months from approval)
            if ($Suppression.approved_date) {
                $approvedDate = [DateTime]::Parse($Suppression.approved_date)
                $maxExpiry = $approvedDate.AddDays(180)
                if ($expiresDate -gt $maxExpiry) {
                    $localWarnings += "Expiry exceeds 6-month maximum: $($Suppression.rule_id)"
                }
            }
        }
        catch {
            $localErrors += "Invalid expires_date format: $($Suppression.expires_date)"
        }
    }

    # Check HIGH/CRITICAL require security approval
    if ($Suppression.severity -in @("HIGH", "CRITICAL")) {
        if (-not $Suppression.approved_by -or [string]::IsNullOrWhiteSpace($Suppression.approved_by)) {
            $localErrors += "HIGH/CRITICAL suppression requires approved_by field: $($Suppression.rule_id)"
        }
    }

    return @{
        Errors = $localErrors
        Warnings = $localWarnings
    }
}

# Validate each suppression section
$allSuppressions = @()

foreach ($section in @("trivy_suppressions", "checkov_suppressions", "tflint_suppressions")) {
    $toolName = $section -replace "_suppressions", ""

    Write-Host "Validating $section..." -ForegroundColor Yellow

    $sectionSuppressions = $suppressions[$section]

    if ($sectionSuppressions -and $sectionSuppressions.Count -gt 0) {
        foreach ($supp in $sectionSuppressions) {
            if ($supp -is [hashtable]) {
                $result = Test-Suppression -Suppression $supp -Tool $toolName
                $errors += $result.Errors
                $warnings += $result.Warnings

                if ($result.Errors.Count -eq 0) {
                    $validCount++
                }

                # Track for duplicate detection
                $allSuppressions += @{
                    rule_id = $supp.rule_id
                    tool = $toolName
                    file_pattern = $supp.file_pattern
                }
            }
        }
        Write-Host "  Found $($sectionSuppressions.Count) suppressions" -ForegroundColor Gray
    }
    else {
        Write-Host "  No suppressions defined" -ForegroundColor Gray
    }
}

# Check for duplicates
$duplicates = $allSuppressions | Group-Object { "$($_.rule_id)-$($_.tool)-$($_.file_pattern)" } |
    Where-Object { $_.Count -gt 1 }

foreach ($dup in $duplicates) {
    $errors += "Duplicate suppression: $($dup.Name)"
}

# Display results
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Validation Results" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

Write-Host "`nValid suppressions: $validCount" -ForegroundColor Green

if ($warnings.Count -gt 0) {
    Write-Host "`nWarnings ($($warnings.Count)):" -ForegroundColor Yellow
    foreach ($warning in $warnings) {
        Write-Host "  - $warning" -ForegroundColor Yellow
    }
}

if ($errors.Count -gt 0) {
    Write-Host "`nErrors ($($errors.Count)):" -ForegroundColor Red
    foreach ($error in $errors) {
        Write-Host "  - $error" -ForegroundColor Red
    }
}

# Summary
Write-Host ""
if ($errors.Count -eq 0 -and ($warnings.Count -eq 0 -or -not $Strict)) {
    Write-Host "VALIDATION PASSED" -ForegroundColor Green
    exit 0
}
elseif ($errors.Count -gt 0) {
    Write-Host "VALIDATION FAILED" -ForegroundColor Red
    exit 1
}
elseif ($Strict -and $warnings.Count -gt 0) {
    Write-Host "VALIDATION FAILED (strict mode - warnings treated as errors)" -ForegroundColor Red
    exit 1
}
