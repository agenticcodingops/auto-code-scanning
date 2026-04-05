#!/usr/bin/env bash
# validate-suppressions.sh — Shell wrapper for Python suppression validator
# Called by dispatcher.sh on Unix/macOS systems

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

SCAN_CONFIG_DIR="${SCAN_CONFIG_DIR:-.scanning/configs}"

# Find Python interpreter
PYTHON=""
if python3 --version &>/dev/null 2>&1; then
    PYTHON="python3"
elif python --version &>/dev/null 2>&1; then
    PYTHON="python"
else
    hook_warn "Python not found — cannot run suppression validation"
    exit 0  # fail-open
fi

# Run the Python validator
hook_verbose "Running suppression validation with $PYTHON"

SUPPRESSION_FILE="${SCAN_CONFIG_DIR}/.scan-suppressions.yaml"
if [[ ! -f "$SUPPRESSION_FILE" ]]; then
    hook_verbose "No suppression file found at $SUPPRESSION_FILE — skipping"
    exit 0
fi

exit_code=0
"$PYTHON" "${SCRIPT_DIR}/validate-suppressions.py" "$SUPPRESSION_FILE" || exit_code=$?

handle_exit_code "$exit_code" "validate-suppressions"
