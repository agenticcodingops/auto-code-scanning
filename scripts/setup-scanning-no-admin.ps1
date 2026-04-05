# ============================================================================
# TERRAFORM SECURITY SCANNING SETUP - NO ADMIN REQUIRED
# auto-code-scanning
#
# Installs security scanning tools WITHOUT requiring Administrator privileges
# using Scoop (user-level package manager) and pip.
#
# USAGE:
#   .\scripts\setup-scanning-no-admin.ps1 -CloudProvider aws
#   .\scripts\setup-scanning-no-admin.ps1 -CloudProvider azure -Tier standard
#   .\scripts\setup-scanning-no-admin.ps1 -CloudProvider gcp -Tier strict -Verbose
#
# TOOLS INSTALLED:
#   - Trivy (IaC security scanner)
#   - tflint (Terraform linter)
#   - Gitleaks (Secret detection)
#   - Checkov (Policy-as-code via pip)
#   - pre-commit (Git hooks framework via pip)
#
# EXIT CODES:
#   0 - Setup completed successfully
#   1 - Setup failed (missing dependency)
#   2 - Partial setup (some tools installed, some failed)
#
# ============================================================================

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, HelpMessage = "Cloud provider: aws, azure, or gcp")]
    [ValidateSet("aws", "azure", "gcp")]
    [string]$CloudProvider,

    [Parameter(HelpMessage = "Adoption tier: starter, standard, or strict")]
    [ValidateSet("starter", "standard", "strict")]
    [string]$Tier = "starter",

    [Parameter(HelpMessage = "Skip tool installation (configure only)")]
    [switch]$SkipTools
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

# Script-level variables
$Script:PythonCmd = $null
$Script:ToolsDir = "$env:USERPROFILE\.local-scanning-tools"
$Script:PythonUserScripts = $null
$Script:RepoPath = (Get-Location).Path
$Script:ToolsInstalled = 0
$Script:ToolsFailed = 0
$Script:TotalTools = 5  # trivy, tflint, gitleaks, checkov, pre-commit

$Script:MinVersions = @{
    trivy        = [version]"0.48.0"
    checkov      = [version]"3.0.0"
    tflint       = [version]"0.50.0"
    "pre-commit" = [version]"3.0.0"
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

function Write-Step {
    param([string]$Message)
    Write-Host "`n>> $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "   [OK] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "   [WARN] $Message" -ForegroundColor Yellow
}

function Write-Fail {
    param([string]$Message)
    Write-Host "   [FAIL] $Message" -ForegroundColor Red
}

function Write-Info {
    param([string]$Message)
    Write-Host "   [INFO] $Message" -ForegroundColor White
}

function Show-Banner {
    Write-Host @"

================================================================================
  SECURITY SCANNING SETUP (NO ADMIN REQUIRED)
================================================================================
  Cloud Provider: $($CloudProvider.ToUpper())
  Adoption Tier:  $Tier
  This script uses Scoop and pip to install tools without Administrator access.
================================================================================

"@ -ForegroundColor Magenta
}

function Test-CommandAvailable {
    param([string]$Command)
    return [bool](Get-Command $Command -ErrorAction SilentlyContinue)
}

function Get-ToolVersion {
    param([string]$Command, [string]$VersionFlag = "--version")
    try {
        $output = & $Command $VersionFlag 2>&1 | Select-Object -First 1
        $versionStr = $output -replace "^[^0-9]*" -replace "\s.*$" -replace "[^0-9.].*$"
        if ($versionStr) {
            return [version]$versionStr
        }
    } catch {}
    return $null
}

function Test-ToolMeetsMinimum {
    param([string]$ToolName, [version]$Actual)
    if ($Script:MinVersions.ContainsKey($ToolName) -and $Actual) {
        return $Actual -ge $Script:MinVersions[$ToolName]
    }
    return $true
}

# ============================================================================
# PRE-FLIGHT CHECKS
# ============================================================================

function Test-Prerequisites {
    Write-Step "Checking prerequisites..."

    $isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if ($isAdmin) {
        Write-Info "Running as Administrator - this script doesn't require admin privileges"
    }

    $psVersion = $PSVersionTable.PSVersion
    Write-Success "PowerShell version: $($psVersion.Major).$($psVersion.Minor)"

    if (Test-CommandAvailable "git") {
        $gitVersion = git --version
        Write-Success "Git installed: $gitVersion"
    } else {
        Write-Fail "Git is not installed. Please ask IT to install Git."
        Write-Info "Git is required for pre-commit hooks to work."
    }

    Test-PythonAvailable | Out-Null
}

function Test-PythonAvailable {
    if (Test-CommandAvailable "python") {
        $Script:PythonCmd = "python"
        $pyVersion = python --version 2>&1
        Write-Success "Python installed: $pyVersion"
        return $true
    }

    if (Test-CommandAvailable "python3") {
        $Script:PythonCmd = "python3"
        $pyVersion = python3 --version 2>&1
        Write-Success "Python installed: $pyVersion"
        return $true
    }

    if (Test-CommandAvailable "py") {
        $Script:PythonCmd = "py"
        $pyVersion = py --version 2>&1
        Write-Success "Python installed: $pyVersion"
        return $true
    }

    Write-Warn "Python not found in PATH"
    Write-Info "Will attempt to install via Scoop"
    return $false
}

# ============================================================================
# SCOOP INSTALLATION
# ============================================================================

function Install-Scoop {
    Write-Step "Setting up Scoop package manager..."

    if (Test-CommandAvailable "scoop") {
        Write-Success "Scoop is already installed"
        scoop update 2>$null
        return $true
    }

    Write-Info "Installing Scoop (no admin required)..."
    try {
        Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force -ErrorAction SilentlyContinue
        Invoke-RestMethod -Uri https://get.scoop.sh | Invoke-Expression

        if (Test-CommandAvailable "scoop") {
            Write-Success "Scoop installed successfully"
            return $true
        }

        $scoopPath = "$env:USERPROFILE\scoop\shims"
        if (Test-Path $scoopPath) {
            $env:Path = "$scoopPath;$env:Path"
            Write-Success "Scoop installed successfully (PATH updated)"
            return $true
        }

        Write-Fail "Scoop installation failed"
        return $false
    } catch {
        Write-Fail "Failed to install Scoop: $_"
        Write-Info "You can manually install from: https://scoop.sh"
        return $false
    }
}

# ============================================================================
# TOOL INSTALLATION VIA SCOOP
# ============================================================================

function Install-ScoopTools {
    Write-Step "Installing security tools via Scoop..."

    if (-not (Test-CommandAvailable "scoop")) {
        Write-Warn "Scoop not available - skipping Scoop installations"
        return
    }

    Write-Info "Adding Scoop buckets..."
    scoop bucket add extras 2>$null
    scoop bucket add main 2>$null

    Install-ScoopPackage -Name "Trivy" -Package "trivy"
    Install-ScoopPackage -Name "tflint" -Package "tflint"
    Install-ScoopPackage -Name "Gitleaks" -Package "gitleaks"

    # Install Python if not present
    if (-not $Script:PythonCmd) {
        Install-ScoopPackage -Name "Python" -Package "python"
        if (Test-CommandAvailable "python") {
            $Script:PythonCmd = "python"
        }
    }
}

function Install-ScoopPackage {
    param(
        [string]$Name,
        [string]$Package
    )

    if (Test-CommandAvailable $Package) {
        $version = Get-ToolVersion -Command $Package
        if ($version -and (Test-ToolMeetsMinimum -ToolName $Package -Actual $version)) {
            $minStr = if ($Script:MinVersions.ContainsKey($Package)) { " (>= $($Script:MinVersions[$Package]))" } else { "" }
            Write-Success "$Name already installed (v$version$minStr)"
            $Script:ToolsInstalled++
            return
        }
    }

    Write-Info "Installing $Name..."
    scoop install $Package 2>$null

    if (Test-CommandAvailable $Package) {
        $version = Get-ToolVersion -Command $Package
        Write-Success "$Name installed (v$version)"
        $Script:ToolsInstalled++
    } else {
        Write-Warn "$Name installation via Scoop failed - will try alternative method"
        $Script:ToolsFailed++
    }
}

# ============================================================================
# MANUAL DOWNLOAD FALLBACKS
# ============================================================================

function Install-TrivyManually {
    if (Test-CommandAvailable "trivy") { return }

    Write-Step "Downloading Trivy manually..."

    if (-not (Test-Path $Script:ToolsDir)) {
        New-Item -ItemType Directory -Path $Script:ToolsDir -Force | Out-Null
    }

    try {
        $trivyUrl = "https://github.com/aquasecurity/trivy/releases/latest/download/trivy_0.58.0_windows-64bit.zip"
        $trivyZip = "$Script:ToolsDir\trivy.zip"
        $trivyDir = "$Script:ToolsDir\trivy"

        Write-Info "Downloading from GitHub releases..."
        Invoke-WebRequest -Uri $trivyUrl -OutFile $trivyZip -UseBasicParsing

        Write-Info "Extracting..."
        Expand-Archive -Path $trivyZip -DestinationPath $trivyDir -Force
        Remove-Item $trivyZip -Force

        Add-ToUserPath -Directory $trivyDir
        Write-Success "Trivy downloaded to $trivyDir"
    } catch {
        Write-Warn "Manual Trivy download failed: $_"
        Write-Info "You can manually download from: https://github.com/aquasecurity/trivy/releases"
    }
}

function Install-TflintManually {
    if (Test-CommandAvailable "tflint") { return }

    Write-Step "Downloading tflint manually..."

    if (-not (Test-Path $Script:ToolsDir)) {
        New-Item -ItemType Directory -Path $Script:ToolsDir -Force | Out-Null
    }

    try {
        $tflintUrl = "https://github.com/terraform-linters/tflint/releases/latest/download/tflint_windows_amd64.zip"
        $tflintZip = "$Script:ToolsDir\tflint.zip"
        $tflintDir = "$Script:ToolsDir\tflint"

        Write-Info "Downloading from GitHub releases..."
        Invoke-WebRequest -Uri $tflintUrl -OutFile $tflintZip -UseBasicParsing

        Write-Info "Extracting..."
        Expand-Archive -Path $tflintZip -DestinationPath $tflintDir -Force
        Remove-Item $tflintZip -Force

        Add-ToUserPath -Directory $tflintDir
        Write-Success "tflint downloaded to $tflintDir"
    } catch {
        Write-Warn "Manual tflint download failed: $_"
        Write-Info "You can manually download from: https://github.com/terraform-linters/tflint/releases"
    }
}

function Add-ToUserPath {
    param([string]$Directory)

    $env:Path = "$Directory;$env:Path"
    [Environment]::SetEnvironmentVariable("Path", "$Directory;$([Environment]::GetEnvironmentVariable('Path', 'User'))", "User")
}

# ============================================================================
# PYTHON TOOLS INSTALLATION
# ============================================================================

function Install-PythonTools {
    Write-Step "Installing Python-based tools via pip..."

    if (-not $Script:PythonCmd) {
        Write-Fail "Python not available - cannot install pre-commit and checkov"
        Write-Info "Please ask IT to install Python, or install via Scoop first"
        $Script:ToolsFailed += 2
        return
    }

    # Ensure pip is available and upgraded
    & $Script:PythonCmd -m ensurepip --upgrade 2>$null
    & $Script:PythonCmd -m pip install --upgrade pip --user --quiet 2>$null

    # Install pre-commit
    Install-PipPackage -Name "pre-commit"

    # Install Checkov
    Install-PipPackage -Name "checkov"

    # Add Python user scripts to PATH
    Update-PythonScriptsPath

    # Verify installations
    Confirm-PythonToolInstallation
}

function Install-PipPackage {
    param([string]$Name)

    Write-Info "Installing $Name..."
    & $Script:PythonCmd -m pip install $Name --user --quiet 2>$null
}

function Update-PythonScriptsPath {
    $Script:PythonUserScripts = & $Script:PythonCmd -c "import site; print(site.getusersitepackages().replace('site-packages', 'Scripts'))" 2>$null

    if ($Script:PythonUserScripts -and (Test-Path $Script:PythonUserScripts)) {
        if ($env:Path -notlike "*$Script:PythonUserScripts*") {
            Add-ToUserPath -Directory $Script:PythonUserScripts
            Write-Info "Added Python Scripts to PATH: $Script:PythonUserScripts"
        }
    }
}

function Confirm-PythonToolInstallation {
    if (Test-CommandAvailable "pre-commit") {
        $version = Get-ToolVersion -Command "pre-commit"
        if ($version -and (Test-ToolMeetsMinimum -ToolName "pre-commit" -Actual $version)) {
            Write-Success "pre-commit installed (v$version, >= $($Script:MinVersions['pre-commit']))"
            $Script:ToolsInstalled++
        } else {
            Write-Warn "pre-commit v$version below minimum $($Script:MinVersions['pre-commit'])"
            $Script:ToolsFailed++
        }
    } else {
        Write-Warn "pre-commit not found in PATH after installation"
        Write-Info "Try: $Script:PythonCmd -m pre_commit --version"
        $Script:ToolsFailed++
    }

    if (Test-CommandAvailable "checkov") {
        $version = Get-ToolVersion -Command "checkov"
        if ($version -and (Test-ToolMeetsMinimum -ToolName "checkov" -Actual $version)) {
            Write-Success "checkov installed (v$version, >= $($Script:MinVersions['checkov']))"
            $Script:ToolsInstalled++
        } else {
            Write-Warn "checkov v$version below minimum $($Script:MinVersions['checkov'])"
            $Script:ToolsFailed++
        }
    } else {
        Write-Warn "checkov not found in PATH after installation"
        Write-Info "Try: $Script:PythonCmd -m checkov --version"
        $Script:ToolsFailed++
    }
}

# ============================================================================
# COPY CLOUD-SPECIFIC CONFIGS
# ============================================================================

function Copy-CloudConfigs {
    Write-Step "Copying $($CloudProvider.ToUpper()) configs to .scanning/configs/..."

    $scanningConfigDir = Join-Path $Script:RepoPath ".scanning" "configs"

    if (-not (Test-Path $scanningConfigDir)) {
        New-Item -ItemType Directory -Path $scanningConfigDir -Force | Out-Null
        Write-Info "Created .scanning/configs/ directory"
    }

    # Search for configs in pre-commit cache or local
    $preCommitCacheBase = Join-Path $env:USERPROFILE ".cache" "pre-commit"
    $cacheConfigDir = $null

    if (Test-Path $preCommitCacheBase) {
        $cacheDirs = Get-ChildItem -Path $preCommitCacheBase -Directory -Recurse -Depth 2 -ErrorAction SilentlyContinue |
            Where-Object { Test-Path (Join-Path $_.FullName "configs" $CloudProvider) }
        if ($cacheDirs) {
            $cacheConfigDir = Join-Path $cacheDirs[0].FullName "configs"
        }
    }

    # Fallback: local configs
    $localConfigDir = Join-Path $Script:RepoPath "configs"
    if (-not $cacheConfigDir -and (Test-Path (Join-Path $localConfigDir $CloudProvider))) {
        $cacheConfigDir = $localConfigDir
    }

    if ($cacheConfigDir) {
        $providerDir = Join-Path $cacheConfigDir $CloudProvider
        if (Test-Path $providerDir) {
            $configFiles = Get-ChildItem -Path $providerDir -File
            foreach ($file in $configFiles) {
                Copy-Item -Path $file.FullName -Destination $scanningConfigDir -Force
                Write-Verbose "Copied $($file.Name)"
            }
            Write-Success "Copied $($configFiles.Count) provider config(s) for $($CloudProvider.ToUpper())"
        }

        $commonDir = Join-Path $cacheConfigDir "common"
        if (Test-Path $commonDir) {
            Get-ChildItem -Path $commonDir -File | ForEach-Object {
                $destPath = Join-Path $scanningConfigDir $_.Name
                if (-not (Test-Path $destPath)) {
                    Copy-Item -Path $_.FullName -Destination $destPath -Force
                }
            }
        }
    } else {
        Write-Warn "Could not find config source for $CloudProvider"
        Write-Info "Configs will be available after first pre-commit run"
    }

    # Copy suppression template to repo root
    $suppressionDest = Join-Path $Script:RepoPath ".scan-suppressions.yaml"
    $suppressionSrc = Join-Path $scanningConfigDir ".scan-suppressions.yaml"
    if (-not (Test-Path $suppressionDest) -and (Test-Path $suppressionSrc)) {
        Copy-Item -Path $suppressionSrc -Destination $suppressionDest -Force
        Write-Success "Copied suppression template to .scan-suppressions.yaml"
    }

    return $cacheConfigDir
}

# ============================================================================
# COPY TIER TEMPLATE
# ============================================================================

function Copy-TierTemplate {
    param([string]$ConfigSourceDir)

    Write-Step "Setting up $Tier tier template..."

    $preCommitConfigDest = Join-Path $Script:RepoPath ".pre-commit-config.yaml"

    if (Test-Path $preCommitConfigDest) {
        Write-Info ".pre-commit-config.yaml already exists - skipping template copy"
        return
    }

    $templateSource = $null

    if ($ConfigSourceDir) {
        $templateCandidateDir = Split-Path $ConfigSourceDir -Parent
        $templatePath = Join-Path $templateCandidateDir "templates" $Tier "pre-commit-config.yaml"
        if (Test-Path $templatePath) {
            $templateSource = $templatePath
        }
    }

    $localTemplate = Join-Path $Script:RepoPath "templates" $Tier "pre-commit-config.yaml"
    if (-not $templateSource -and (Test-Path $localTemplate)) {
        $templateSource = $localTemplate
    }

    if ($templateSource) {
        Copy-Item -Path $templateSource -Destination $preCommitConfigDest -Force
        Write-Success "Copied $Tier tier template to .pre-commit-config.yaml"
    } else {
        Write-Warn "Could not find $Tier tier template"
    }
}

# ============================================================================
# POST-INSTALLATION SETUP
# ============================================================================

function Initialize-TflintPlugins {
    Write-Step "Initializing tflint plugins..."

    if (-not (Test-CommandAvailable "tflint")) {
        Write-Warn "tflint not available - skipping plugin initialization"
        return
    }

    $tflintConfig = Join-Path $Script:RepoPath ".scanning" "configs" ".tflint.hcl"
    if (Test-Path $tflintConfig) {
        try {
            tflint --init --config $tflintConfig 2>&1 | Out-Null
            Write-Success "tflint plugins initialized for $($CloudProvider.ToUpper())"
        } catch {
            Write-Warn "tflint plugin initialization failed: $_"
        }
    } else {
        Write-Info "No .tflint.hcl in .scanning/configs/ - plugins will initialize on first run"
    }
}

function Install-PrecommitHooks {
    Write-Step "Installing pre-commit hooks..."

    if (-not (Test-Path (Join-Path $Script:RepoPath ".git"))) {
        Write-Warn "Not a Git repository - skipping hook installation"
        return
    }

    $preCommitConfigDest = Join-Path $Script:RepoPath ".pre-commit-config.yaml"
    if (-not (Test-Path $preCommitConfigDest)) {
        Write-Warn ".pre-commit-config.yaml not found - hooks not installed"
        return
    }

    Push-Location $Script:RepoPath

    if (Test-CommandAvailable "pre-commit") {
        Install-HooksWithCommand -Command "pre-commit"
    } elseif ($Script:PythonCmd) {
        Install-HooksWithPythonModule
    } else {
        Write-Fail "Cannot install hooks - pre-commit not available"
    }

    Pop-Location
}

function Install-HooksWithCommand {
    param([string]$Command)

    try {
        & $Command install 2>&1 | Out-Null
        Write-Success "Pre-commit hooks installed"
    } catch {
        Write-Warn "Hook installation failed: $_"
    }

    try {
        & $Command install --hook-type pre-push 2>&1 | Out-Null
        Write-Success "Pre-push hooks installed"
    } catch {
        Write-Warn "Pre-push hook installation failed: $_"
    }
}

function Install-HooksWithPythonModule {
    try {
        & $Script:PythonCmd -m pre_commit install 2>&1 | Out-Null
        Write-Success "Pre-commit hooks installed (via python -m)"

        & $Script:PythonCmd -m pre_commit install --hook-type pre-push 2>&1 | Out-Null
        Write-Success "Pre-push hooks installed (via python -m)"
    } catch {
        Write-Warn "Hook installation failed: $_"
    }
}

# ============================================================================
# VERIFICATION
# ============================================================================

function Show-VerificationResults {
    Write-Step "Verifying installation..."

    $tools = @(
        @{Name = "Trivy"; Command = "trivy"; MinVersion = $Script:MinVersions["trivy"] },
        @{Name = "tflint"; Command = "tflint"; MinVersion = $Script:MinVersions["tflint"] },
        @{Name = "Gitleaks"; Command = "gitleaks"; MinVersion = $null },
        @{Name = "pre-commit"; Command = "pre-commit"; MinVersion = $Script:MinVersions["pre-commit"] },
        @{Name = "Checkov"; Command = "checkov"; MinVersion = $Script:MinVersions["checkov"] }
    )

    Write-Host "`n"
    Write-Host "   Installation Results:" -ForegroundColor Cyan
    Write-Host "   =====================" -ForegroundColor Cyan

    foreach ($tool in $tools) {
        if (Test-CommandAvailable $tool.Command) {
            $version = Get-ToolVersion -Command $tool.Command
            $versionStr = if ($version) { "v$version" } else { "(version unknown)" }
            $minStr = if ($tool.MinVersion) { " (>= $($tool.MinVersion))" } else { "" }
            Write-Success "$($tool.Name) $versionStr$minStr"
        } else {
            Write-Fail "$($tool.Name): not found"
        }
    }

    # Optional tools verification
    if (Test-CommandAvailable "snyk") {
        $version = Get-ToolVersion -Command "snyk"
        $versionStr = if ($version) { "v$version" } else { "(version unknown)" }
        Write-Success "Snyk CLI $versionStr [optional]"
    } else {
        Write-Info "Snyk CLI: not installed [optional - requires npm and Snyk license]"
    }

    Write-Host "`n"
    Write-Host "   Cloud Provider: $($CloudProvider.ToUpper())" -ForegroundColor White
    Write-Host "   Adoption Tier:  $Tier" -ForegroundColor White
    Write-Host "   Tools:          $Script:ToolsInstalled/$Script:TotalTools installed" -ForegroundColor White
}

function Show-Summary {
    Write-Host @"

================================================================================
  SETUP COMPLETE
================================================================================

  Cloud Provider: $($CloudProvider.ToUpper())
  Adoption Tier:  $Tier

  Tools are installed in your user profile (no admin required):
  - Scoop packages: $env:USERPROFILE\scoop
  - Python packages: $Script:PythonUserScripts
  - Manual downloads: $Script:ToolsDir

  IMPORTANT: You may need to restart your terminal for PATH changes to take effect.

  Quick Test:
    pre-commit run --all-files
    pre-commit run --hook-stage pre-push --all-files

  All scanning runs LOCALLY - no code is uploaded to external services.

================================================================================
"@ -ForegroundColor Magenta
}

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

function Main {
    Show-Banner
    Test-Prerequisites

    if (-not $SkipTools) {
        # Install package managers and tools
        Install-Scoop
        Install-ScoopTools

        # Fallback to manual downloads if needed
        Install-TrivyManually
        Install-TflintManually

        # Install Python-based tools
        Install-PythonTools

        # ============================================================================
        # OPTIONAL: Snyk CLI (requires npm and Snyk license)
        # ============================================================================
        Write-Step "Optional: Snyk CLI"

        if (Test-CommandAvailable "snyk") {
            $version = Get-ToolVersion -Command "snyk"
            Write-Success "Snyk CLI already installed (v$version) [optional]"
        } elseif (Test-CommandAvailable "npm") {
            Write-Info "Installing Snyk CLI via npm (optional - requires Snyk license)..."
            try {
                npm install -g snyk 2>&1 | Out-Null
                if (Test-CommandAvailable "snyk") {
                    $version = Get-ToolVersion -Command "snyk"
                    Write-Success "Snyk CLI installed (v$version) [optional]"
                } else {
                    Write-Info "Snyk CLI installed but not on PATH. This is optional."
                }
            } catch {
                Write-Info "Snyk CLI installation skipped: $_. This is optional."
            }
        } else {
            Write-Info "Snyk CLI not installed (npm not found). This is optional - ignore if no Snyk license."
        }
    } else {
        Write-Info "Skipping tool installation (-SkipTools specified)"
    }

    # Copy cloud-specific configs and tier template
    $configSourceDir = Copy-CloudConfigs
    Copy-TierTemplate -ConfigSourceDir $configSourceDir

    # Post-installation setup
    Initialize-TflintPlugins
    Install-PrecommitHooks

    # Show results
    Show-VerificationResults
    Show-Summary

    # Return exit code
    if ($Script:ToolsFailed -eq 0) {
        exit 0
    } elseif ($Script:ToolsInstalled -gt 0) {
        exit 2
    } else {
        exit 1
    }
}

# Run the script
Main
