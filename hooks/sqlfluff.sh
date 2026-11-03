#!/usr/bin/env bash
# sqlfluff.sh — SQLFluff linting for staged .sql files
# Stage: pre-commit | Mode: staged .sql only
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

run_staged_snapshot "$@"

require_tool "sqlfluff" || exit 0

read_nul_paths files get_staged_files sql
if [[ ${#files[@]} -eq 0 ]]; then
    hook_log "PASS: No SQL files staged"
    exit 0
fi

# A CLI dialect overrides nested configs too. Batch configured files separately
# so unconfigured siblings keep the default without overriding project settings.
configured_files=()
default_files=()
for file in "${files[@]}"; do
    directory="$(dirname -- "$file")"
    configured=0
    while :; do
        if [[ -f "$directory/.sqlfluff" ]]; then configured=1; break; fi
        [[ "$directory" != . ]] || break
        directory="$(dirname -- "$directory")"
    done
    if [[ "$configured" == 1 ]]; then configured_files+=("$file"); else default_files+=("$file"); fi
done

start_timer
hook_log "Linting... (${#files[@]} SQL files, project dialects or ansi default)"
output=''
exit_code=0
for group in configured default; do
    sqlfluff_cmd=(sqlfluff lint)
    if [[ "$group" == configured ]]; then
        [[ ${#configured_files[@]} -gt 0 ]] || continue
        selected_files=("${configured_files[@]}")
    else
        [[ ${#default_files[@]} -gt 0 ]] || continue
        selected_files=("${default_files[@]}")
        sqlfluff_cmd+=(--dialect ansi)
    fi
    [[ $# -gt 0 ]] && sqlfluff_cmd+=("$@")
    sqlfluff_cmd+=(-- "${selected_files[@]}")
    set +e
    group_output="$("${sqlfluff_cmd[@]}" 2>&1)"
    group_exit=$?
    set -e
    output+="${group_output}"$'\n'
    if [[ $group_exit -eq 1 ]]; then
        exit_code=1
    elif [[ $group_exit -ne 0 ]]; then
        handle_exit_code "$group_exit"
    fi
done

duration_ms="$(stop_timer)"

if [[ ${exit_code} -eq 0 ]]; then
    hook_log "PASS: SQLFluff clean (${duration_ms}ms)"
    write_scan_json "$(build_pass_json "sqlfluff" "." "${duration_ms}")"
    exit 0
elif [[ ${exit_code} -eq 1 ]]; then
    echo "${output}"
    hook_log "FAIL: SQLFluff lint issues"
    write_scan_json "$(build_findings_json "sqlfluff" "." "${duration_ms}" "[]" 0 0 1 0)"
    exit 1
else
    handle_exit_code ${exit_code}
    exit 0
fi
