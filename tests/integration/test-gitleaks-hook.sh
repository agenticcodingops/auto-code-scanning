#!/usr/bin/env bash
# Regression test for the Gitleaks pre-commit hook.
# Builds a throwaway git repo and three fake secrets at runtime.
# Nothing under this repository is given a credential-shaped value.
# Usage: tests/integration/test-gitleaks-hook.sh [sh|ps1]
set -euo pipefail

impl="${1:-sh}"
if [[ "${impl}" != "sh" && "${impl}" != "ps1" ]]; then
    echo "usage: $0 [sh|ps1]" >&2
    exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if ! command -v gitleaks >/dev/null 2>&1; then
    echo "FAIL: gitleaks is not on PATH" >&2
    exit 1
fi

if ! command -v git >/dev/null 2>&1; then
    echo "FAIL: git is not on PATH" >&2
    exit 1
fi

py=""
# The Windows "python3" app-execution alias exists and does not run Python.
for candidate in python3 python py; do
    if command -v "${candidate}" >/dev/null 2>&1 && "${candidate}" -c "import json" >/dev/null 2>&1; then
        py="${candidate}"
        break
    fi
done
if [[ -z "${py}" ]]; then
    echo "FAIL: python is required to generate the runtime fixtures" >&2
    exit 1
fi

if [[ "${impl}" == "ps1" ]] && ! command -v pwsh >/dev/null 2>&1; then
    echo "FAIL: pwsh is required to run hooks/gitleaks.ps1" >&2
    exit 1
fi

work="$(mktemp -d)"
empty_hooks="$(mktemp -d)"
parser_free="$(mktemp -d)"
stub_dir="$(mktemp -d)"
cleanup() {
    rm -rf "${work}" "${empty_hooks}" "${parser_free}" "${stub_dir}"
}
trap cleanup EXIT

cd "${work}"
git init -q
git config user.email "scanner-eval@example.invalid"
git config user.name "scanner-eval"
git config commit.gpgsign false

# Deterministic high-entropy fakes. The strings stay in this temp repo.
"${py}" - <<'PY'
import hashlib
import json
import pathlib

alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

def token(label, size):
    out = []
    counter = 0
    while len(out) < size:
        digest = hashlib.sha256(f"{label}:{counter}".encode()).digest()
        counter += 1
        for byte in digest:
            out.append(alphabet[byte % len(alphabet)])
            if len(out) == size:
                break
    return "".join(out)

stripe = "sk_live_" + token("stripe", 24)
github = "ghp_" + token("github", 36)
slack = (
    "https://hooks.slack.com/services/T"
    + token("slackT", 10)
    + "/B"
    + token("slackB", 10)
    + "/"
    + token("slackS", 24)
)
pathlib.Path("sample.txt").write_text(
    stripe + "\n" + github + "\n" + slack + "\n",
    encoding="utf-8",
)
pathlib.Path(".runtime-secrets.json").write_text(
    json.dumps([stripe, github, slack]),
    encoding="utf-8",
)
PY

git add sample.txt

export SCAN_HOOK_ID="gitleaks"
export SCAN_CONFIG_DIR="${work}/.scanning/configs"
mkdir -p "${SCAN_CONFIG_DIR}"

# PATH for the hook under test. The default is this process's PATH.
# Invoke bash by absolute path: a PATH= prefix is applied before command
# lookup, so `PATH=<dir> bash` cannot find bash when <dir> has no bash.
hook_path="${PATH}"
hook_path_prefix_win=""
bash_bin="$(command -v bash)"

# Bash-only. Copy the hook's external commands into one directory so python
# and jq, wherever they live on this machine, are not visible. Each wrapper
# execs the real binary by absolute path.
write_exec_wrapper() {
    local name="$1"
    local target="$2"
    printf '#!/bin/sh\nexec "%s" "$@"\n' "${target}" > "${parser_free}/${name}"
    chmod +x "${parser_free}/${name}"
}

prepare_parser_free_path() {
    local tool target
    for tool in gitleaks git mktemp wc date mkdir rm cat dirname; do
        target="$(command -v "${tool}" 2>/dev/null || true)"
        if [[ -z "${target}" ]]; then
            echo "FAIL: ${tool} is required to build a parser-free PATH" >&2
            exit 1
        fi
        write_exec_wrapper "${tool}" "${target}"
    done
    if command -v cygpath >/dev/null 2>&1; then
        write_exec_wrapper cygpath "$(command -v cygpath)"
        # gitleaks.exe looks up git with Windows PATHEXT. A shell script named
        # git is invisible to it, so the scan exits 1 with no JSON report.
        # git.cmd is the same git binary, and bash still prefers the `git` script.
        win_git="$(cygpath -w "$(command -v git)")"
        printf '@echo off\r\n"%s" %%*\r\n' "${win_git}" > "${parser_free}/git.cmd"
    fi
    if env PATH="${parser_free}" "${bash_bin}" -c 'command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1 || command -v jq >/dev/null 2>&1'; then
        echo "FAIL: parser-free PATH still contains python or jq" >&2
        exit 1
    fi
    if ! env PATH="${parser_free}" "${bash_bin}" -c 'command -v gitleaks >/dev/null && command -v git >/dev/null && command -v mktemp >/dev/null'; then
        echo "FAIL: parser-free PATH is missing gitleaks, git, or mktemp" >&2
        exit 1
    fi
}

run_hook() {
    local out_file="$1"
    local err_file="$2"
    local status=0
    if [[ "${impl}" == "ps1" ]]; then
        local hook_ps1="${REPO_ROOT}/hooks/gitleaks.ps1"
        if command -v cygpath >/dev/null 2>&1; then
            hook_ps1="$(cygpath -w "${hook_ps1}")"
        fi
        # -File, not -Command. A script's exit is the process exit only when
        # that script is the -File target. Prepend the stub directory in this
        # shell so MSYS converts PATH for pwsh and `exit` in the hook is kept.
        if [[ -n "${hook_path_prefix_win}" ]]; then
            PATH="${hook_path_prefix_win}:${PATH}" pwsh -NoProfile -File "${hook_ps1}" >"${out_file}" 2>"${err_file}" || status=$?
        else
            pwsh -NoProfile -File "${hook_ps1}" >"${out_file}" 2>"${err_file}" || status=$?
        fi
    else
        PATH="${hook_path}" "${bash_bin}" "${REPO_ROOT}/hooks/gitleaks.sh" >"${out_file}" 2>"${err_file}" || status=$?
    fi
    printf '%s' "${status}"
}

assert_no_secrets() {
    local label="$1"
    shift
    "${py}" - "${label}" "$@" <<'PY'
import json
import pathlib
import sys

label = sys.argv[1]
paths = sys.argv[2:]
secrets = json.loads(pathlib.Path(".runtime-secrets.json").read_text(encoding="utf-8"))
for path in paths:
    file_path = pathlib.Path(path)
    if not file_path.exists():
        continue
    blob = file_path.read_text(encoding="utf-8", errors="replace")
    for index, secret in enumerate(secrets):
        if secret and secret in blob:
            sys.stderr.write(f"FAIL: {label}: runtime secret {index} was written to {path}\n")
            sys.exit(1)
scan = pathlib.Path(".scanning/last-scan.json")
if scan.exists():
    blob = scan.read_text(encoding="utf-8", errors="replace")
    for index, secret in enumerate(secrets):
        if secret and secret in blob:
            sys.stderr.write(f"FAIL: {label}: runtime secret {index} was stored in .scanning/last-scan.json\n")
            sys.exit(1)
PY
}

out_file="$(mktemp)"
err_file="$(mktemp)"

echo "=== ${impl}: three staged findings ==="
status="$(run_hook "${out_file}" "${err_file}")"
if [[ "${status}" -ne 1 ]]; then
    echo "FAIL: expected exit 1, got ${status}" >&2
    echo "---- stdout ----" >&2
    cat "${out_file}" >&2
    echo "---- stderr ----" >&2
    cat "${err_file}" >&2
    exit 1
fi
assert_no_secrets "findings" "${out_file}" "${err_file}"
"${py}" - "${out_file}" "${err_file}" <<'PY'
import json
import pathlib
import sys

out_path, err_path = sys.argv[1:3]
shown = pathlib.Path(out_path).read_text(encoding="utf-8", errors="replace")
shown += pathlib.Path(err_path).read_text(encoding="utf-8", errors="replace")
scan = json.loads(pathlib.Path(".scanning/last-scan.json").read_text(encoding="utf-8"))
summary = scan["summary"]
if summary["total_findings"] != 3:
    sys.stderr.write(f"FAIL: total_findings={summary['total_findings']}\n")
    sys.exit(1)
if summary["by_severity"]["HIGH"] != 3:
    sys.stderr.write("FAIL: HIGH count is not 3\n")
    sys.exit(1)
findings = scan["findings"]
if len(findings) != 3:
    sys.stderr.write(f"FAIL: findings length={len(findings)}\n")
    sys.exit(1)
rules = sorted(item["rule_id"] for item in findings)
expected = ["github-pat", "slack-webhook-url", "stripe-access-token"]
if rules != expected:
    sys.stderr.write(f"FAIL: rules={rules}\n")
    sys.exit(1)
for item in findings:
    if item["tool"] != "gitleaks" or item["severity"] != "HIGH":
        sys.stderr.write("FAIL: tool or severity\n")
        sys.exit(1)
    if not str(item["file"]).replace("\\", "/").endswith("sample.txt"):
        sys.stderr.write(f"FAIL: file={item['file']}\n")
        sys.exit(1)
    if not isinstance(item["line"], int) or item["line"] < 1:
        sys.stderr.write(f"FAIL: line={item['line']}\n")
        sys.exit(1)
    if not item["message"]:
        sys.stderr.write(f"FAIL: empty message for {item['rule_id']}\n")
        sys.exit(1)
    for forbidden in ("Match", "Secret", "secret", "match"):
        if forbidden in item:
            sys.stderr.write(f"FAIL: finding has {forbidden}\n")
            sys.exit(1)
    if item["rule_id"] not in shown or "sample.txt" not in shown:
        sys.stderr.write(f"FAIL: stdout missing rule or file for {item['rule_id']}\n")
        sys.stderr.write(shown + "\n")
        sys.exit(1)
    if f":{item['line']}" not in shown and f":{item['line']}-" not in shown:
        sys.stderr.write(f"FAIL: stdout missing line for {item['rule_id']}\n")
        sys.exit(1)
print("PASS: 3 findings with rule, file, and line, and no secret value")
PY

if [[ "${impl}" == "sh" ]]; then
    echo "=== sh: JSON findings report and no parser ==="
    prepare_parser_free_path
    hook_path="${parser_free}"
    status="$(run_hook "${out_file}" "${err_file}")"
    hook_path="${PATH}"
    if [[ "${status}" -ne 1 ]]; then
        echo "FAIL: no-parser findings expected exit 1, got ${status}" >&2
        echo "---- stdout ----" >&2
        cat "${out_file}" >&2
        echo "---- stderr ----" >&2
        cat "${err_file}" >&2
        exit 1
    fi
    assert_no_secrets "no-parser" "${out_file}" "${err_file}"
    "${py}" - "${out_file}" "${err_file}" <<'PY'
import json
import pathlib
import sys

out_path, err_path = sys.argv[1:3]
shown = (
    pathlib.Path(out_path).read_text(encoding="utf-8", errors="replace")
    + pathlib.Path(err_path).read_text(encoding="utf-8", errors="replace")
)
if "fail-open" in shown.lower():
    sys.stderr.write("FAIL: no-parser findings fail-opened\n")
    sys.stderr.write(shown + "\n")
    sys.exit(1)
if "RuleID" in shown or "Secret" in shown or "Match" in shown:
    sys.stderr.write("FAIL: no-parser path printed the Gitleaks report\n")
    sys.exit(1)
scan = json.loads(pathlib.Path(".scanning/last-scan.json").read_text(encoding="utf-8"))
findings = scan["findings"]
if scan["summary"]["total_findings"] != 1 or len(findings) != 1:
    sys.stderr.write(
        "FAIL: no-parser findings count total="
        + str(scan["summary"]["total_findings"])
        + " rules="
        + str([item.get("rule_id") for item in findings])
        + "\n"
    )
    sys.exit(1)
item = findings[0]
if item["rule_id"] != "gitleaks-report-unparsed" or item["tool"] != "gitleaks":
    sys.stderr.write(f"FAIL: no-parser finding={item}\n")
    sys.exit(1)
if "Python" not in item["message"] and "jq" not in item["message"]:
    sys.stderr.write("FAIL: no-parser message does not name a parser\n")
    sys.exit(1)
if "gitleaks-report-unparsed" not in shown:
    sys.stderr.write("FAIL: no-parser stdout missing the rule id\n")
    sys.exit(1)
print("PASS: no parser blocked and did not print the report")
PY
fi

if [[ "${impl}" == "ps1" ]]; then
    echo "=== ps1: array-shaped report that cannot be parsed ==="
    # The stub replaces gitleaks. Its stdout is not valid JSON and must not
    # be copied into the hook output. ConvertFrom-Json is built in, so this
    # is the PowerShell twin of the bash no-parser block.
    printf '%s\r\n' '@echo off' 'echo [{"Secret":"SENTINEL-DO-NOT-LEAK"' 'exit /b 1' > "${stub_dir}/gitleaks.cmd"
    # Unix path. The bash PATH= prefix is what pwsh inherits.
    hook_path_prefix_win="${stub_dir}"
    status="$(run_hook "${out_file}" "${err_file}")"
    hook_path_prefix_win=""
    if [[ "${status}" -ne 1 ]]; then
        echo "FAIL: unparsed report expected exit 1, got ${status}" >&2
        echo "---- stdout ----" >&2
        cat "${out_file}" >&2
        echo "---- stderr ----" >&2
        cat "${err_file}" >&2
        exit 1
    fi
    assert_no_secrets "unparsed" "${out_file}" "${err_file}"
    if grep -q "SENTINEL-DO-NOT-LEAK" "${out_file}" "${err_file}" ".scanning/last-scan.json"; then
        echo "FAIL: unparsed report leaked the stub marker" >&2
        exit 1
    fi
    "${py}" - <<'PY'
import json
import pathlib
import sys

scan = json.loads(pathlib.Path(".scanning/last-scan.json").read_text(encoding="utf-8"))
findings = scan["findings"]
if scan["summary"]["total_findings"] != 1 or len(findings) != 1:
    sys.stderr.write("FAIL: unparsed findings count\n")
    sys.exit(1)
if findings[0]["rule_id"] != "gitleaks-report-unparsed":
    sys.stderr.write("FAIL: unparsed rule id\n")
    sys.exit(1)
print("PASS: unparsed array blocked and was not printed")
PY
fi

echo "=== ${impl}: broken config fail-open ==="
printf 'this is not toml [[[[\n' > "${SCAN_CONFIG_DIR}/.gitleaks.toml"
status="$(run_hook "${out_file}" "${err_file}")"
if [[ "${status}" -ne 0 ]]; then
    echo "FAIL: broken config expected exit 0, got ${status}" >&2
    echo "---- stdout ----" >&2
    cat "${out_file}" >&2
    echo "---- stderr ----" >&2
    cat "${err_file}" >&2
    exit 1
fi
assert_no_secrets "broken-config" "${out_file}" "${err_file}"
"${py}" - "${out_file}" "${err_file}" <<'PY'
import json
import pathlib
import sys

out_path, err_path = sys.argv[1:3]
shown = (
    pathlib.Path(out_path).read_text(encoding="utf-8", errors="replace")
    + pathlib.Path(err_path).read_text(encoding="utf-8", errors="replace")
)
if "FAIL:" in shown:
    sys.stderr.write("FAIL: broken config was counted as a finding\n")
    sys.stderr.write(shown + "\n")
    sys.exit(1)
if "fail-open" not in shown.lower():
    sys.stderr.write("FAIL: broken config did not warn fail-open\n")
    sys.stderr.write(shown + "\n")
    sys.exit(1)
scan = json.loads(pathlib.Path(".scanning/last-scan.json").read_text(encoding="utf-8"))
if scan["summary"]["total_findings"] != 0 or scan["findings"]:
    sys.stderr.write("FAIL: broken config stored findings\n")
    sys.exit(1)
print("PASS: broken config warned and allowed the commit")
PY

if [[ "${impl}" == "sh" ]]; then
    echo "=== sh: broken config and no parser ==="
    hook_path="${parser_free}"
    status="$(run_hook "${out_file}" "${err_file}")"
    hook_path="${PATH}"
    if [[ "${status}" -ne 0 ]]; then
        echo "FAIL: no-parser broken config expected exit 0, got ${status}" >&2
        cat "${out_file}" >&2
        cat "${err_file}" >&2
        exit 1
    fi
    assert_no_secrets "no-parser-broken-config" "${out_file}" "${err_file}"
    if ! grep -q "fail-open" "${out_file}" "${err_file}"; then
        echo "FAIL: no-parser broken config did not warn fail-open" >&2
        cat "${out_file}" >&2
        cat "${err_file}" >&2
        exit 1
    fi
    "${py}" - <<'PY'
import json
import pathlib
import sys

scan = json.loads(pathlib.Path(".scanning/last-scan.json").read_text(encoding="utf-8"))
if scan["summary"]["total_findings"] != 0 or scan["findings"]:
    sys.stderr.write("FAIL: no-parser broken config stored findings\n")
    sys.exit(1)
print("PASS: no-parser broken config still fail-open")
PY
fi

echo "=== ${impl}: clean staged file ==="
rm -f "${SCAN_CONFIG_DIR}/.gitleaks.toml"
printf 'hello\n' > sample.txt
git add sample.txt
status="$(run_hook "${out_file}" "${err_file}")"
if [[ "${status}" -ne 0 ]]; then
    echo "FAIL: clean file expected exit 0, got ${status}" >&2
    cat "${out_file}" >&2
    cat "${err_file}" >&2
    exit 1
fi
"${py}" - <<'PY'
import json
import pathlib
import sys

scan = json.loads(pathlib.Path(".scanning/last-scan.json").read_text(encoding="utf-8"))
if scan["summary"]["total_findings"] != 0 or scan["findings"]:
    sys.stderr.write("FAIL: clean file stored findings\n")
    sys.exit(1)
print("PASS: clean staged file")
PY

if [[ "${impl}" == "sh" ]]; then
    echo "=== sh: clean file and no parser ==="
    hook_path="${parser_free}"
    status="$(run_hook "${out_file}" "${err_file}")"
    hook_path="${PATH}"
    if [[ "${status}" -ne 0 ]]; then
        echo "FAIL: no-parser clean file expected exit 0, got ${status}" >&2
        cat "${out_file}" >&2
        cat "${err_file}" >&2
        exit 1
    fi
    "${py}" - <<'PY'
import json
import pathlib
import sys

scan = json.loads(pathlib.Path(".scanning/last-scan.json").read_text(encoding="utf-8"))
if scan["summary"]["total_findings"] != 0 or scan["findings"]:
    sys.stderr.write("FAIL: no-parser clean file stored findings\n")
    sys.exit(1)
print("PASS: no-parser clean file")
PY
fi

echo "=== ${impl}: nothing staged ==="
git -c "core.hooksPath=${empty_hooks}" add sample.txt
git -c "core.hooksPath=${empty_hooks}" commit -q -m "clean"
status="$(run_hook "${out_file}" "${err_file}")"
if [[ "${status}" -ne 0 ]]; then
    echo "FAIL: empty index expected exit 0, got ${status}" >&2
    exit 1
fi
if ! grep -q "No files staged" "${out_file}" "${err_file}"; then
    echo "FAIL: empty index did not say no files staged" >&2
    cat "${out_file}" >&2
    cat "${err_file}" >&2
    exit 1
fi
echo "PASS: empty index"

rm -f "${out_file}" "${err_file}"
echo "PASS: gitleaks hook (${impl})"
