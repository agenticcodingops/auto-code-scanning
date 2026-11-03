#!/usr/bin/env bash
# posttooluse-scan.sh â€” in-session, per-file scan for Claude Code (bash twin).
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
    local path="$1" out code
    [[ "${CC_SKIP_SECRET_HOOK:-0}" == "1" ]] && return 0
    command -v trivy >/dev/null 2>&1 || return 0
    out="$(trivy fs "${path}" --scanners secret --severity CRITICAL,HIGH --exit-code 1 --quiet --format json 2>/dev/null)"
    code=$?
    if [[ $code -ne 0 && $code -ne 1 ]]; then
        echo 'PostToolUse: secret scan failed (details redacted).' >&2
        rc=2
        return
    fi
    # Project only metadata; neither raw output nor parser errors reach feedback.
    printf '%s' "$out" | "$py" -c '
import json,sys
try:
    data=json.load(sys.stdin)
    if not isinstance(data,dict) or not ("Results" in data or type(data.get("SchemaVersion")) is int): raise ValueError()
    if data.get("error") or data.get("errors"): raise ValueError()
    results=data.get("Results",[])
    if not isinstance(results,list): raise ValueError()
    rows=[]
    for result in results:
        if not isinstance(result,dict) or not isinstance(result.get("Target"),str): raise ValueError()
        secrets=result.get("Secrets",[])
        if not isinstance(secrets,list): raise ValueError()
        for secret in secrets:
            if not isinstance(secret,dict): raise ValueError()
            rule,line=secret.get("RuleID"),secret.get("StartLine")
            if not isinstance(rule,str) or not rule or type(line) is not int or line<1: raise ValueError()
            rows.append(dict(file=result["Target"],line=line,rule=rule))
    for row in rows:
        print(json.dumps(row),file=sys.stderr)
    if rows:
        print("PostToolUse: secret finding count="+str(len(rows)),file=sys.stderr)
        sys.exit(2)
except Exception:
    print("PostToolUse: secret scan report invalid (details redacted).",file=sys.stderr)
    sys.exit(2)
' >&2 || rc=2
    if [[ $code -eq 1 ]]; then rc=2; fi
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
