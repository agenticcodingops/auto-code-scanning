#!/usr/bin/env bash
# stop-scan.sh — final mandatory scan before Claude Code finishes (bash twin).
# Guarded by stop_hook_active so it blocks at most once per stop-chain.
# Runs the shared scan-and-fix (default: secrets); exit 2 blocks the stop on findings.
# Configure via CC_STOP_SCAN_TYPE (secrets|semgrep|all). Default: secrets.
set -uo pipefail

raw="$(cat)"
py=""
for c in python python3 py; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c "" >/dev/null 2>&1; then py="$c"; break; fi
done
stop_active=0
if [[ -n "${py}" ]]; then
    stop_active="$(printf '%s' "${raw}" | "${py}" -c "import json,sys
try:
    print(1 if json.load(sys.stdin).get('stop_hook_active') else 0)
except Exception:
    print(0)" 2>/dev/null)"
fi
# Loop guard.
[[ "${stop_active}" == "1" ]] && exit 0

scan_type="${CC_STOP_SCAN_TYPE:-secrets}"
findings=".claude/scan-findings.json"
rm -f "${findings}" 2>/dev/null || true

scan_script=""
for cand in scripts/scan-and-fix.sh scan-and-fix.sh .scanning/scripts/scan-and-fix.sh; do
    [[ -f "${cand}" ]] && { scan_script="${cand}"; break; }
done
if [[ -z "${scan_script}" ]]; then
    echo "Stop hook: scan-and-fix.sh not found; skipping (install via setup-scanning)." >&2
    exit 0
fi

bash "${scan_script}" "${scan_type}" --auto-fix >/dev/null 2>&1
scan_exit=$?

if [[ ${scan_exit} -ne 0 || -f "${findings}" ]]; then
    echo "Stop hook: the mandatory '${scan_type}' scan failed (exit=${scan_exit}); fix before finishing." >&2
    echo "Resolve findings (move secrets to env vars / a vault), then finish." >&2
    exit 2
fi
exit 0
