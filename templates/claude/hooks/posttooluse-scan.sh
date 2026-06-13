#!/usr/bin/env bash
# posttooluse-scan.sh — in-session, per-file scan for Claude Code (bash twin).
# Fires after Write|Edit|MultiEdit; scans ONLY the edited file and exits 2 with
# findings on stderr so Claude self-corrects within the session. Fail-open if a
# tool is missing. Escape hatches: CC_SKIP_SEMGREP_HOOK=1, CC_SKIP_SECRET_HOOK=1
set -uo pipefail

raw="$(cat)"
# Find a python that ACTUALLY runs (skip the broken Windows Store python3 shim).
py=""
for c in python python3 py; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c "" >/dev/null 2>&1; then py="$c"; break; fi
done
file_path=""
if [[ -n "${py}" ]]; then
    file_path="$(printf '%s' "${raw}" | "${py}" -c "import json,sys
try:
    print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))
except Exception:
    print('')" 2>/dev/null)"
fi
[[ -z "${file_path}" ]] && exit 0
[[ -f "${file_path}" ]] || exit 0

export PYTHONUTF8=1 SEMGREP_SEND_METRICS=off
ext="${file_path##*.}"
rc=0

semgrep_file() {
    local ruleset="$1" path="$2"
    [[ "${CC_SKIP_SEMGREP_HOOK:-0}" == "1" ]] && return 0
    command -v semgrep >/dev/null 2>&1 || return 0
    if ! out="$(semgrep scan --config "${ruleset}" --error --metrics off --quiet "${path}" 2>&1)"; then
        echo "PostToolUse: semgrep (${ruleset}) found issues in ${path}" >&2
        echo "${out}" >&2
        rc=2
    fi
}

secret_file() {
    local path="$1"
    [[ "${CC_SKIP_SECRET_HOOK:-0}" == "1" ]] && return 0
    command -v trivy >/dev/null 2>&1 || return 0
    if ! out="$(trivy fs "${path}" --scanners secret --severity CRITICAL,HIGH --exit-code 1 --quiet 2>&1)"; then
        echo "PostToolUse: secret detected in ${path}" >&2
        echo "${out}" >&2
        rc=2
    fi
}

cs_ruleset="${SEMGREP_RULESET_CSHARP:-p/csharp}"
ts_ruleset="${SEMGREP_RULESET_TYPESCRIPT:-p/typescript}"
case ".${ext}" in
    .cs)            semgrep_file "${cs_ruleset}" "${file_path}" ;;
    .ts|.tsx|.js|.jsx) semgrep_file "${ts_ruleset}" "${file_path}" ;;
esac
secret_file "${file_path}"

if [[ ${rc} -eq 2 ]]; then
    echo "Fix the above before continuing (in-session self-correction)." >&2
    exit 2
fi
exit 0
