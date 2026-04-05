# ============================================================================
# TERRAFORM SECURITY SCANNING SETUP
# auto-code-scanning
#
# Sets up local security scanning tools for Terraform development.
# All tools run LOCALLY - no code is uploaded to third-party services.
#
# PREREQUISITES:
#   - Windows 11
#   - PowerShell 7+
#   - Administrator rights (use setup-scanning-no-admin.ps1 if unavailable)
#
# USAGE:
#   .\scripts\setup-scanning.ps1 -CloudProvider aws
#   .\scripts\setup-scanning.ps1 -CloudProvider azure -Tier standard
#   .\scripts\setup-scanning.ps1 -CloudProvider gcp -Tier strict -Verbose
#
# TOOLS INSTALLED:
#   - Trivy (IaC security scanner, secrets detection)
#   - Checkov (Policy-as-code)
#   - tflint (Terraform linter with cloud-specific plugins)
#   - Gitleaks (Secret detection)
#   - pre-commit (Git hook framework)
#
# EXIT CODES:
#   0 - Setup completed successfully
#   1 - Setup failed (missing dependency, permission error)
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
    [switch]$SkipTools,

    [Parameter(HelpMessage = "Skip Chocolatey installation if already installed")]
    [switch]$SkipChocolatey
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# ============================================================================
# CONFIGURATION
# ============================================================================

$Script:RepoPath = (Get-Location).Path
$Script:MinVersions = @{
    trivy        = [version]"0.48.0"
    checkov      = [version]"3.0.0"
    tflint       = [version]"0.50.0"
    "pre-commit" = [version]"3.0.0"
}
$Script:ToolsInstalled = 0
$Script:ToolsFailed = 0
$Script:TotalTools = 5  # trivy, checkov, tflint, gitleaks, pre-commit

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

function Write-Step {
    param([string]$Message)
    if ($VerbosePreference -ne "SilentlyContinue" -or -not $Quiet) {
        Write-Host ""
        Write-Host "===============================================================================" -ForegroundColor Cyan
        Write-Host " $Message" -ForegroundColor Cyan
        Write-Host "===============================================================================" -ForegroundColor Cyan
    }
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor White
}

function Test-AdminRights {
    $currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Refresh-EnvironmentPath {
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
}

function Test-CommandExists {
    param([string]$Command)
    return $null -ne (Get-Command $Command -ErrorAction SilentlyContinue)
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

function Install-ChocolateyPackage {
    param(
        [string]$PackageName,
        [string]$DisplayName,
        [string]$CommandName = $PackageName
    )

    if (Test-CommandExists $CommandName) {
        $version = Get-ToolVersion -Command $CommandName
        if ($version -and (Test-ToolMeetsMinimum -ToolName $CommandName -Actual $version)) {
            Write-Success "$DisplayName already installed (v$version, >= $($Script:MinVersions[$CommandName]))"
            $Script:ToolsInstalled++
            return $true
        } elseif ($version -and -not (Test-ToolMeetsMinimum -ToolName $CommandName -Actual $version)) {
            Write-Warn "$DisplayName v$version installed but below minimum $($Script:MinVersions[$CommandName]). Upgrading..."
            try {
                choco upgrade $PackageName -y --no-progress 2>&1 | Out-Null
                Refresh-EnvironmentPath
            } catch {
                Write-Err "Failed to upgrade $DisplayName : $_"
                $Script:ToolsFailed++
                return $false
            }
        } else {
            Write-Success "$DisplayName already installed"
            $Script:ToolsInstalled++
            return $true
        }
    }

    Write-Info "Installing $DisplayName..."
    try {
        choco install $PackageName -y --no-progress 2>&1 | Out-Null
        Refresh-EnvironmentPath

        if (Test-CommandExists $CommandName) {
            $version = Get-ToolVersion -Command $CommandName
            Write-Success "$DisplayName installed (v$version)"
            $Script:ToolsInstalled++
            return $true
        } else {
            Write-Warn "$DisplayName installed but command not found - may need PATH refresh"
            $Script:ToolsInstalled++
            return $true
        }
    } catch {
        Write-Err "Failed to install $DisplayName : $_"
        $Script:ToolsFailed++
        return $false
    }
}

# ============================================================================
# PREREQUISITE CHECKS
# ============================================================================

Write-Host ""
Write-Host "Setting up security scanning for $($CloudProvider.ToUpper()) ($Tier tier)..." -ForegroundColor Cyan
Write-Host ""

Write-Step "Checking Prerequisites"

# Check Administrator
if (-not (Test-AdminRights)) {
    Write-Err "This script must be run as Administrator!"
    Write-Host ""
    Write-Host "Options:" -ForegroundColor Yellow
    Write-Host "  1. Right-click PowerShell 7, select 'Run as Administrator'" -ForegroundColor Yellow
    Write-Host "  2. Use setup-scanning-no-admin.ps1 (no admin required)" -ForegroundColor Yellow
    Write-Host "  3. Use setup-scanning.py (cross-platform, no admin)" -ForegroundColor Yellow
    exit 1
}
Write-Success "Running as Administrator"

# Check PowerShell version
if ($PSVersionTable.PSVersion.Major -lt 7) {
    Write-Err "PowerShell 7+ required. Current version: $($PSVersionTable.PSVersion)"
    exit 1
}
Write-Success "PowerShell $($PSVersionTable.PSVersion) detected"

# Check Git repository
if (-not (Test-Path ".git")) {
    Write-Warn "Not in a Git repository - pre-commit hooks will not be installed"
}

# ============================================================================
# INSTALL TOOLS
# ============================================================================

if (-not $SkipTools) {
    # Install Chocolatey
    if (-not $SkipChocolatey) {
        Write-Step "Setting Up Chocolatey Package Manager"

        if (Test-CommandExists "choco") {
            Write-Success "Chocolatey already installed"
        } else {
            Write-Info "Installing Chocolatey..."
            try {
                Set-ExecutionPolicy Bypass -Scope Process -Force
                [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
                $installScript = (New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1')
                Invoke-Expression $installScript
                Refresh-EnvironmentPath

                if (Test-CommandExists "choco") {
                    Write-Success "Chocolatey installed successfully"
                } else {
                    Write-Err "Chocolatey installation completed but 'choco' command not found"
                    Write-Host "Please close and reopen PowerShell, then run this script again" -ForegroundColor Yellow
                    exit 1
                }
            } catch {
                Write-Err "Failed to install Chocolatey: $_"
                exit 1
            }
        }
    }

    Write-Step "Installing Security Scanning Tools"

    # Install Python (required for Checkov and pre-commit)
    if (-not (Test-CommandExists "python")) {
        Write-Info "Installing Python..."
        try {
            choco install python -y --no-progress 2>&1 | Out-Null
            Refresh-EnvironmentPath
        } catch {
            Write-Err "Failed to install Python: $_"
        }
    }
    Write-Success "Python available"

    # Install Git (if not present)
    if (-not (Test-CommandExists "git")) {
        Write-Info "Installing Git..."
        try {
            choco install git -y --no-progress 2>&1 | Out-Null
            Refresh-EnvironmentPath
        } catch {
            Write-Warn "Failed to install Git: $_"
        }
    }

    # Install Trivy
    Install-ChocolateyPackage -PackageName "trivy" -DisplayName "Trivy (IaC Security Scanner)"

    # Install tflint
    Install-ChocolateyPackage -PackageName "tflint" -DisplayName "tflint (Terraform Linter)"

    # Install Gitleaks
    Install-ChocolateyPackage -PackageName "gitleaks" -DisplayName "Gitleaks (Secret Detection)"

    # Refresh PATH after Chocolatey installs
    Refresh-EnvironmentPath

    # Install Python-based tools
    Write-Step "Installing Python-based Tools"

    Write-Info "Upgrading pip..."
    try {
        python -m pip install --upgrade pip --quiet 2>&1 | Out-Null
    } catch {
        Write-Warn "Could not upgrade pip: $_"
    }

    # Install pre-commit
    Write-Info "Installing pre-commit..."
    try {
        pip install pre-commit --quiet 2>&1 | Out-Null
        if (Test-CommandExists "pre-commit") {
            $version = Get-ToolVersion -Command "pre-commit"
            if ($version -and (Test-ToolMeetsMinimum -ToolName "pre-commit" -Actual $version)) {
                Write-Success "pre-commit installed (v$version, >= $($Script:MinVersions['pre-commit']))"
                $Script:ToolsInstalled++
            } else {
                Write-Warn "pre-commit installed but version $version below minimum $($Script:MinVersions['pre-commit'])"
                $Script:ToolsFailed++
            }
        } else {
            Write-Warn "pre-commit installed but command not in PATH"
            $Script:ToolsFailed++
        }
    } catch {
        Write-Err "Failed to install pre-commit: $_"
        $Script:ToolsFailed++
    }

    # Install Checkov
    Write-Info "Installing Checkov (this may take a minute)..."
    try {
        pip install checkov --quiet 2>&1 | Out-Null
        if (Test-CommandExists "checkov") {
            $version = Get-ToolVersion -Command "checkov"
            if ($version -and (Test-ToolMeetsMinimum -ToolName "checkov" -Actual $version)) {
                Write-Success "Checkov installed (v$version, >= $($Script:MinVersions['checkov']))"
                $Script:ToolsInstalled++
            } else {
                Write-Warn "Checkov installed but version $version below minimum $($Script:MinVersions['checkov'])"
                $Script:ToolsFailed++
            }
        } else {
            # Try to find checkov in Python Scripts
            $pythonScripts = "$env:LOCALAPPDATA\Programs\Python\Python*\Scripts"
            $checkovPath = Get-ChildItem -Path $pythonScripts -Filter "checkov.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($checkovPath) {
                Write-Success "Checkov installed at: $($checkovPath.DirectoryName)"
                $env:Path += ";$($checkovPath.DirectoryName)"
                $Script:ToolsInstalled++
            } else {
                Write-Warn "Checkov installed but command not in PATH"
                $Script:ToolsFailed++
            }
        }
    } catch {
        Write-Err "Failed to install Checkov: $_"
        $Script:ToolsFailed++
    }
    # ============================================================================
    # OPTIONAL: Snyk CLI (requires npm and Snyk license)
    # ============================================================================
    Write-Step "Optional: Snyk CLI"

    if (Test-CommandExists "snyk") {
        $version = Get-ToolVersion -Command "snyk"
        Write-Success "Snyk CLI already installed (v$version) [optional]"
    } elseif (Test-CommandExists "npm") {
        Write-Info "Installing Snyk CLI via npm (optional - requires Snyk license)..."
        try {
            npm install -g snyk 2>&1 | Out-Null
            if (Test-CommandExists "snyk") {
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

# ============================================================================
# COPY CLOUD-SPECIFIC CONFIGS
# ============================================================================

Write-Step "Copying $($CloudProvider.ToUpper()) Configs to .scanning/configs/"

$scanningConfigDir = Join-Path $Script:RepoPath ".scanning" "configs"

if (-not (Test-Path $scanningConfigDir)) {
    New-Item -ItemType Directory -Path $scanningConfigDir -Force | Out-Null
    Write-Info "Created .scanning/configs/ directory"
}

# Determine the config source directory
# When run from a consuming repo, configs come from the pre-commit cache.
# When run from this repo directly, configs are local.
$preCommitCacheBase = Join-Path $env:USERPROFILE ".cache" "pre-commit"
$repoSlug = "auto-code-scanning"
$cacheConfigDir = $null

# Search for configs in pre-commit cache
if (Test-Path $preCommitCacheBase) {
    $cacheDirs = Get-ChildItem -Path $preCommitCacheBase -Directory -Recurse -Depth 2 -ErrorAction SilentlyContinue |
        Where-Object { Test-Path (Join-Path $_.FullName "configs" $CloudProvider) }
    if ($cacheDirs) {
        $cacheConfigDir = Join-Path $cacheDirs[0].FullName "configs"
    }
}

# Fallback: check if we're running from the scanning repo itself
$localConfigDir = Join-Path $Script:RepoPath "configs"
if (-not $cacheConfigDir -and (Test-Path (Join-Path $localConfigDir $CloudProvider))) {
    $cacheConfigDir = $localConfigDir
}

if ($cacheConfigDir) {
    # Copy provider-specific configs
    $providerDir = Join-Path $cacheConfigDir $CloudProvider
    if (Test-Path $providerDir) {
        $configFiles = Get-ChildItem -Path $providerDir -File
        foreach ($file in $configFiles) {
            Copy-Item -Path $file.FullName -Destination $scanningConfigDir -Force
            Write-Verbose "Copied $($file.Name) to .scanning/configs/"
        }
        Write-Success "Copied $($configFiles.Count) provider config(s) for $($CloudProvider.ToUpper())"
    }

    # Copy common configs (suppressions template, trivyignore)
    $commonDir = Join-Path $cacheConfigDir "common"
    if (Test-Path $commonDir) {
        $commonFiles = Get-ChildItem -Path $commonDir -File
        foreach ($file in $commonFiles) {
            $destPath = Join-Path $scanningConfigDir $file.Name
            if (-not (Test-Path $destPath)) {
                Copy-Item -Path $file.FullName -Destination $destPath -Force
                Write-Verbose "Copied common config: $($file.Name)"
            }
        }
    }
} else {
    Write-Warn "Could not find config source directory for $CloudProvider"
    Write-Info "Configs will be available after first pre-commit run (downloaded to cache)"
}

# Copy suppression template to repo root if it doesn't exist
$suppressionDest = Join-Path $Script:RepoPath ".scan-suppressions.yaml"
$suppressionSrc = Join-Path $scanningConfigDir ".scan-suppressions.yaml"
if (-not (Test-Path $suppressionDest) -and (Test-Path $suppressionSrc)) {
    Copy-Item -Path $suppressionSrc -Destination $suppressionDest -Force
    Write-Success "Copied suppression template to .scan-suppressions.yaml"
}

Write-Success "Configs copied to .scanning/configs/"

# ============================================================================
# COPY TIER TEMPLATE
# ============================================================================

Write-Step "Setting Up $Tier Tier Template"

$preCommitConfigDest = Join-Path $Script:RepoPath ".pre-commit-config.yaml"

if (Test-Path $preCommitConfigDest) {
    Write-Info ".pre-commit-config.yaml already exists - skipping template copy"
} else {
    $templateSource = $null

    # Search in pre-commit cache
    if ($cacheConfigDir) {
        $templateCandidateDir = Split-Path $cacheConfigDir -Parent
        $templatePath = Join-Path $templateCandidateDir "templates" $Tier "pre-commit-config.yaml"
        if (Test-Path $templatePath) {
            $templateSource = $templatePath
        }
    }

    # Fallback: local templates directory
    $localTemplate = Join-Path $Script:RepoPath "templates" $Tier "pre-commit-config.yaml"
    if (-not $templateSource -and (Test-Path $localTemplate)) {
        $templateSource = $localTemplate
    }

    if ($templateSource) {
        Copy-Item -Path $templateSource -Destination $preCommitConfigDest -Force
        Write-Success "Copied $Tier tier template to .pre-commit-config.yaml"
    } else {
        Write-Warn "Could not find $Tier tier template"
        Write-Info "Template will be available after the scanning repo is cloned via pre-commit"
    }
}

# ============================================================================
# INITIALIZE TFLINT PLUGINS
# ============================================================================

Write-Step "Initializing tflint Plugins"

if (Test-CommandExists "tflint") {
    $tflintConfig = Join-Path $scanningConfigDir ".tflint.hcl"
    if (Test-Path $tflintConfig) {
        try {
            tflint --init --config $tflintConfig 2>&1 | Out-Null
            Write-Success "tflint plugins initialized for $($CloudProvider.ToUpper())"
        } catch {
            Write-Warn "tflint plugin initialization failed: $_"
        }
    } else {
        Write-Info "No .tflint.hcl found in .scanning/configs/ - plugins will initialize on first run"
    }
} else {
    Write-Warn "tflint not available - skipping plugin initialization"
}

# ============================================================================
# INSTALL PRE-COMMIT HOOKS
# ============================================================================

Write-Step "Installing Pre-commit Hooks"

if (Test-Path ".git") {
    if (Test-Path $preCommitConfigDest) {
        if (Test-CommandExists "pre-commit") {
            try {
                pre-commit install 2>&1 | Out-Null
                Write-Success "Pre-commit hooks installed"
            } catch {
                Write-Warn "Could not install pre-commit hooks: $_"
            }

            try {
                pre-commit install --hook-type pre-push 2>&1 | Out-Null
                Write-Success "Pre-push hooks installed"
            } catch {
                Write-Warn "Could not install pre-push hooks: $_"
            }
        } else {
            Write-Warn "pre-commit not available - hooks will need manual installation"
            Write-Info "Run: pip install pre-commit && pre-commit install"
        }
    } else {
        Write-Warn ".pre-commit-config.yaml not found - hooks not installed"
        Write-Info "Create or copy a config file, then run: pre-commit install"
    }
} else {
    Write-Warn "Not a Git repository - skipping hook installation"
}

# ============================================================================
# VERIFICATION
# ============================================================================

Write-Step "Verifying Installation"

$verifyTools = @(
    @{Name = "Trivy"; Command = "trivy"; MinVersion = $Script:MinVersions["trivy"] },
    @{Name = "Checkov"; Command = "checkov"; MinVersion = $Script:MinVersions["checkov"] },
    @{Name = "tflint"; Command = "tflint"; MinVersion = $Script:MinVersions["tflint"] },
    @{Name = "Gitleaks"; Command = "gitleaks"; MinVersion = $null },
    @{Name = "pre-commit"; Command = "pre-commit"; MinVersion = $Script:MinVersions["pre-commit"] }
)

foreach ($tool in $verifyTools) {
    if (Test-CommandExists $tool.Command) {
        $version = Get-ToolVersion -Command $tool.Command
        $versionStr = if ($version) { "v$version" } else { "(version unknown)" }
        $minStr = if ($tool.MinVersion) { " (>= $($tool.MinVersion))" } else { "" }
        Write-Success "$($tool.Name) $versionStr$minStr"
    } else {
        Write-Warn "$($tool.Name): not found - run manually: choco install $($tool.Command)"
    }
}

# Optional tools verification
if (Test-CommandExists "snyk") {
    $version = Get-ToolVersion -Command "snyk"
    $versionStr = if ($version) { "v$version" } else { "(version unknown)" }
    Write-Success "Snyk CLI $versionStr [optional]"
} else {
    Write-Info "Snyk CLI: not installed [optional - requires npm and Snyk license]"
}

# ============================================================================
# FINAL SUMMARY
# ============================================================================

Write-Host ""
Write-Host "===============================================================================" -ForegroundColor Green
Write-Host " SETUP COMPLETE" -ForegroundColor Green
Write-Host "===============================================================================" -ForegroundColor Green
Write-Host ""

Write-Host "  Cloud Provider: $($CloudProvider.ToUpper())" -ForegroundColor White
Write-Host "  Adoption Tier:  $Tier" -ForegroundColor White
Write-Host "  Tools:          $Script:ToolsInstalled/$Script:TotalTools installed" -ForegroundColor White
Write-Host ""

if ($Script:ToolsFailed -eq 0) {
    Write-Success "All tools installed and verified!"
} else {
    Write-Warn "$Script:ToolsFailed tool(s) need attention - check warnings above"
}

Write-Host ""
Write-Host "NEXT STEPS:" -ForegroundColor Cyan
Write-Host "  1. Test hooks: pre-commit run --all-files" -ForegroundColor White
Write-Host "  2. Test push hooks: pre-commit run --hook-stage pre-push --all-files" -ForegroundColor White
Write-Host ""
Write-Host "All scanning runs LOCALLY - no code is uploaded to external services." -ForegroundColor Green
Write-Host ""

# Return exit code based on installation success
if ($Script:ToolsFailed -eq 0) {
    exit 0
} elseif ($Script:ToolsInstalled -gt 0) {
    exit 2
} else {
    exit 1
}
