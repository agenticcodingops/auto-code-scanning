# ============================================================================
# LOCAL SECURITY SCANNING VERIFICATION SCRIPT
# azure-wordpress
#
# This script verifies that all security scanning tools are properly installed
# and configured for local development.
#
# USAGE:
#   .\scripts\verify-local-scanning.ps1
#
# All tools run LOCALLY - no code is uploaded to external services.
# ============================================================================

[CmdletBinding()]
param(
    [Parameter(HelpMessage = "Run full test including pre-commit hooks")]
    [switch]$Full = $false,

    [Parameter(HelpMessage = "Show verbose output")]
    [switch]$ShowDetails = $false
)

$ErrorActionPreference = "Continue"

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

function Write-Header {
    param([string]$Message)
    Write-Host ""
    Write-Host "===============================================================================" -ForegroundColor Cyan
    Write-Host " $Message" -ForegroundColor Cyan
    Write-Host "===============================================================================" -ForegroundColor Cyan
}

function Write-Pass {
    param([string]$Message)
    Write-Host "[PASS] $Message" -ForegroundColor Green
}

function Write-Fail {
    param([string]$Message)
    Write-Host "[FAIL] $Message" -ForegroundColor Red
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor White
}

function Test-CommandExists {
    param([string]$Command)
    return $null -ne (Get-Command $Command -ErrorAction SilentlyContinue)
}

# ============================================================================
# VERIFICATION RESULTS
# ============================================================================

$Script:TotalChecks = 0
$Script:PassedChecks = 0
$Script:FailedChecks = 0
$Script:Warnings = 0

function Add-CheckResult {
    param(
        [bool]$Passed,
        [string]$Message,
        [switch]$Warning
    )

    $Script:TotalChecks++

    if ($Warning) {
        $Script:Warnings++
        Write-Warn $Message
    }
    elseif ($Passed) {
        $Script:PassedChecks++
        Write-Pass $Message
    }
    else {
        $Script:FailedChecks++
        Write-Fail $Message
    }
}

# ============================================================================
# MAIN VERIFICATION
# ============================================================================

Write-Header "Terraform Security Scanning - Setup Verification"
Write-Host "Verifying all LOCAL security scanning tools are installed and configured..."
Write-Host ""

# ============================================================================
# 1. CHECK REQUIRED TOOLS
# ============================================================================

Write-Header "1. Checking Required Tools"

$tools = @(
    @{Name = "Trivy"; Command = "trivy"; Args = "--version"; Description = "IaC security scanner" },
    @{Name = "Checkov"; Command = "checkov"; Args = "--version"; Description = "Policy-as-code scanner" },
    @{Name = "tflint"; Command = "tflint"; Args = "--version"; Description = "Terraform linter" },
    @{Name = "Terraform"; Command = "terraform"; Args = "--version"; Description = "Infrastructure as Code" },
    @{Name = "pre-commit"; Command = "pre-commit"; Args = "--version"; Description = "Git hook framework" },
    @{Name = "Python"; Command = "python"; Args = "--version"; Description = "Required for Checkov" },
    @{Name = "Git"; Command = "git"; Args = "--version"; Description = "Version control" }
)

foreach ($tool in $tools) {
    if (Test-CommandExists $tool.Command) {
        try {
            $version = & $tool.Command $tool.Args 2>&1 | Select-Object -First 1
            $version = ($version -replace "^[^0-9]*", "" -replace "\s.*$", "").Trim()
            if ($version.Length -gt 20) { $version = $version.Substring(0, 20) + "..." }
            Add-CheckResult -Passed $true -Message "$($tool.Name) installed: $version"
        }
        catch {
            Add-CheckResult -Passed $false -Message "$($tool.Name) installed but version check failed"
        }
    }
    else {
        Add-CheckResult -Passed $false -Message "$($tool.Name) NOT FOUND - $($tool.Description)"
    }
}

# ============================================================================
# 2. CHECK CONFIGURATION FILES
# ============================================================================

Write-Header "2. Checking Configuration Files"

$configFiles = @(
    @{Path = ".pre-commit-config.yaml"; Name = "Pre-commit configuration"; Required = $true },
    @{Path = ".tflint.hcl"; Name = "tflint configuration"; Required = $true },
    @{Path = ".checkov.yaml"; Name = "Checkov configuration"; Required = $true },
    @{Path = ".trivyignore"; Name = "Trivy ignore file"; Required = $false }
)

foreach ($config in $configFiles) {
    if (Test-Path $config.Path) {
        $size = (Get-Item $config.Path).Length
        Add-CheckResult -Passed $true -Message "$($config.Name) exists ($size bytes)"
    }
    else {
        if ($config.Required) {
            Add-CheckResult -Passed $false -Message "$($config.Name) NOT FOUND: $($config.Path)"
        }
        else {
            Add-CheckResult -Passed $true -Warning -Message "$($config.Name) not found (optional): $($config.Path)"
        }
    }
}

# ============================================================================
# 3. CHECK PRE-COMMIT HOOKS
# ============================================================================

Write-Header "3. Checking Pre-commit Hooks"

if (Test-Path ".git") {
    Add-CheckResult -Passed $true -Message "Git repository detected"

    if (Test-Path ".git/hooks/pre-commit") {
        $hookContent = Get-Content ".git/hooks/pre-commit" -Raw -ErrorAction SilentlyContinue
        if ($hookContent -match "pre-commit") {
            Add-CheckResult -Passed $true -Message "Pre-commit hooks installed in .git/hooks/"
        }
        else {
            Add-CheckResult -Passed $false -Message "Pre-commit hook file exists but may not be configured"
        }
    }
    else {
        Add-CheckResult -Passed $false -Message "Pre-commit hooks NOT installed - run: pre-commit install"
    }
}
else {
    Add-CheckResult -Passed $true -Warning -Message "Not a Git repository - pre-commit hooks not applicable"
}

# ============================================================================
# 4. CHECK HOOK CONFIGURATION
# ============================================================================

Write-Header "4. Checking Security Hooks in Configuration"

if (Test-Path ".pre-commit-config.yaml") {
    $configContent = Get-Content ".pre-commit-config.yaml" -Raw

    $securityHooks = @(
        @{Pattern = "terraform_trivy"; Name = "Trivy IaC scanner" },
        @{Pattern = "terraform_checkov"; Name = "Checkov policy scanner" },
        @{Pattern = "terraform_tflint"; Name = "tflint linter" },
        @{Pattern = "trivy-secrets|trivy.*secret"; Name = "Trivy secret scanner" },
        @{Pattern = "detect-private-key"; Name = "Private key detection" }
    )

    foreach ($hook in $securityHooks) {
        if ($configContent -match $hook.Pattern) {
            Add-CheckResult -Passed $true -Message "$($hook.Name) configured"
        }
        else {
            Add-CheckResult -Passed $false -Message "$($hook.Name) NOT configured in .pre-commit-config.yaml"
        }
    }
}
else {
    Add-CheckResult -Passed $false -Message "Cannot check hooks - .pre-commit-config.yaml not found"
}

# ============================================================================
# 5. TEST TRIVY (Quick Scan)
# ============================================================================

Write-Header "5. Testing Trivy Scanner"

if (Test-CommandExists "trivy") {
    Write-Info "Running quick Trivy secret scan..."
    try {
        $trivyOutput = trivy fs . --scanners secret --severity CRITICAL --quiet 2>&1
        $trivyExitCode = $LASTEXITCODE

        if ($trivyExitCode -eq 0) {
            Add-CheckResult -Passed $true -Message "Trivy secret scan completed - no CRITICAL secrets found"
        }
        else {
            Add-CheckResult -Passed $true -Warning -Message "Trivy found potential secrets (exit code: $trivyExitCode)"
        }
    }
    catch {
        Add-CheckResult -Passed $false -Message "Trivy scan failed: $_"
    }
}
else {
    Add-CheckResult -Passed $false -Message "Cannot test Trivy - not installed"
}

# ============================================================================
# 6. TEST TFLINT (Quick Check)
# ============================================================================

Write-Header "6. Testing tflint"

if (Test-CommandExists "tflint") {
    if (Test-Path ".tflint.hcl") {
        Write-Info "Initializing tflint plugins..."
        try {
            tflint --init 2>&1 | Out-Null
            Add-CheckResult -Passed $true -Message "tflint initialized with plugins"
        }
        catch {
            Add-CheckResult -Passed $true -Warning -Message "tflint init had warnings (plugins may download on first use)"
        }
    }
    else {
        Add-CheckResult -Passed $true -Warning -Message "tflint available but .tflint.hcl not found"
    }
}
else {
    Add-CheckResult -Passed $false -Message "Cannot test tflint - not installed"
}

# ============================================================================
# 7. FULL TEST (Optional)
# ============================================================================

if ($Full) {
    Write-Header "7. Running Full Pre-commit Test"
    Write-Info "Running all pre-commit hooks (this may take a minute)..."

    try {
        $precommitOutput = pre-commit run --all-files 2>&1
        $precommitExitCode = $LASTEXITCODE

        if ($precommitExitCode -eq 0) {
            Add-CheckResult -Passed $true -Message "All pre-commit hooks passed"
        }
        else {
            Add-CheckResult -Passed $true -Warning -Message "Some pre-commit hooks had findings (review output below)"
            Write-Host ""
            Write-Host $precommitOutput -ForegroundColor Yellow
        }
    }
    catch {
        Add-CheckResult -Passed $false -Message "Pre-commit run failed: $_"
    }
}

# ============================================================================
# SUMMARY
# ============================================================================

Write-Header "VERIFICATION SUMMARY"

$status = if ($Script:FailedChecks -eq 0) { "PASSED" } else { "FAILED" }
$statusColor = if ($Script:FailedChecks -eq 0) { "Green" } else { "Red" }

Write-Host ""
Write-Host "Results:" -ForegroundColor Cyan
Write-Host "  Total checks:  $($Script:TotalChecks)" -ForegroundColor White
Write-Host "  Passed:        $($Script:PassedChecks)" -ForegroundColor Green
Write-Host "  Failed:        $($Script:FailedChecks)" -ForegroundColor $(if ($Script:FailedChecks -gt 0) { "Red" } else { "White" })
Write-Host "  Warnings:      $($Script:Warnings)" -ForegroundColor $(if ($Script:Warnings -gt 0) { "Yellow" } else { "White" })
Write-Host ""
Write-Host "Overall Status: $status" -ForegroundColor $statusColor
Write-Host ""

if ($Script:FailedChecks -gt 0) {
    Write-Host "NEXT STEPS:" -ForegroundColor Yellow
    Write-Host "  1. Run setup script: .\scripts\setup-local-scanning.ps1" -ForegroundColor White
    Write-Host "  2. Install pre-commit hooks: pre-commit install" -ForegroundColor White
    Write-Host "  3. Run this script again to verify" -ForegroundColor White
}
else {
    Write-Host "All security scanning tools are installed and configured!" -ForegroundColor Green
    Write-Host ""
    Write-Host "QUICK COMMANDS:" -ForegroundColor Cyan
    Write-Host "  pre-commit run --all-files  - Run all hooks manually" -ForegroundColor White
    Write-Host "  trivy config .              - Scan Terraform for issues" -ForegroundColor White
    Write-Host "  checkov -d .                - Run Checkov policies" -ForegroundColor White
    Write-Host "  tflint --recursive          - Lint Terraform files" -ForegroundColor White
}

Write-Host ""
Write-Host "All scanning runs LOCALLY - no code is uploaded to external services." -ForegroundColor Green
Write-Host ""

# Return exit code
if ($Script:FailedChecks -eq 0) {
    exit 0
}
else {
    exit 1
}
