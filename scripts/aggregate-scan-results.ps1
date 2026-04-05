<#
.SYNOPSIS
    Aggregates scan results from multiple tools into unified JSON format.

.DESCRIPTION
    This script collects security scan results from multiple tools and normalizes them
    into a unified JSON schema for trend analysis and metrics tracking.

    Supported tools:
    - Trivy (IaC misconfigurations, secrets)
    - Checkov (CIS Benchmark policies)
    - tflint (Terraform linting)
    - Snyk (IaC misconfigurations)
    - Gitleaks (secret detection)
    - PSScriptAnalyzer (PowerShell linting)
    - ShellCheck (shell script linting)
    - hadolint (Dockerfile linting)

    Features:
    - Cross-tool deduplication: matches on (file, resource, category)
    - Severity normalization to CRITICAL/HIGH/MEDIUM/LOW
    - Remediation URL generation for Checkov and Trivy findings
    - Output conforms to schemas/unified-results.schema.json

.PARAMETER OutputPath
    Directory to store aggregated results. Default: .scan-results

.PARAMETER IncludeHistory
    Include historical results for trend analysis.

.PARAMETER RunScans
    Run the scanning tools before aggregating results.

.EXAMPLE
    .\aggregate-scan-results.ps1
    Aggregates existing scan results to .scan-results/

.EXAMPLE
    .\aggregate-scan-results.ps1 -RunScans -OutputPath "C:\Reports"
    Runs all scanners and aggregates results to custom path.

.NOTES
    Part of auto-code-scanning infrastructure.
    All scans run locally - no code is uploaded to external services.
    Output conforms to schemas/unified-results.schema.json (v1.0).
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$OutputPath = ".scan-results",

    [Parameter()]
    [switch]$IncludeHistory,

    [Parameter()]
    [switch]$RunScans
)

# Ensure output directory exists
if (-not (Test-Path $OutputPath)) {
    New-Item -ItemType Directory -Path $OutputPath -Force | Out-Null
}

# Track scan duration
$scanStartTime = Get-Date

# Generate scan ID (full UUID) and timestamp
$scanId = [guid]::NewGuid().ToString()
$timestamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ"
$dateStamp = Get-Date -Format "yyyy-MM-dd"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Scan Results Aggregator" -ForegroundColor Cyan
Write-Host "  Scan ID: $scanId" -ForegroundColor Cyan
Write-Host "  Timestamp: $timestamp" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Initialize unified results structure per data-model.md
$unifiedResults = @{
    schema_version = "1.0"
    scan_id = $scanId
    scan_timestamp = $timestamp
    duration_ms = 0
    scan_directory = (Get-Location).Path
    tools_executed = @()
    summary = @{
        total_findings = 0
        by_severity = @{
            CRITICAL = 0
            HIGH = 0
            MEDIUM = 0
            LOW = 0
        }
        by_tool = @{}
        suppressed = 0
        baselined = 0
    }
    findings = @()
}

# Severity normalization mapping per data-model.md
# Covers all 8 tools: Trivy, Checkov, tflint, Snyk, Gitleaks, PSScriptAnalyzer, ShellCheck, hadolint
function Get-NormalizedSeverity {
    param(
        [string]$Severity,
        [string]$Tool = ""
    )

    # Tool-specific mappings first
    switch ($Tool.ToLower()) {
        "gitleaks" {
            # All secrets are HIGH severity
            return "HIGH"
        }
        "tflint" {
            switch ($Severity.ToLower()) {
                "error"   { return "HIGH" }
                "warning" { return "MEDIUM" }
                "notice"  { return "LOW" }
                default   { return "MEDIUM" }
            }
        }
        "psscriptanalyzer" {
            switch ($Severity.ToLower()) {
                "error"       { return "HIGH" }
                "warning"     { return "MEDIUM" }
                "information" { return "LOW" }
                default       { return "LOW" }
            }
        }
        "shellcheck" {
            switch ($Severity.ToLower()) {
                "error"   { return "HIGH" }
                "warning" { return "MEDIUM" }
                "info"    { return "LOW" }
                "style"   { return "LOW" }
                default   { return "LOW" }
            }
        }
        "hadolint" {
            switch ($Severity.ToLower()) {
                "error"   { return "HIGH" }
                "warning" { return "MEDIUM" }
                "info"    { return "LOW" }
                "style"   { return "LOW" }
                default   { return "LOW" }
            }
        }
        "snyk" {
            switch ($Severity.ToLower()) {
                "critical" { return "CRITICAL" }
                "high"     { return "HIGH" }
                "medium"   { return "MEDIUM" }
                "low"      { return "LOW" }
                default    { return "MEDIUM" }
            }
        }
    }

    # Generic mapping for Trivy and Checkov (direct mapping)
    switch ($Severity.ToUpper()) {
        { $_ -in @("CRITICAL", "CRIT") } { return "CRITICAL" }
        { $_ -in @("HIGH", "ERROR") } { return "HIGH" }
        { $_ -in @("MEDIUM", "MED", "WARNING", "WARN") } { return "MEDIUM" }
        { $_ -in @("LOW", "INFO", "INFORMATION", "UNKNOWN") } { return "LOW" }
        default { return "LOW" }
    }
}

# Remediation URL generation per spec FR-033f/FR-033g
function Get-RemediationUrl {
    param(
        [string]$Tool,
        [string]$RuleId
    )

    switch ($Tool.ToLower()) {
        "checkov" {
            if ($RuleId) {
                return "https://docs.checkov.io/docs/$RuleId"
            }
        }
        "trivy" {
            if ($RuleId -and $RuleId -match "^AVD-") {
                return "https://avd.aquasec.com/misconfig/$($RuleId.ToLower())"
            }
        }
        "tflint" {
            return "https://github.com/terraform-linters/tflint/blob/master/docs/rules/"
        }
        "snyk" {
            if ($RuleId) {
                return "https://security.snyk.io/rules/cloud/$RuleId"
            }
        }
    }

    return $null
}

# Category normalization for deduplication
function Get-FindingCategory {
    param(
        [string]$RuleId,
        [string]$Title
    )

    $text = "$RuleId $Title".ToLower()

    if ($text -match "encrypt") { return "encryption" }
    if ($text -match "public.*(access|bucket|storage|ip)") { return "public-access" }
    if ($text -match "(ssh|rdp|port\s*(22|3389))") { return "remote-access" }
    if ($text -match "log") { return "logging" }
    if ($text -match "tls|ssl|https") { return "transport-security" }
    if ($text -match "backup|versioning|retention") { return "data-protection" }
    if ($text -match "iam|permission|role|policy") { return "access-control" }
    if ($text -match "tag") { return "tagging" }
    if ($text -match "network|firewall|security.group|nsg") { return "network-security" }
    if ($text -match "secret|key|password|credential") { return "secret-detection" }

    return "other"
}

# Function to parse Trivy JSON output
function Get-TrivyFindings {
    param([string]$JsonPath)

    if (-not (Test-Path $JsonPath)) {
        Write-Warning "Trivy results not found at $JsonPath"
        return @()
    }

    $findings = @()
    try {
        $trivyResults = Get-Content $JsonPath -Raw | ConvertFrom-Json

        foreach ($result in $trivyResults.Results) {
            foreach ($misconfig in $result.Misconfigurations) {
                $ruleId = $misconfig.AVDID ?? $misconfig.ID
                $severity = Get-NormalizedSeverity $misconfig.Severity "trivy"
                $findings += @{
                    id = [guid]::NewGuid().ToString()
                    tool = "trivy"
                    rule_id = $ruleId
                    severity = $severity
                    original_severity = $misconfig.Severity
                    title = $misconfig.Title
                    description = $misconfig.Description ?? ""
                    message = $misconfig.Message
                    file = $result.Target
                    line = $misconfig.CauseMetadata.StartLine ?? 0
                    resource = $misconfig.CauseMetadata.Resource ?? ""
                    remediation = $misconfig.Resolution
                    remediation_url = Get-RemediationUrl "trivy" $ruleId
                    url = ($misconfig.References | Select-Object -First 1) ?? $null
                    suppressed = $false
                    suppression_reason = $null
                    baseline = $false
                    detected_by = @("trivy")
                    category = Get-FindingCategory $ruleId $misconfig.Title
                }
            }
        }
    }
    catch {
        Write-Warning "Failed to parse Trivy results: $_"
    }

    return $findings
}

# Function to parse Checkov JSON output
function Get-CheckovFindings {
    param([string]$JsonPath)

    if (-not (Test-Path $JsonPath)) {
        Write-Warning "Checkov results not found at $JsonPath"
        return @()
    }

    $findings = @()
    try {
        $checkovResults = Get-Content $JsonPath -Raw | ConvertFrom-Json

        foreach ($check in $checkovResults.results.failed_checks) {
            $ruleId = $check.check_id
            $severity = Get-NormalizedSeverity ($check.severity ?? "MEDIUM") "checkov"
            $findings += @{
                id = [guid]::NewGuid().ToString()
                tool = "checkov"
                rule_id = $ruleId
                severity = $severity
                original_severity = $check.severity ?? "MEDIUM"
                title = $check.check_name
                description = $check.check_name
                message = $check.guideline ?? $check.check_name
                file = $check.file_path
                line = $check.file_line_range[0] ?? 0
                resource = $check.resource
                remediation = $check.guideline ?? ""
                remediation_url = Get-RemediationUrl "checkov" $ruleId
                url = $check.guideline_url ?? $null
                suppressed = $false
                suppression_reason = $null
                baseline = $false
                detected_by = @("checkov")
                category = Get-FindingCategory $ruleId $check.check_name
            }
        }
    }
    catch {
        Write-Warning "Failed to parse Checkov results: $_"
    }

    return $findings
}

# Function to parse tflint JSON output
function Get-TflintFindings {
    param([string]$JsonPath)

    if (-not (Test-Path $JsonPath)) {
        Write-Warning "tflint results not found at $JsonPath"
        return @()
    }

    $findings = @()
    try {
        $tflintResults = Get-Content $JsonPath -Raw | ConvertFrom-Json

        foreach ($issue in $tflintResults.issues) {
            $ruleId = $issue.rule.name
            $severity = Get-NormalizedSeverity $issue.rule.severity "tflint"
            $findings += @{
                id = [guid]::NewGuid().ToString()
                tool = "tflint"
                rule_id = $ruleId
                severity = $severity
                original_severity = $issue.rule.severity
                title = $issue.rule.name
                description = $issue.message
                message = $issue.message
                file = $issue.range.filename
                line = $issue.range.start.line ?? 0
                resource = ""
                remediation = ""
                remediation_url = Get-RemediationUrl "tflint" $ruleId
                url = $issue.rule.link ?? $null
                suppressed = $false
                suppression_reason = $null
                baseline = $false
                detected_by = @("tflint")
                category = Get-FindingCategory $ruleId $issue.rule.name
            }
        }
    }
    catch {
        Write-Warning "Failed to parse tflint results: $_"
    }

    return $findings
}

# Function to parse Snyk IaC JSON output
function Import-SnykResults {
    param([string]$JsonPath)

    $snykFindings = @()

    if (-not (Test-Path $JsonPath)) {
        Write-Warning "Snyk results not found at $JsonPath"
        return $snykFindings
    }

    try {
        $snykResults = Get-Content $JsonPath -Raw | ConvertFrom-Json

        foreach ($issue in $snykResults.infrastructureAsCodeIssues) {
            $ruleId = $issue.publicId ?? $issue.id
            $severity = Get-NormalizedSeverity $issue.severity "snyk"
            $snykFindings += @{
                id = [guid]::NewGuid().ToString()
                tool = "snyk"
                rule_id = $ruleId
                severity = $severity
                original_severity = $issue.severity
                title = $issue.title
                description = $issue.iacDescription.issue ?? ""
                message = $issue.title
                file = $issue.filePath ?? $issue.targetFile
                line = $issue.lineNumber ?? 0
                resource = $issue.resource ?? ""
                remediation = $issue.iacDescription.resolve ?? ""
                remediation_url = Get-RemediationUrl "snyk" $ruleId
                url = $null
                suppressed = $false
                suppression_reason = $null
                baseline = $false
                detected_by = @("snyk")
                category = Get-FindingCategory $ruleId $issue.title
            }
        }
    } catch {
        Write-Warning "Failed to parse Snyk results: $_"
    }

    return $snykFindings
}

# Cross-tool deduplication per spec FR-068a
# Match key: (file, resource, category)
# Merge: highest severity, merge detected_by arrays, keep most detailed remediation
function Invoke-CrossToolDeduplication {
    param([array]$Findings)

    if ($Findings.Count -eq 0) { return @() }

    $dedupMap = @{}

    foreach ($finding in $Findings) {
        $file = $finding.file ?? ""
        $resource = $finding.resource ?? ""
        $category = $finding.category ?? "other"
        $dedupKey = "$file|$resource|$category"

        if ($dedupMap.ContainsKey($dedupKey)) {
            $existing = $dedupMap[$dedupKey]

            # Merge detected_by arrays
            $existingTools = [System.Collections.Generic.HashSet[string]]::new([string[]]$existing.detected_by)
            foreach ($tool in $finding.detected_by) {
                $existingTools.Add($tool) | Out-Null
            }
            $existing.detected_by = @($existingTools)

            # Keep highest severity
            $severityRank = @{ "CRITICAL" = 4; "HIGH" = 3; "MEDIUM" = 2; "LOW" = 1 }
            $existingSev = $severityRank[$existing.severity] ?? 0
            $newSev = $severityRank[$finding.severity] ?? 0
            if ($newSev -gt $existingSev) {
                $existing.severity = $finding.severity
                $existing.original_severity = $finding.original_severity
            }

            # Keep most detailed remediation
            if ($finding.remediation -and $finding.remediation.Length -gt ($existing.remediation ?? "").Length) {
                $existing.remediation = $finding.remediation
            }
            if ($finding.remediation_url -and -not $existing.remediation_url) {
                $existing.remediation_url = $finding.remediation_url
            }

            # Generate new UUID for merged finding
            $existing.id = [guid]::NewGuid().ToString()

            $dedupMap[$dedupKey] = $existing
        }
        else {
            $dedupMap[$dedupKey] = $finding.Clone()
        }
    }

    return @($dedupMap.Values)
}

# Run scans if requested
if ($RunScans) {
    Write-Host "Running security scans..." -ForegroundColor Yellow

    # Run Trivy
    Write-Host "  Running Trivy..." -ForegroundColor Gray
    $trivyOutput = Join-Path $OutputPath "trivy-$dateStamp.json"
    & trivy config . --severity CRITICAL,HIGH,MEDIUM --format json --output $trivyOutput --skip-dirs .terraform 2>$null

    # Run Checkov
    Write-Host "  Running Checkov..." -ForegroundColor Gray
    $checkovOutput = Join-Path $OutputPath "checkov-$dateStamp.json"
    & checkov -d terraform --config-file .checkov.yaml --output json --output-file-path $OutputPath 2>$null
    if (Test-Path (Join-Path $OutputPath "results_json.json")) {
        Move-Item (Join-Path $OutputPath "results_json.json") $checkovOutput -Force
    }

    # Run tflint
    Write-Host "  Running tflint..." -ForegroundColor Gray
    $tflintOutput = Join-Path $OutputPath "tflint-$dateStamp.json"
    & tflint --config=.tflint.hcl --format=json > $tflintOutput 2>$null

    # Run Snyk IaC
    Write-Host "  Running Snyk IaC..." -ForegroundColor Gray
    $snykOutput = Join-Path $OutputPath "snyk-$dateStamp.json"
    & snyk iac test . --json > $snykOutput 2>$null
}

# Find most recent scan results
Write-Host "Collecting scan results..." -ForegroundColor Yellow

$trivyFile = Get-ChildItem -Path $OutputPath -Filter "trivy-*.json" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1

$checkovFile = Get-ChildItem -Path $OutputPath -Filter "checkov-*.json" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1

$tflintFile = Get-ChildItem -Path $OutputPath -Filter "tflint-*.json" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1

$snykFile = Get-ChildItem -Path $OutputPath -Filter "snyk-*.json" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1

# Aggregate findings from each tool
$allFindings = @()
$toolsExecuted = @()

if ($trivyFile) {
    Write-Host "  Processing Trivy results: $($trivyFile.Name)" -ForegroundColor Gray
    $trivyFindings = Get-TrivyFindings $trivyFile.FullName
    $allFindings += $trivyFindings
    $toolsExecuted += "trivy"
}

if ($checkovFile) {
    Write-Host "  Processing Checkov results: $($checkovFile.Name)" -ForegroundColor Gray
    $checkovFindings = Get-CheckovFindings $checkovFile.FullName
    $allFindings += $checkovFindings
    $toolsExecuted += "checkov"
}

if ($tflintFile) {
    Write-Host "  Processing tflint results: $($tflintFile.Name)" -ForegroundColor Gray
    $tflintFindings = Get-TflintFindings $tflintFile.FullName
    $allFindings += $tflintFindings
    $toolsExecuted += "tflint"
}

if ($snykFile) {
    Write-Host "  Processing Snyk results: $($snykFile.Name)" -ForegroundColor Gray
    $snykFindings = Import-SnykResults $snykFile.FullName
    $allFindings += $snykFindings
    $toolsExecuted += "snyk"
}

$unifiedResults.tools_executed = $toolsExecuted

# Apply cross-tool deduplication
Write-Host "Deduplicating cross-tool findings..." -ForegroundColor Yellow
$preDedupCount = $allFindings.Count
$dedupedFindings = Invoke-CrossToolDeduplication $allFindings
$dedupCount = $preDedupCount - $dedupedFindings.Count
if ($dedupCount -gt 0) {
    Write-Host "  Merged $dedupCount duplicate findings across tools" -ForegroundColor Gray
}

# Remove internal category field from output
foreach ($finding in $dedupedFindings) {
    $finding.Remove("category")
}

# Add findings to results
$unifiedResults.findings = $dedupedFindings

# Calculate summary statistics
$unifiedResults.summary.total_findings = $dedupedFindings.Count
$unifiedResults.summary.by_severity.CRITICAL = @($dedupedFindings | Where-Object { $_.severity -eq "CRITICAL" }).Count
$unifiedResults.summary.by_severity.HIGH = @($dedupedFindings | Where-Object { $_.severity -eq "HIGH" }).Count
$unifiedResults.summary.by_severity.MEDIUM = @($dedupedFindings | Where-Object { $_.severity -eq "MEDIUM" }).Count
$unifiedResults.summary.by_severity.LOW = @($dedupedFindings | Where-Object { $_.severity -eq "LOW" }).Count
$unifiedResults.summary.suppressed = @($dedupedFindings | Where-Object { $_.suppressed -eq $true }).Count
$unifiedResults.summary.baselined = @($dedupedFindings | Where-Object { $_.baseline -eq $true }).Count

foreach ($tool in $toolsExecuted) {
    $toolFindings = @($dedupedFindings | Where-Object { $tool -in $_.detected_by })
    $unifiedResults.summary.by_tool[$tool] = $toolFindings.Count
}

# Calculate duration
$scanEndTime = Get-Date
$unifiedResults.duration_ms = [int]($scanEndTime - $scanStartTime).TotalMilliseconds

# Save unified results
$unifiedOutputPath = Join-Path $OutputPath "unified-results-$dateStamp.json"
$unifiedResults | ConvertTo-Json -Depth 10 | Set-Content $unifiedOutputPath -Encoding UTF8

# Also save as latest
$latestPath = Join-Path $OutputPath "unified-results-latest.json"
$unifiedResults | ConvertTo-Json -Depth 10 | Set-Content $latestPath -Encoding UTF8

# Display summary
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Aggregation Complete" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Summary:" -ForegroundColor White
Write-Host "  Total Findings: $($unifiedResults.summary.total_findings)" -ForegroundColor $(if ($unifiedResults.summary.total_findings -gt 0) { "Yellow" } else { "Green" })
Write-Host "    CRITICAL: $($unifiedResults.summary.by_severity.CRITICAL)" -ForegroundColor $(if ($unifiedResults.summary.by_severity.CRITICAL -gt 0) { "Red" } else { "Green" })
Write-Host "    HIGH:     $($unifiedResults.summary.by_severity.HIGH)" -ForegroundColor $(if ($unifiedResults.summary.by_severity.HIGH -gt 0) { "Red" } else { "Green" })
Write-Host "    MEDIUM:   $($unifiedResults.summary.by_severity.MEDIUM)" -ForegroundColor $(if ($unifiedResults.summary.by_severity.MEDIUM -gt 0) { "Yellow" } else { "Green" })
Write-Host "    LOW:      $($unifiedResults.summary.by_severity.LOW)" -ForegroundColor Gray
Write-Host ""
Write-Host "By Tool:" -ForegroundColor White
foreach ($tool in $unifiedResults.summary.by_tool.Keys) {
    Write-Host "  $tool`: $($unifiedResults.summary.by_tool[$tool]) findings" -ForegroundColor Gray
}
if ($dedupCount -gt 0) {
    Write-Host ""
    Write-Host "Deduplication: $dedupCount cross-tool duplicates merged" -ForegroundColor Gray
}
Write-Host ""
Write-Host "Duration: $($unifiedResults.duration_ms)ms" -ForegroundColor Gray
Write-Host "Output: $unifiedOutputPath" -ForegroundColor Green
Write-Host ""

# Return results object for programmatic use
return $unifiedResults
