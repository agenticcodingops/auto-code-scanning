# stop-scan.ps1 — final mandatory scan before Claude Code finishes.
# Guarded by stop_hook_active so it blocks at most once per stop-chain (no loops).
# Runs the shared scan-and-fix (default: secrets) and blocks the stop (exit 2) on
# findings, surfacing them so Claude fixes before declaring done.
#
# Configure the gate scan via CC_STOP_SCAN_TYPE (secrets|semgrep|all). Default: secrets.
$ErrorActionPreference = 'Continue'

$raw = [Console]::In.ReadToEnd()
$stopHookActive = $false
if ($raw) {
    try { $stopHookActive = [bool]($raw | ConvertFrom-Json).stop_hook_active } catch { $stopHookActive = $false }
}
# Loop guard: only ever block once per stop-chain.
if ($stopHookActive) { exit 0 }

$scanType = if ($env:CC_STOP_SCAN_TYPE) { $env:CC_STOP_SCAN_TYPE } else { 'secrets' }
$findingsPath = '.claude/scan-findings.json'
if (Test-Path $findingsPath) { Remove-Item $findingsPath -ErrorAction SilentlyContinue }

# Prefer the installed shared script; resolve a couple of likely locations.
$scanScript = $null
foreach ($cand in @('scripts/scan-and-fix.ps1', 'scan-and-fix.ps1', '.scanning/scripts/scan-and-fix.ps1')) {
    if (Test-Path $cand) { $scanScript = $cand; break }
}
if (-not $scanScript) {
    [Console]::Error.WriteLine("Stop hook: scan-and-fix.ps1 not found; skipping (install via setup-scanning).")
    exit 0
}

& pwsh -NoProfile -ExecutionPolicy Bypass -File $scanScript -ScanType $scanType -AutoFix *> $null
$scanExit = $LASTEXITCODE

if (($scanExit -ne 0) -or (Test-Path $findingsPath)) {
    [Console]::Error.WriteLine("Stop hook: the mandatory '$scanType' scan failed (exit=$scanExit); fix before finishing.")
    if (Test-Path $findingsPath) {
        try {
            $doc = Get-Content $findingsPath -Raw | ConvertFrom-Json
            foreach ($f in $doc.findings) {
                if (-not $f.passed) {
                    [Console]::Error.WriteLine("  [$($f.tool)] exit=$($f.exitCode)")
                    foreach ($issue in (@($f.issues) | Select-Object -First 15)) {
                        [Console]::Error.WriteLine("    $issue")
                    }
                }
            }
        } catch {
            [Console]::Error.WriteLine("  (could not parse $findingsPath)")
        }
    }
    [Console]::Error.WriteLine("Resolve these (move secrets to env vars / a vault), then finish.")
    exit 2
}
exit 0
