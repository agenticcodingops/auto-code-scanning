#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
PYTHON="$(find_python)" || { hook_error "Suppression validation requires Python"; exit 1; }
# Resolve suppressions.file using the same strict resolver as CI.
SUPPRESSION_FILE="$("$PYTHON" "${SCRIPT_DIR}/../scripts/scan_policy.py")"
[[ -f "$SUPPRESSION_FILE" ]] || exit 0
args=()
[[ "${SCAN_ALLOW_LEGACY_EXCEPTIONS:-0}" == 1 ]] && args+=(--allow-legacy-exceptions)
"$PYTHON" "${SCRIPT_DIR}/validate-suppressions.py" "${args[@]}" -- "$SUPPRESSION_FILE"
