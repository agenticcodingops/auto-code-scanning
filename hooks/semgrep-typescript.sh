#!/usr/bin/env bash
# semgrep-typescript.sh — Semgrep SAST for TypeScript/JavaScript (p/typescript)
# Stage: pre-commit | Mode: scan ONLY staged ts/tsx/js/jsx files
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

require_tool "semgrep" || exit 0

export PYTHONUTF8=1
export SEMGREP_SEND_METRICS=off

mapfile -t files < <(get_staged_files ts tsx js jsx)
if [[ ${#files[@]} -eq 0 ]]; then
    hook_log "PASS: No TypeScript/JavaScript files staged"
    exit 0
fi

ruleset="${SEMGREP_RULESET_TYPESCRIPT:-p/typescript}"

start_timer
hook_log "Scanning... (${#files[@]} TS/JS files, ${ruleset})"

semgrep_cmd=(semgrep scan --config "${ruleset}" --error --metrics off --quiet)
[[ $# -gt 0 ]] && semgrep_cmd+=("$@")
semgrep_cmd+=("${files[@]}")

set +e
output="$("${semgrep_cmd[@]}" 2>&1)"
exit_code=$?
set -e

duration_ms="$(stop_timer)"

if [[ ${exit_code} -eq 0 ]]; then
    hook_log "PASS: No findings (${duration_ms}ms)"
    write_scan_json "$(build_pass_json "semgrep-typescript" "." "${duration_ms}")"
    exit 0
elif [[ ${exit_code} -eq 1 ]]; then
    echo "${output}"
    hook_log "FAIL: Semgrep (p/typescript) found issues"
    write_scan_json "$(build_findings_json "semgrep-typescript" "." "${duration_ms}" "[]" 0 1 0 0)"
    exit 1
else
    handle_exit_code ${exit_code}
    exit 0
fi
