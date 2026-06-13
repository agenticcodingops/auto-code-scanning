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
$PlatformRoot = (Resolve-Path "$PSScriptRoot\..").Path
$RepoPath = (Resolve-Path $RepoPath).Path

function Info  { param($m) Write-Host "[INFO] $m" -ForegroundColor White }
function Ok    { param($m) Write-Host "[OK]   $m" -ForegroundColor Green }
function Warn  { param($m) Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Step  { param($m) Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Find-Py {
    foreach ($c in @('python', 'python3', 'py')) {
        if (Get-Command $c -ErrorAction SilentlyContinue) { try { & $c -c "" 2>$null; if ($LASTEXITCODE -eq 0) { return $c } } catch {} }
    }
    return $null
}
function Copy-IfNewer {
    param($Src, $Dst)
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
    Copy-Item -Path (Join-Path $PlatformRoot "hooks") -Destination $RepoPath -Recurse -Force
    foreach ($s in @("scan-and-fix.ps1", "scan-and-fix.sh", "check-fix-allowlist.py", "validate-scan-config.py", "render-scan-config.py")) {
        Copy-IfNewer (Join-Path $PlatformRoot "scripts/$s") (Join-Path $RepoPath "scripts/$s")
    }
    Ok "Copied hooks/ and shared scripts/"
} else {
    Info "Running inside the platform repo; hooks/scripts already present"
}

# ---------------------------------------------------------------------------
# 3) Local runner
# ---------------------------------------------------------------------------
Step "Local runner: $HooksRunner"
if ($HooksRunner -eq "lefthook") {
    Copy-IfNewer (Join-Path $PlatformRoot "templates/lefthook/lefthook.yml") (Join-Path $RepoPath "lefthook.yml")
    if (Get-Command lefthook -ErrorAction SilentlyContinue) {
        Push-Location $RepoPath; try { lefthook install | Out-Null; Ok "lefthook installed" } finally { Pop-Location }
    } else {
        Warn "lefthook not on PATH. Install: 'choco install lefthook' or 'go install github.com/evilmartians/lefthook@latest', then 'lefthook install'"
    }
} else {
    $pcDest = Join-Path $RepoPath ".pre-commit-config.yaml"
    $pcSrc = Join-Path $PlatformRoot "templates/$Tier/pre-commit-config.yaml"
    if ((Test-Path $pcSrc) -and -not (Test-Path $pcDest)) { Copy-IfNewer $pcSrc $pcDest }
    if (Get-Command pre-commit -ErrorAction SilentlyContinue) {
        Push-Location $RepoPath; try { pre-commit install | Out-Null; pre-commit install --hook-type pre-push | Out-Null; Ok "pre-commit hooks installed" } finally { Pop-Location }
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
Ok "Caller workflows copied (remember to pin @vX.Y.Z)"

# ---------------------------------------------------------------------------
# 6) Labels + 7) Secret verification (fix-loop only)
# ---------------------------------------------------------------------------
if ($EnableFixLoop) {
    Step "Fix-loop: labels + secret verification"
    if (Get-Command gh -ErrorAction SilentlyContinue) {
        Push-Location $RepoPath
        try {
            try { gh label create "ai-autofix" --color 1D76DB --description "Opt this PR into the autonomous fix-loop" --force | Out-Null; Ok "label ai-autofix" } catch { Warn "could not create ai-autofix label: $_" }
            try { gh label create "needs-human-review" --color B60205 --description "Autonomous fix loop stopped; needs a human" --force | Out-Null; Ok "label needs-human-review" } catch { Warn "could not create needs-human-review label: $_" }

            $secrets = @()
            try { $secrets = (gh secret list --json name 2>$null | ConvertFrom-Json).name } catch { $secrets = (gh secret list 2>$null | ForEach-Object { ($_ -split '\s+')[0] }) }
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
if (Test-Path $verify) {
    Push-Location $RepoPath
    try { & pwsh -NoProfile -ExecutionPolicy Bypass -File $verify 2>&1 | Select-Object -First 30 } catch { Warn "verify-scanning reported issues: $_" } finally { Pop-Location }
} else { Info "verify-scanning.ps1 not found; skipping" }

Write-Host "`n=== SETUP COMPLETE ===" -ForegroundColor Green
Write-Host "Next:" -ForegroundColor Cyan
Write-Host "  1. Review scan-config.yaml (enabled languages, fix_loop)" -ForegroundColor White
Write-Host "  2. Pin the caller workflows' uses: to a release tag (never @main)" -ForegroundColor White
if ($HooksRunner -eq 'lefthook') { Write-Host "  3. Test: stage a file and 'git commit' (or 'lefthook run pre-commit')" -ForegroundColor White }
else { Write-Host "  3. Test: 'pre-commit run --all-files'" -ForegroundColor White }
if ($EnableFixLoop) { Write-Host "  4. Add the 'ai-autofix' label to a PR to opt it into the fix-loop" -ForegroundColor White }
exit 0
