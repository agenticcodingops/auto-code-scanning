#!/usr/bin/env bash
# dispatcher.sh — OS-detecting dispatcher for pre-commit hooks
# Routes to .sh (Unix) or .ps1 (Windows) based on OS detection
# Usage: hooks/dispatcher.sh <hook-id> [args...]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

HOOK_ID="${1:?Error: hook-id argument is required}"
shift

# Export environment variables for hook scripts
export SCAN_HOOK_ID="${HOOK_ID}"
export SCAN_VERBOSE="${SCAN_VERBOSE:-0}"
export SCAN_CONFIG_DIR="${SCAN_CONFIG_DIR:-.scanning/configs}"

# OS detection and routing
case "${OSTYPE:-}" in
    msys*|cygwin*|mingw*|win*)
        # Windows — prefer PowerShell if available
        if command -v pwsh >/dev/null 2>&1; then
            exec pwsh -NoProfile -ExecutionPolicy Bypass -File "${SCRIPT_DIR}/${HOOK_ID}.ps1" "$@"
        elif command -v powershell >/dev/null 2>&1; then
            exec powershell -NoProfile -ExecutionPolicy Bypass -File "${SCRIPT_DIR}/${HOOK_ID}.ps1" "$@"
        else
            # Fallback to bash on Windows if no PowerShell
            exec "${SCRIPT_DIR}/${HOOK_ID}.sh" "$@"
        fi
        ;;
    *)
        # Unix (Linux, macOS, etc.)
        exec "${SCRIPT_DIR}/${HOOK_ID}.sh" "$@"
        ;;
esac
