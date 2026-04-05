<#
.SYNOPSIS
    Creates a baseline snapshot of current scan findings for new-only reporting.

.DESCRIPTION
    Creates a baseline of current security scan findings so subsequent scans
    report only NEW findings. This enables teams adopting scanning on existing
    codebases to focus on preventing new issues while gradually addressing debt.

    Baseline matching uses (rule_id, file_path) tuples with SHA-256 hashing
    for O(1) lookup. Line numbers are intentionally excluded to be resilient
    to code refactoring.

    Output conforms to the Baseline entity schema in data-model.md.

.PARAMETER Tool
    Which scanning tool to baseline. Default: all

.PARAMETER OutputDir
    Directory to store baseline files. Default: .scan-baseline

.PARAMETER TerraformDir
    Directory containing Terraform code to scan. Default: .

.PARAMETER CloudProvider
    Cloud provider for context. Default: auto-detected.

.PARAMETER MonorepoScope
    Scope baseline to specific Terraform modules/directories (comma-separated).
    Example: "terraform/modules/networking,terraform/modules/compute"

.PARAMETER Force
    Overwrite existing baseline without prompting.

.EXAMPLE
    .\create-baseline.ps1
    Creates baseline for all tools in the current directory.

.EXAMPLE
    .\create-baseline.ps1 -Tool trivy -CloudProvider aws -Force
    Creates Trivy-only baseline with AWS context, overwriting existing.

.EXAMPLE
    .\create-baseline.ps1 -MonorepoScope "terraform/networking,terraform/compute"
    Creates scoped baseline for specific monorepo modules.

.NOTES
    Part of auto-code-scanning infrastructure.
    Baseline matching: SHA-256(rule_id + "|" + file_path) per FR-074b.
    Staleness warning at 90 days per FR-072.
#>

[CmdletBinding()]
param(
    [ValidateSet("trivy", "checkov", "tflint", "all")]
    [string]$Tool = "all",

    [string]$OutputDir = ".scan-baseline",

    [string]$TerraformDir = ".",

    [ValidateSet("aws", "azure", "gcp", "")]
    [string]$CloudProvider = "",

    [string]$MonorepoScope = "",

    [switch]$Force
)

$ErrorActionPreference = "Stop"

# Create output directory
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$timestamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ"
$dateStamp = Get-Date -Format "yyyy-MM-dd"

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

# Parse monorepo scope
$scopedDirs = @()
if ($MonorepoScope) {
    $scopedDirs = $MonorepoScope -split "," | ForEach-Object { $_.Trim() }
}

# SHA-256 hash function for baseline matching per FR-074b
function Get-BaselineHash {
    param(
        [string]$RuleId,
        [string]$FilePath
    )
    $input_string = "$RuleId|$FilePath"
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($input_string)
    $hash = $sha256.ComputeHash($bytes)
    return [System.BitConverter]::ToString($hash).Replace("-", "").ToLower()
}

# Initialize baseline structure per data-model.md Baseline entity
$baseline = @{
    schema_version = "1.0"
    created_date = $timestamp
    created_by = "create-baseline.ps1"
    cloud_provider = $CloudProvider
    scoped_directories = $scopedDirs
    entries = @()
}

function New-TrivyBaseline {
    Write-Host "Creating Trivy baseline..." -ForegroundColor Cyan

    if (-not (Get-Command trivy -ErrorAction SilentlyContinue)) {
        Write-Warning "Trivy not found. Skipping Trivy baseline."
        return @()
    }

    $scanDirs = if ($scopedDirs.Count -gt 0) { $scopedDirs } else { @($TerraformDir) }
    $entries = @()

    foreach ($dir in $scanDirs) {
        $trivyJson = trivy config $dir --severity CRITICAL,HIGH,MEDIUM,LOW --format json --quiet 2>$null
        if ($trivyJson) {
            try {
                $trivyResults = $trivyJson | ConvertFrom-Json
                foreach ($result in $trivyResults.Results) {
                    foreach ($misconfig in $result.Misconfigurations) {
                        $ruleId = $misconfig.AVDID ?? $misconfig.ID
                        $filePath = $result.Target
                        $entries += @{
                            hash = Get-BaselineHash $ruleId $filePath
                            rule_id = $ruleId
                            file_path = $filePath
                            tool = "trivy"
                            severity = $misconfig.Severity
                            baselined_date = $dateStamp
                        }
                    }
                }
            }
            catch {
                Write-Warning "Failed to parse Trivy output for $dir`: $_"
            }
        }
    }

    Write-Host "  Trivy: $($entries.Count) findings baselined" -ForegroundColor Gray
    return $entries
}

function New-CheckovBaseline {
    Write-Host "Creating Checkov baseline..." -ForegroundColor Cyan

    if (-not (Get-Command checkov -ErrorAction SilentlyContinue)) {
        Write-Warning "Checkov not found. Skipping Checkov baseline."
        return @()
    }

    $scanDirs = if ($scopedDirs.Count -gt 0) { $scopedDirs } else { @($TerraformDir) }
    $entries = @()

    foreach ($dir in $scanDirs) {
        $checkovJson = checkov -d $dir --framework terraform --output json --quiet --compact 2>$null
        if ($checkovJson) {
            try {
                $checkovResults = $checkovJson | ConvertFrom-Json
                foreach ($check in $checkovResults.results.failed_checks) {
                    $ruleId = $check.check_id
                    $filePath = $check.file_path
                    $entries += @{
                        hash = Get-BaselineHash $ruleId $filePath
                        rule_id = $ruleId
                        file_path = $filePath
                        tool = "checkov"
                        severity = $check.severity ?? "MEDIUM"
                        baselined_date = $dateStamp
                    }
                }
            }
            catch {
                Write-Warning "Failed to parse Checkov output for $dir`: $_"
            }
        }
    }

    Write-Host "  Checkov: $($entries.Count) findings baselined" -ForegroundColor Gray
    return $entries
}

function New-TflintBaseline {
    Write-Host "Creating tflint baseline..." -ForegroundColor Cyan

    if (-not (Get-Command tflint -ErrorAction SilentlyContinue)) {
        Write-Warning "tflint not found. Skipping tflint baseline."
        return @()
    }

    $scanDirs = if ($scopedDirs.Count -gt 0) { $scopedDirs } else { @($TerraformDir) }
    $entries = @()

    foreach ($dir in $scanDirs) {
        $tflintJson = tflint --format json $dir 2>$null
        if ($tflintJson) {
            try {
                $tflintResults = $tflintJson | ConvertFrom-Json
                foreach ($issue in $tflintResults.issues) {
                    $ruleId = $issue.rule.name
                    $filePath = $issue.range.filename
                    $entries += @{
                        hash = Get-BaselineHash $ruleId $filePath
                        rule_id = $ruleId
                        file_path = $filePath
                        tool = "tflint"
                        severity = $issue.rule.severity
                        baselined_date = $dateStamp
                    }
                }
            }
            catch {
                Write-Warning "Failed to parse tflint output for $dir`: $_"
            }
        }
    }

    Write-Host "  tflint: $($entries.Count) findings baselined" -ForegroundColor Gray
    return $entries
}

# Check for existing baseline
$metadataFile = Join-Path $OutputDir "baseline.json"
if ((Test-Path $metadataFile) -and -not $Force) {
    # Check staleness of existing baseline (90-day warning per FR-072)
    try {
        $existingBaseline = Get-Content $metadataFile -Raw | ConvertFrom-Json
        $createdDate = [DateTime]::Parse($existingBaseline.created_date)
        $daysOld = ((Get-Date) - $createdDate).Days
        if ($daysOld -gt 90) {
            Write-Warning "Existing baseline is $daysOld days old (>90 days). Consider refreshing with -Force."
        }
    }
    catch {}

    Write-Warning "Baseline already exists at $OutputDir. Use -Force to overwrite."
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor White
Write-Host " Creating Scan Baseline" -ForegroundColor White
Write-Host "========================================" -ForegroundColor White
Write-Host " Cloud Provider: $CloudProvider" -ForegroundColor Gray
if ($scopedDirs.Count -gt 0) {
    Write-Host " Monorepo Scope: $($scopedDirs -join ', ')" -ForegroundColor Gray
}
Write-Host ""

# Collect baseline entries
$allEntries = @()

switch ($Tool) {
    "trivy"   { $allEntries += New-TrivyBaseline }
    "checkov" { $allEntries += New-CheckovBaseline }
    "tflint"  { $allEntries += New-TflintBaseline }
    "all" {
        $allEntries += New-TrivyBaseline
        $allEntries += New-CheckovBaseline
        $allEntries += New-TflintBaseline
    }
}

$baseline.entries = $allEntries

# Deduplicate by hash (same rule+file from different scan runs)
$uniqueHashes = @{}
$dedupedEntries = @()
foreach ($entry in $allEntries) {
    if (-not $uniqueHashes.ContainsKey($entry.hash)) {
        $uniqueHashes[$entry.hash] = $true
        $dedupedEntries += $entry
    }
}
$baseline.entries = $dedupedEntries

# Save baseline as single JSON file
$baseline | ConvertTo-Json -Depth 10 | Set-Content $metadataFile -Encoding UTF8

# Summary
$bySeverity = @{ CRITICAL = 0; HIGH = 0; MEDIUM = 0; LOW = 0 }
foreach ($entry in $dedupedEntries) {
    $sev = $entry.severity.ToUpper()
    if ($bySeverity.ContainsKey($sev)) { $bySeverity[$sev]++ }
}

$byTool = @{}
foreach ($entry in $dedupedEntries) {
    $t = $entry.tool
    if (-not $byTool.ContainsKey($t)) { $byTool[$t] = 0 }
    $byTool[$t]++
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " Baseline Created Successfully" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Location: $metadataFile" -ForegroundColor White
Write-Host "  Total entries: $($dedupedEntries.Count)" -ForegroundColor White
Write-Host "  Created: $timestamp" -ForegroundColor White
Write-Host ""
Write-Host "  By Severity:" -ForegroundColor White
Write-Host "    CRITICAL: $($bySeverity.CRITICAL)" -ForegroundColor $(if ($bySeverity.CRITICAL -gt 0) { "Red" } else { "Gray" })
Write-Host "    HIGH:     $($bySeverity.HIGH)" -ForegroundColor $(if ($bySeverity.HIGH -gt 0) { "Yellow" } else { "Gray" })
Write-Host "    MEDIUM:   $($bySeverity.MEDIUM)" -ForegroundColor Gray
Write-Host "    LOW:      $($bySeverity.LOW)" -ForegroundColor Gray
Write-Host ""
Write-Host "  By Tool:" -ForegroundColor White
foreach ($t in $byTool.Keys) {
    Write-Host "    $t`: $($byTool[$t])" -ForegroundColor Gray
}
Write-Host ""
Write-Host "Matching algorithm: SHA-256(rule_id | file_path)" -ForegroundColor Gray
Write-Host "Line numbers excluded for refactoring resilience." -ForegroundColor Gray
Write-Host ""
Write-Host "Baseline will expire in 90 days ($((Get-Date).AddDays(90).ToString('yyyy-MM-dd')))" -ForegroundColor Yellow
Write-Host "Use -Force to refresh the baseline when needed." -ForegroundColor Yellow
Write-Host ""
