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
        for config in setup.cfg tox.ini pep8.ini; do
            if [[ -f "$directory/$config" ]] && grep -Eq '^[[:space:]]*\[sqlfluff(:|\])' "$directory/$config"; then
                configured=1
            fi
        done
        if [[ -f "$directory/pyproject.toml" ]] && grep -Eq '^[[:space:]]*\[tool\.sqlfluff(\.|\])' "$directory/pyproject.toml"; then
            configured=1
        fi
        [[ "$configured" == 0 ]] || break
        [[ "$directory" != . ]] || break
        directory="$(dirname -- "$directory")"
    done
    if [[ "$configured" == 1 ]]; then configured_files+=("$file"); else default_files+=("$file"); fi
done

start_timer
hook_log "Linting... (${#files[@]} SQL files, project dialects or ansi default)"
results="$(mktemp -d)"
trap 'rm -rf -- "$results"' EXIT
exit_code=0
tool_errors=()
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
    "${sqlfluff_cmd[@]}" > "$results/$group.output" 2>&1
    group_exit=$?
    set -e
    printf '%s\n' "$group_exit" > "$results/$group.exit"
    if [[ $group_exit -eq 1 ]]; then
        exit_code=1
    elif [[ $group_exit -ne 0 ]]; then
        tool_errors+=("$group_exit")
    fi
done

duration_ms="$(stop_timer)"
py="$(find_python)" || { hook_error 'Python is required for SQL lint reports'; exit 1; }
report="$("$py" -I "$SCRIPT_DIR/lib/sqlfluff_report.py" "$results" "$duration_ms")"
write_scan_json "$report"
for group in configured default; do
    [[ ! -f "$results/$group.output" ]] || cat -- "$results/$group.output"
done

if [[ ${exit_code} -eq 1 ]]; then
    hook_log "FAIL: SQLFluff lint issues"
elif [[ ${#tool_errors[@]} -eq 0 ]]; then
    hook_log "PASS: SQLFluff clean (${duration_ms}ms)"
fi
for code in "${tool_errors[@]}"; do
    if ! handle_exit_code "$code"; then exit_code=1; fi
done
exit "$exit_code"
