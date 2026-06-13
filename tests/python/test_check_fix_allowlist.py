"""Fix-loop path-gate tests (the security-critical gate).

Asserts that the autonomous fix-loop allowlist gate:
  * passes files inside fix_loop.allowlist_paths,
  * rejects a patch touching .github/ (-> needs-human-review),
  * fails CLOSED on a security-sensitive substring even inside an allowlisted dir,
  * rejects paths outside the allowlist,
  * rejects the whole set if any single file is bad.
"""
import subprocess
import sys
from pathlib import Path

import check_fix_allowlist as gate  # noqa: E402 (pre-imported in conftest)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG = REPO_ROOT / "scan-config.yaml"

# Mirror scan-config.yaml fix_loop defaults so the unit tests are config-free.
ALLOW = ["src/", "tests/", "app/", "lib/"]
GATED = ["auth", "payment", "crypto", "security", "identity", "secret", "credential",
         ".github/", ".claude/", "hooks", "lefthook.yml", "scan-and-fix.ps1", "scripts/", ".env", "license"]


def test_allowlisted_path_passes():
    ok, reason = gate.check(["src/app.cs"], ALLOW, GATED)
    assert ok, reason


def test_github_workflow_is_rejected():
    ok, reason = gate.check([".github/workflows/ci.yml"], ALLOW, GATED)
    assert not ok
    assert ".github" in reason


def test_sensitive_substring_inside_allowlist_fails_closed():
    # Inside an allowlisted dir but contains 'auth' -> gated.
    ok, reason = gate.check(["src/AuthService.cs"], ALLOW, GATED)
    assert not ok
    assert "gated" in reason.lower()


def test_outside_allowlist_is_rejected():
    ok, reason = gate.check(["docs/readme.md"], ALLOW, GATED)
    assert not ok
    assert "allowlist" in reason.lower()


def test_one_bad_file_rejects_the_whole_set():
    ok, reason = gate.check(["src/ok.cs", ".claude/settings.json"], ALLOW, GATED)
    assert not ok


def test_leading_dot_slash_is_normalised():
    ok, _ = gate.check(["./src/app.cs"], ALLOW, GATED)
    assert ok


def test_cli_against_real_config_rejects_github():
    """End-to-end CLI run against the repo's actual scan-config.yaml."""
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check-fix-allowlist.py"),
         "--config", str(CONFIG), ".github/workflows/x.yml"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 1
    assert "GATED" in proc.stdout


def test_cli_against_real_config_allows_src():
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check-fix-allowlist.py"),
         "--config", str(CONFIG), "src/app.cs"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0
    assert "OK" in proc.stdout
