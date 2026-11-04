# ============================================================================
# LOCAL SECURITY SCANNING VERIFICATION SCRIPT
# auto-code-scanning
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
    [Parameter(HelpMessage = "Run full test including the selected runner's hooks")]
    [switch]$Full = $false,

    [ValidateSet('lefthook', 'pre-commit')]
    [string]$HooksRunner = 'pre-commit',

    [ValidateSet('starter', 'standard', 'strict')]
    [string]$Tier = 'standard',

    [Parameter(HelpMessage = "Show verbose output")]
    [switch]$ShowDetails = $false
)

. "$PSScriptRoot/../hooks/lib/common.ps1"
. "$PSScriptRoot/setup-paths.ps1"
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

function Resolve-VerifiedTool {
    # Resolve a tool by name and refuse one that lives inside the scanned or consumer
    # checkout, so a repository cannot shadow it on PATH. Check the canonical identity,
    # but return the original absolute path so virtual environments keep their packages.
    param([Parameter(Mandatory)][string]$Name, [Parameter(Mandatory)][string]$Label)
    $path = (Get-Command $Name -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    if (-not [IO.Path]::IsPathRooted($path)) { throw "$Label must resolve to an absolute executable path" }
    $target = Resolve-SetupRealPath $path
    $snapshot = $env:SCAN_PUSH_SNAPSHOT -eq '1' -or $env:SCAN_INDEX_SNAPSHOT -eq '1'
    $repoRoot = if ($snapshot) { (Get-Location).Path } else {
        Assert-GitAvailable
        git rev-parse --show-toplevel 2>$null
    }
    if (-not $repoRoot) { $repoRoot = (Get-Location).Path }
    $roots = @($repoRoot)
    if ($snapshot -and $env:SCAN_CONSUMER_ROOT) { $roots += $env:SCAN_CONSUMER_ROOT }
    $comparison = if ([Environment]::OSVersion.Platform -eq 'Win32NT') {
        [StringComparison]::OrdinalIgnoreCase
    } else { [StringComparison]::Ordinal }
    foreach ($root in $roots) {
        $boundary = (Resolve-SetupRealPath $root).TrimEnd('/', '\')
        if ($target.Equals($boundary, $comparison) -or $target.StartsWith($boundary + [IO.Path]::DirectorySeparatorChar, $comparison)) {
            throw "$Label must resolve outside the scanned and consumer checkouts"
        }
    }
    return $path
}

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

$runnerConfig = if ($HooksRunner -eq 'lefthook') { 'lefthook.yml' } else { '.pre-commit-config.yaml' }
$runnerRunArgs = if ($HooksRunner -eq 'lefthook') { @('run', 'pre-commit', '--all-files') } else { @('run', '--all-files') }

$tools = @(
    @{Name = "Trivy"; Command = "trivy"; Args = "--version"; Description = "IaC security scanner" },
    @{Name = "Checkov"; Command = "checkov"; Args = "--version"; Description = "Policy-as-code scanner" },
    @{Name = "tflint"; Command = "tflint"; Args = "--version"; Description = "Terraform linter" },
    @{Name = "Terraform"; Command = "terraform"; Args = "--version"; Description = "Infrastructure as Code" },
    @{Name = $HooksRunner; Command = $HooksRunner; Args = "--version"; Description = "Git hook framework" },
    @{Name = "Python"; Command = "python"; Args = "--version"; Description = "Required for Checkov" },
    @{Name = "Git"; Command = "git"; Args = "--version"; Description = "Version control" }
)

foreach ($tool in $tools) {
    if (Test-CommandExists $tool.Command) {
        if ($tool.Command -eq 'tflint') {
            # Even informational invocations must stay behind policy validation.
            Add-CheckResult -Passed $true -Message 'tflint found; trusted policy verification follows'
            continue
        }
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
    @{Path = $runnerConfig; Name = "$HooksRunner configuration"; Required = $true },
    @{Path = $env:SCAN_TFLINT_CONFIG; Name = "Trusted external tflint configuration"; Required = $true },
    @{Path = (Join-Path $(if ($env:SCAN_CONFIG_DIR) { $env:SCAN_CONFIG_DIR } else { '.scanning/configs' }) '.checkov.yaml'); Name = "Checkov configuration"; Required = $true },
    @{Path = ".trivyignore"; Name = "Trivy ignore file"; Required = $false }
)

foreach ($config in $configFiles) {
    if ($config.Path -and (Test-Path -LiteralPath $config.Path -PathType Leaf)) {
        $size = (Get-Item -LiteralPath $config.Path -Force).Length
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

Write-Header "3. Checking $HooksRunner Hooks"

if (Test-Path ".git") {
    Add-CheckResult -Passed $true -Message "Git repository detected"

    $installedHooks = @('pre-commit', 'pre-push')
    foreach ($hookName in $installedHooks) {
        $hookPath = git rev-parse --git-path "hooks/$hookName"
        $hookContent = if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $hookPath -PathType Leaf)) {
            Get-Content -LiteralPath $hookPath -Raw -ErrorAction SilentlyContinue
        } else { '' }
        $matchesRunner = if ($HooksRunner -eq 'pre-commit' -and $hookName -eq 'pre-push') {
            $hookContent -match '(?m)^# scan push transaction adapter\s*$' -and $hookContent.Contains('--pre-commit-runner')
        } else { $hookContent -match [regex]::Escape($HooksRunner) }
        if ($matchesRunner) {
            Add-CheckResult -Passed $true -Message "$HooksRunner $hookName hook installed"
        }
        else {
            Add-CheckResult -Passed $false -Message "$HooksRunner $hookName hook NOT installed - run: $HooksRunner install"
        }
    }
}
else {
    Add-CheckResult -Passed $true -Warning -Message "Not a Git repository - $HooksRunner hooks not applicable"
}

# ============================================================================
# 4. CHECK HOOK CONFIGURATION
# ============================================================================

Write-Header "4. Checking Security Hooks in Configuration"

if (Test-Path -LiteralPath $runnerConfig -PathType Leaf) {
    try {
        # Parse YAML with an external interpreter; isolated mode excludes the
        # consumer working directory from Python's import search path.
        $python = Resolve-VerifiedTool -Name python -Label Python
        $hookResult = & $python -I "$PSScriptRoot/verify-setup-hooks.py" $HooksRunner $Tier $runnerConfig 2>&1
        if ($LASTEXITCODE -ne 0) { throw ($hookResult -join "`n") }
        Add-CheckResult -Passed $true -Message "$HooksRunner $Tier template hooks configured"
    }
    catch {
        Add-CheckResult -Passed $false -Message "Cannot verify template hooks: $_"
    }
}
else {
    Add-CheckResult -Passed $false -Message "Cannot check hooks - $runnerConfig not found"
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
    try {
        if (-not $env:SCAN_TFLINT_CONFIG -or -not (Test-Path -LiteralPath $env:SCAN_TFLINT_CONFIG -PathType Leaf)) {
            throw 'Set SCAN_TFLINT_CONFIG to a trusted external HCL file'
        }
        Assert-TrustedTflintConfig $env:SCAN_TFLINT_CONFIG
        if (-not $env:SCAN_TFLINT_PLUGIN_DIR) { throw 'Set SCAN_TFLINT_PLUGIN_DIR to an external plugin cache' }
        Assert-ExternalPath $env:SCAN_TFLINT_PLUGIN_DIR
        Assert-SafeWritePath $env:SCAN_TFLINT_PLUGIN_DIR
        $env:TFLINT_PLUGIN_DIR = Resolve-ExternalRealPath $env:SCAN_TFLINT_PLUGIN_DIR
        $trustedConfig = Resolve-ExternalRealPath $env:SCAN_TFLINT_CONFIG
        $tflint = Resolve-VerifiedTool -Name tflint -Label TFLint
        Write-Info "Initializing tflint with trusted external policy..."
        & $tflint --init --config=$trustedConfig 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'tflint initialization failed' }
        & $tflint --config=$trustedConfig 2>&1 | Out-Null
        if ($LASTEXITCODE -notin @(0, 2)) { throw 'tflint verification failed' }
        Add-CheckResult -Passed $true -Message "tflint initialized and verified with trusted external policy"
    }
    catch {
        Add-CheckResult -Passed $false -Message "Cannot verify tflint: $_"
    }
}
else {
    Add-CheckResult -Passed $false -Message "Cannot test tflint - not installed"
}

# ============================================================================
# 7. FULL TEST (Optional)
# ============================================================================

if ($Full) {
    Write-Header "7. Running Full $HooksRunner Test"
    Write-Info "Running all $HooksRunner hooks (this may take a minute)..."

    try {
        $precommitOutput = & $HooksRunner @runnerRunArgs 2>&1
        $precommitExitCode = $LASTEXITCODE

        if ($precommitExitCode -eq 0) {
            Add-CheckResult -Passed $true -Message "All $HooksRunner hooks passed"
        }
        else {
            Add-CheckResult -Passed $true -Warning -Message "Some $HooksRunner hooks had findings (review output below)"
            Write-Host ""
            Write-Host $precommitOutput -ForegroundColor Yellow
        }
    }
    catch {
        Add-CheckResult -Passed $false -Message "$HooksRunner run failed: $_"
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
    Write-Host "  2. Install hooks: $HooksRunner install" -ForegroundColor White
    Write-Host "  3. Run this script again to verify" -ForegroundColor White
}
else {
    Write-Host "All security scanning tools are installed and configured!" -ForegroundColor Green
    Write-Host ""
    Write-Host "QUICK COMMANDS:" -ForegroundColor Cyan
    Write-Host "  $HooksRunner $($runnerRunArgs -join ' ')  - Run all hooks manually" -ForegroundColor White
    Write-Host "  trivy config .              - Scan Terraform for issues" -ForegroundColor White
    Write-Host "  checkov -d .                - Run Checkov policies" -ForegroundColor White
    Write-Host '  tflint --recursive --config="$env:SCAN_TFLINT_CONFIG" - Lint with trusted policy' -ForegroundColor White
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
