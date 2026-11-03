<#
.SYNOPSIS
  setup-scan-fix.ps1 — ONE-command onboarding for the scan->fix platform.

.DESCRIPTION
  Idempotent and re-runnable. Writes scan-config.yaml from a tier template,
  installs the chosen local runner (Lefthook default | pre-commit), copies the
  Claude Code in-session bundle + thin caller workflows, creates the ai-autofix /
  needs-human-review labels, VERIFIES (never creates) the required secrets, and
  runs verify-scanning to prove the install.

.EXAMPLE
  ./scripts/setup-scan-fix.ps1 -Languages csharp,typescript -Tier standard -EnableFixLoop
  ./scripts/setup-scan-fix.ps1 -Languages terraform -CloudProvider aws -HooksRunner pre-commit
#>
[CmdletBinding()]
param(
    [string]$Languages = "",                                  # csv: csharp,typescript,terraform,sql
    [ValidateSet("starter", "standard", "strict")] [string]$Tier = "standard",
    [ValidateSet("lefthook", "pre-commit")] [string]$HooksRunner = "lefthook",
    [switch]$EnableFixLoop,
    [ValidateSet("aws", "azure", "gcp", "")] [string]$CloudProvider = "",
    [string]$RepoPath = (Get-Location).Path,                  # target consumer repo
    [switch]$Force                                            # overwrite existing scan-config.yaml
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/../hooks/lib/common.ps1"
Assert-SafeWritePath (Get-Location).Path

$PlatformRoot = (Resolve-Path "$PSScriptRoot\..").Path
Assert-SafeWritePath $RepoPath
$RepoPath = (Resolve-Path $RepoPath).Path

function Resolve-SetupTool {
    param([string]$Name)
    $command = Get-Command $Name -CommandType Application, ExternalScript -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $command) { return $null }
    if (-not [IO.Path]::IsPathRooted($command.Source)) { throw "$Name must resolve to an absolute executable path" }
    $boundary = $RepoPath.TrimEnd('/', '\')
    $path = [IO.Path]::GetFullPath($command.Source)
    if ($path -eq $boundary -or $path.StartsWith($boundary + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "$Name must resolve outside the destination repository"
    }
    try { $path = Resolve-ExternalRealPath $path }
    catch {
        # Store application aliases expose no link target. Use the interpreter
        # already running this script rather than executing an unresolved alias.
        if ($Name -ne 'pwsh' -or $PSVersionTable.PSEdition -ne 'Core') { throw }
        $path = Resolve-ExternalRealPath ([Diagnostics.Process]::GetCurrentProcess().MainModule.FileName)
    }
    if ($path -eq $boundary -or $path.StartsWith($boundary + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "$Name must resolve outside the destination repository"
    }
    return $path
}

# Resolve every executable before probes, writes or directory changes.
$setupTools = @{}
foreach ($name in @('lefthook', 'pre-commit', 'gh', 'pwsh')) {
    $setupTools[$name] = Resolve-SetupTool $name
}

function Info  { param($m) Write-Host "[INFO] $m" -ForegroundColor White }
function Ok    { param($m) Write-Host "[OK]   $m" -ForegroundColor Green }
function Warn  { param($m) Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Step  { param($m) Write-Host "`n=== $m ===" -ForegroundColor Cyan }
$script:FailedSteps = @()
function Install-Step {
    param([string]$Label, [scriptblock]$Action)
    try {
        & $Action
        if ($LASTEXITCODE -ne 0) { throw "exit code $LASTEXITCODE" }
        Ok $Label
    } catch {
        $script:FailedSteps += $Label
        Warn "FAILED: ${Label}: $_. Resolve the error above and re-run setup."
    }
}
function Find-Py {
    foreach ($c in @('python', 'python3', 'py')) {
        $path = Resolve-SetupTool $c
        if ($path) { try { & $path -c "" 2>$null; if ($LASTEXITCODE -eq 0) { return $path } } catch {} }
    }
    return $null
}
function Copy-IfNewer {
    param($Src, $Dst)
    Assert-SafeWritePath $Dst
    $dir = Split-Path $Dst -Parent
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    Copy-Item -Path $Src -Destination $Dst -Force
}

Write-Host "`nOnboarding scan->fix platform into: $RepoPath" -ForegroundColor Cyan
Write-Host "  tier=$Tier runner=$HooksRunner languages=$Languages fixLoop=$EnableFixLoop`n"

$py = Find-Py
if (-not $py) { Warn "Python not found; scan-config rendering + some hooks need it. Continuing." }

# ---------------------------------------------------------------------------
# 1) scan-config.yaml from tier template
# ---------------------------------------------------------------------------
Step "scan-config.yaml ($Tier tier)"
$cfgOut = Join-Path $RepoPath "scan-config.yaml"
$langArg = $Languages
if ($CloudProvider -and ($Languages -notmatch "terraform")) { $langArg = (@($Languages, "terraform") | Where-Object { $_ } ) -join "," }
if ($py) {
    $renderArgs = @((Join-Path $PlatformRoot "scripts/render-scan-config.py"),
        "--tier", $Tier, "--languages", $langArg,
        "--templates-dir", (Join-Path $PlatformRoot "templates/scan-config"),
        "--out", $cfgOut)
    if ($EnableFixLoop) { $renderArgs += "--enable-fix-loop" }
    if ($Force) { $renderArgs += "--force" }
    & $py @renderArgs
    Ok "scan-config.yaml ready"
} else {
    if (-not (Test-Path $cfgOut)) { Copy-IfNewer (Join-Path $PlatformRoot "templates/scan-config/$Tier.yaml") $cfgOut; Warn "Copied $Tier template verbatim (enable languages manually)" }
}

# ---------------------------------------------------------------------------
# 2) Vendor shared hooks + scripts (needed by Lefthook + Claude bundle)
# ---------------------------------------------------------------------------
Step "Vendoring shared hooks + scripts"
if ($RepoPath -ne $PlatformRoot) {
    Assert-SafeTree (Join-Path $RepoPath "hooks")
    Copy-Item -Path (Join-Path $PlatformRoot "hooks") -Destination $RepoPath -Recurse -Force
    Assert-SafeTree (Join-Path $RepoPath "schemas")
    Copy-Item -Path (Join-Path $PlatformRoot "schemas") -Destination $RepoPath -Recurse -Force
    foreach ($s in @("scan-and-fix.ps1", "scan-and-fix.sh", "check-fix-allowlist.py", "validate-scan-config.py", "render-scan-config.py",
                     "scan.py", "safe_io.py", "scan_policy.py", "scan_reports.py", "validate-suppressions.py", "create-baseline.ps1", "finalize_baseline.py")) {
        Copy-IfNewer (Join-Path $PlatformRoot "scripts/$s") (Join-Path $RepoPath "scripts/$s")
    }
    Ok "Copied hooks/, schemas/, and shared scripts/"
} else {
    Info "Running inside the platform repo; hooks/scripts already present"
}

# ---------------------------------------------------------------------------
# 3) Local runner
# ---------------------------------------------------------------------------
Step "Local runner: $HooksRunner"
if ($HooksRunner -eq "lefthook") {
    Copy-IfNewer (Join-Path $PlatformRoot "templates/lefthook/lefthook.yml") (Join-Path $RepoPath "lefthook.yml")
    if ($setupTools['lefthook']) {
        Push-Location $RepoPath; try { & $setupTools['lefthook'] install | Out-Null; Ok "lefthook installed" } finally { Pop-Location }
    } else {
        Warn "lefthook not on PATH. Install: 'choco install lefthook' or 'go install github.com/evilmartians/lefthook@latest', then 'lefthook install'"
    }
} else {
    $pcDest = Join-Path $RepoPath ".pre-commit-config.yaml"
    $pcSrc = Join-Path $PlatformRoot "templates/$Tier/pre-commit-config.yaml"
    if ((Test-Path $pcSrc) -and -not (Test-Path $pcDest)) { Copy-IfNewer $pcSrc $pcDest }
    if ($setupTools['pre-commit']) {
        Push-Location $RepoPath
        try {
            Install-Step 'pre-commit hook installation' {
                if (-not $py) { throw 'Python is required to install the pre-commit hook' }
                & $setupTools['pre-commit'] install
            }
            Install-Step 'push transaction adapter installation' {
                if (-not $py) { throw 'Python is required to install the push transaction adapter' }
                & $py (Join-Path $RepoPath 'hooks/pre-push.py') --install-pre-commit
            }
        } finally { Pop-Location }
    } else { Warn "pre-commit not on PATH. Install: 'pip install pre-commit', then 'pre-commit install'" }
}

# ---------------------------------------------------------------------------
# 4) Claude Code in-session bundle
# ---------------------------------------------------------------------------
Step "Claude Code in-session bundle (.claude/)"
$claudeSettings = Join-Path $RepoPath ".claude/settings.json"
# Install the runner-appropriate settings: pwsh on Windows, bash on macOS/Linux.
$settingsSrc = if ($IsWindows -eq $false) { "templates/claude/settings.unix.json" } else { "templates/claude/settings.json" }
if (-not (Test-Path $claudeSettings)) {
    Copy-IfNewer (Join-Path $PlatformRoot $settingsSrc) $claudeSettings
    Info "Installed $(Split-Path $settingsSrc -Leaf) as .claude/settings.json"
} else { Info ".claude/settings.json exists; leaving it (merge manually if needed)" }
foreach ($h in @("posttooluse-scan.ps1", "posttooluse-scan.sh", "stop-scan.ps1", "stop-scan.sh")) {
    Copy-IfNewer (Join-Path $PlatformRoot "templates/claude/hooks/$h") (Join-Path $RepoPath ".claude/hooks/$h")
}
Ok "Claude bundle copied"

# ---------------------------------------------------------------------------
# 5) Caller workflows
# ---------------------------------------------------------------------------
Step "CI caller workflows (.github/workflows/)"
Copy-IfNewer (Join-Path $PlatformRoot "templates/workflows/code-security-scan.yml") (Join-Path $RepoPath ".github/workflows/code-security-scan.yml")
if ($langArg -match "terraform") { Copy-IfNewer (Join-Path $PlatformRoot "templates/workflows/terraform-scan.yml") (Join-Path $RepoPath ".github/workflows/terraform-scan.yml") }
if ($EnableFixLoop) { Copy-IfNewer (Join-Path $PlatformRoot "templates/fix-loop/autonomous-fix.yml") (Join-Path $RepoPath ".github/workflows/autonomous-fix.yml") }
Ok "Caller workflows copied (review the immutable commit pins)"

# ---------------------------------------------------------------------------
# 6) Labels + 7) Secret verification (fix-loop only)
# ---------------------------------------------------------------------------
if ($EnableFixLoop) {
    Step "Fix-loop: labels + secret verification"
    if ($setupTools['gh']) {
        Push-Location $RepoPath
        try {
            try { & $setupTools['gh'] label create "ai-autofix" --color 1D76DB --description "Opt this PR into the autonomous fix-loop" --force | Out-Null; Ok "label ai-autofix" } catch { Warn "could not create ai-autofix label: $_" }
            try { & $setupTools['gh'] label create "needs-human-review" --color B60205 --description "Autonomous fix loop stopped; needs a human" --force | Out-Null; Ok "label needs-human-review" } catch { Warn "could not create needs-human-review label: $_" }

            $secrets = @()
            try { $secrets = (& $setupTools['gh'] secret list --json name 2>$null | ConvertFrom-Json).name } catch { $secrets = (& $setupTools['gh'] secret list 2>$null | ForEach-Object { ($_ -split '\s+')[0] }) }
            foreach ($need in @("AUTOFIX_TOKEN", "ANTHROPIC_API_KEY")) {
                if ($secrets -contains $need) { Ok "secret $need present" }
                else {
                    Warn "secret $need MISSING — create it (this script never stores secrets):"
                    if ($need -eq "AUTOFIX_TOKEN") {
                        Write-Host "    Create a fine-grained PAT (Contents: RW, Pull requests: RW, THIS repo only), then:" -ForegroundColor Yellow
                        Write-Host "      gh secret set AUTOFIX_TOKEN" -ForegroundColor Yellow
                    } else {
                        Write-Host "      gh secret set ANTHROPIC_API_KEY   # or CLAUDE_CODE_OAUTH_TOKEN" -ForegroundColor Yellow
                    }
                }
            }
        } finally { Pop-Location }
    } else {
        Warn "gh CLI not found — cannot create labels or verify secrets. Install GitHub CLI, then re-run."
    }
}

# ---------------------------------------------------------------------------
# 8) Verify
# ---------------------------------------------------------------------------
Step "Verify install"
$verify = Join-Path $PlatformRoot "scripts/verify-scanning.ps1"
if ((Test-Path $verify) -and $setupTools['pwsh']) {
    Push-Location $RepoPath
    try { & $setupTools['pwsh'] -NoProfile -ExecutionPolicy Bypass -File $verify 2>&1 | Select-Object -First 30 } catch { Warn "verify-scanning reported issues: $_" } finally { Pop-Location }
} else { Info "Verification needs verify-scanning.ps1 and an external pwsh; skipping" }

if ($script:FailedSteps.Count) {
    Warn "Setup finished with failed steps: $($script:FailedSteps -join ', ')"
    Write-Host "`n=== SETUP COMPLETED WITH ERRORS ===" -ForegroundColor Yellow
} else { Write-Host "`n=== SETUP COMPLETE ===" -ForegroundColor Green }
Write-Host "Next:" -ForegroundColor Cyan
Write-Host "  1. Review scan-config.yaml (enabled languages, fix_loop)" -ForegroundColor White
Write-Host "  2. Review the caller workflows' immutable commit pins" -ForegroundColor White
if ($HooksRunner -eq 'lefthook') { Write-Host "  3. Test: stage a file and 'git commit' (or 'lefthook run pre-commit')" -ForegroundColor White }
else { Write-Host "  3. Test: 'pre-commit run --all-files'" -ForegroundColor White }
if ($EnableFixLoop) { Write-Host "  4. Add the 'ai-autofix' label to a PR to opt it into the fix-loop" -ForegroundColor White }
if ($script:FailedSteps.Count) { exit 1 }
exit 0
