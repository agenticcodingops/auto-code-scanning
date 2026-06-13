# posttooluse-scan.ps1 — in-session, per-file scan for Claude Code.
# Fires after Write|Edit|MultiEdit. Scans ONLY the edited file by language and
# exits 2 (with findings on stderr) so Claude self-corrects within the session.
# Thin by design: routes to the right tool/ruleset; heavy logic lives in the
# shared dispatcher hooks + scan-and-fix. Fail-open if a tool is missing.
#
# Skips (escape hatches): CC_SKIP_SEMGREP_HOOK=1, CC_SKIP_SECRET_HOOK=1
$ErrorActionPreference = 'Continue'

# Read the hook payload (JSON on stdin) to find the edited file.
$raw = [Console]::In.ReadToEnd()
$filePath = $null
if ($raw) {
    try { $filePath = ($raw | ConvertFrom-Json).tool_input.file_path } catch { }
}
if (-not $filePath) { exit 0 }
if (-not [System.IO.Path]::IsPathRooted($filePath)) { $filePath = Join-Path (Get-Location) $filePath }
if (-not (Test-Path $filePath)) { exit 0 }

$ext = [System.IO.Path]::GetExtension($filePath).ToLowerInvariant()
$env:PYTHONUTF8 = '1'
$env:SEMGREP_SEND_METRICS = 'off'

function Invoke-SemgrepFile {
    param([string]$Ruleset, [string]$Path)
    if ($env:CC_SKIP_SEMGREP_HOOK -eq '1') { return 0 }
    if (-not (Get-Command semgrep -ErrorAction SilentlyContinue)) { return 0 }
    $out = & semgrep scan --config $Ruleset --error --metrics off --quiet $Path 2>&1
    if ($LASTEXITCODE -ne 0) {
        [Console]::Error.WriteLine("PostToolUse: semgrep ($Ruleset) found issues in $Path")
        $out | ForEach-Object { [Console]::Error.WriteLine("  $_") }
        return 2
    }
    return 0
}

function Invoke-SecretFile {
    param([string]$Path)
    if ($env:CC_SKIP_SECRET_HOOK -eq '1') { return 0 }
    if (-not (Get-Command trivy -ErrorAction SilentlyContinue)) { return 0 }
    $out = & trivy fs $Path --scanners secret --severity CRITICAL,HIGH --exit-code 1 --quiet 2>&1
    if ($LASTEXITCODE -eq 1) {
        [Console]::Error.WriteLine("PostToolUse: secret detected in $Path")
        $out | ForEach-Object { [Console]::Error.WriteLine("  $_") }
        return 2
    }
    return 0
}

$csRuleset = if ($env:SEMGREP_RULESET_CSHARP) { $env:SEMGREP_RULESET_CSHARP } else { 'p/csharp' }
$tsRuleset = if ($env:SEMGREP_RULESET_TYPESCRIPT) { $env:SEMGREP_RULESET_TYPESCRIPT } else { 'p/typescript' }
$rc = 0
switch -Regex ($ext) {
    '\.cs$'                 { $rc = [Math]::Max($rc, (Invoke-SemgrepFile $csRuleset $filePath)) }
    '\.(ts|tsx|js|jsx)$'    { $rc = [Math]::Max($rc, (Invoke-SemgrepFile $tsRuleset $filePath)) }
}
# Secret scan on every edited file (cheap, single-file).
$rc = [Math]::Max($rc, (Invoke-SecretFile $filePath))

if ($rc -eq 2) {
    [Console]::Error.WriteLine("Fix the above before continuing (in-session self-correction).")
    exit 2
}
exit 0
