#!/usr/bin/env bash
# semgrep-csharp.sh — Semgrep SAST for C# (p/csharp ruleset)
# Stage: pre-commit | Mode: scan ONLY staged .cs files | native, no network
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

require_tool "semgrep" || exit 0

# Native path (Fall-2025) + UTF-8 so Semgrep runs without WSL on Windows.
export PYTHONUTF8=1
export SEMGREP_SEND_METRICS=off

mapfile -t files < <(get_staged_files cs)
if [[ ${#files[@]} -eq 0 ]]; then
    hook_log "PASS: No C# files staged"
    exit 0
fi

# Ruleset is overridable (tests/consumers); defaults to the registry pack.
ruleset="${SEMGREP_RULESET_CSHARP:-p/csharp}"

start_timer
hook_log "Scanning... (${#files[@]} C# files, ${ruleset})"

semgrep_cmd=(semgrep scan --config "${ruleset}" --error --metrics off --quiet)
# Pass-through extra args (e.g. from .pre-commit/lefthook), then the staged files.
[[ $# -gt 0 ]] && semgrep_cmd+=("$@")
semgrep_cmd+=("${files[@]}")

set +e
output="$("${semgrep_cmd[@]}" 2>&1)"
exit_code=$?
set -e

duration_ms="$(stop_timer)"

if [[ ${exit_code} -eq 0 ]]; then
    hook_log "PASS: No findings (${duration_ms}ms)"
    write_scan_json "$(build_pass_json "semgrep-csharp" "." "${duration_ms}")"
    exit 0
elif [[ ${exit_code} -eq 1 ]]; then
    echo "${output}"
    hook_log "FAIL: Semgrep (p/csharp) found issues"
    write_scan_json "$(build_findings_json "semgrep-csharp" "." "${duration_ms}" "[]" 0 1 0 0)"
    exit 1
else
    # Infrastructure error — fail-open
    handle_exit_code ${exit_code}
    exit 0
fi
