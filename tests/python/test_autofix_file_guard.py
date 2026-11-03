"""Exercise the fix-loop's installed tool guard and pre-publication secret gate."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/autonomous-fix.yml"


def analyze():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["analyze"]["steps"]


def step(name):
    return next(s for s in analyze() if name in s.get("name", ""))


@pytest.fixture
def guard(tmp_path):
    source = step("Write the fix tool guard")["run"]
    script = tmp_path / "install-guard.sh"
    script.write_text(source, encoding="utf-8", newline="\n")
    install = subprocess.run(
        [shutil.which("bash"), bash_path(script)], cwd=tmp_path,
        env={**os.environ, "RUNNER_TEMP": bash_path(tmp_path)},
        text=True, capture_output=True,
    )
    assert install.returncode == 0, install.stderr
    path = tmp_path / "fix-tool-guard.js"
    assert path.is_file(), "the workflow must install the guard at the hook's path"
    ws = tmp_path / "checkout"
    ws.mkdir()
    (ws / ".git").mkdir()
    (ws / "src").mkdir()
    (ws / "src/code.py").write_text("pass\n", encoding="utf-8")

    def call(tool, inputs):
        proc = subprocess.run(
            ["node", str(path), "12", "owner/repo", str(ws)],
            input=json.dumps({"tool_name": tool, "tool_input": inputs}),
            text=True, capture_output=True, cwd=ws,
        )
        assert proc.returncode in (0, 2), proc.stderr
        return proc.returncode

    return call, ws


@pytest.mark.parametrize("tool,key", [("Read", "file_path"), ("Edit", "file_path"),
                                      ("Write", "file_path"), ("NotebookEdit", "notebook_path")])
@pytest.mark.parametrize("target", ["/proc/self/environ", "~/.config/settings", "../outside",
                                    ".git/config", "src/../.git/config", "src/.git/config", ""])
def test_file_tools_refuse_runner_and_git_paths(guard, tool, key, target):
    call, _ = guard
    assert call(tool, {key: target}) == 2


def test_file_tools_allow_checkout_and_refuse_links_and_extra_paths(guard, tmp_path):
    call, ws = guard
    assert call("Read", {"file_path": "src/code.py"}) == 0
    assert call("Edit", {"file_path": str(ws / "src/code.py")}) == 0
    assert call("Write", {"file_path": "src/new.py"}) == 0
    assert call("Edit", {"file_path": "src/code.py", "other_path": str(tmp_path)}) == 2
    assert call("Read", {}) == 2
    assert call("Write", {}) == 2
    assert call("NewTool", {}) == 2
    try:
        (ws / "link").symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is not available")
    assert call("Read", {"file_path": "link/outside"}) == 2
    assert call("Write", {"file_path": "link/new"}) == 2


@pytest.mark.parametrize("command", [
    "gh pr diff 12 --jq env", "gh pr view 12 --template '{{.}}'",
    "gh pr view 12 -q env", "gh pr view 12 -t '{{.}}'",
    "gh pr diff 13", "gh pr diff 12; printenv", "gh pr diff 12\nprintenv",
    "gh api repos/owner/repo/pulls/12/comments --jq env", "cat /proc/self/environ",
])
def test_shell_tools_reject_unapproved_commands(guard, command):
    call, _ = guard
    for tool in ("Bash", "Monitor", "PowerShell"):
        assert call(tool, {"command": command}) == 2


def test_shell_tools_allow_the_prompt_commands(guard):
    call, _ = guard
    for command in ("gh pr diff 12", "gh pr view 12",
                    "gh api repos/owner/repo/pulls/12/comments",
                    "gh api repos/owner/repo/issues/12/comments"):
        assert call("Bash", {"command": command}) == 0


@pytest.mark.parametrize("tool,inputs", [
    ("Grep", {"path": "../", "pattern": "credential"}),
    ("Grep", {"glob": "**/*", "pattern": "credential"}),
    ("Glob", {"pattern": "{src,../outside}/*"}),
    ("Glob", {"pattern": ".git/*"}),
    ("LS", {"path": ".git"}),
])
def test_search_tools_share_the_review_path_boundary(guard, tool, inputs):
    call, _ = guard
    assert call(tool, inputs) == 2


def test_guard_is_installed_for_every_tool_before_the_agent():
    steps = analyze()
    agent = step("Run Claude Code")
    settings = json.loads(agent["with"]["settings"])
    assert not settings.get("disableAllHooks")
    hook = settings["hooks"]["PreToolUse"][0]
    assert hook["matcher"] == "*"
    command = hook["hooks"][0]
    assert command["timeout"] == 30
    assert command["command"] == (
        "node '${{ runner.temp }}/fix-tool-guard.js' ${{ steps.ctx.outputs.pr }} "
        "${{ github.repository }} '${{ github.workspace }}' || exit 2"
    )
    assert steps.index(step("Write the fix tool guard")) < steps.index(agent)
    cleanup = step("Remove the agent config files")
    assert steps.index(cleanup) < steps.index(agent)
    assert "-type l" in cleanup["run"] and "-name .claude" in cleanup["run"]
    assert "--setting-sources user" in agent["with"]["claude_args"]


def test_patch_scan_is_a_required_gate_before_upload():
    steps = analyze()
    scan = step("Secret-scan the patch before publication")
    upload = step("Upload vetted patch")
    assert steps.index(step("Capture fix")) < steps.index(scan) < steps.index(upload)
    assert scan["id"] == "patch_secrets"
    assert "continue-on-error" not in scan
    assert "always()" not in upload["if"]
    assert "steps.patch_secrets.outcome == 'success'" in upload["if"]
    assert scan["working-directory"] == "${{ runner.temp }}"
    assert "--exit-code 1" in scan["run"]


def bash_path(path):
    value = str(path).replace("\\", "/")
    return "/" + value[0].lower() + value[2:] if re.match(r"^[A-Za-z]:", value) else value


@pytest.mark.parametrize("status", [0, 1, 2, 127])
def test_patch_scan_fails_closed_on_scanner_failure(tmp_path, status):
    scan = step("Secret-scan the patch before publication")
    binary_dir = tmp_path / "autofix-trivy"
    binary_dir.mkdir()
    shim = binary_dir / "trivy"
    shim.write_text(f"#!/bin/sh\nexit {status}\n", encoding="utf-8")
    shim.chmod(0o755)
    (tmp_path / "autofix.patch").write_text("safe patch\n", encoding="utf-8")
    result = subprocess.run([shutil.which("bash"), "-c", scan["run"]], cwd=tmp_path,
                            env={**os.environ, "RUNNER_TEMP": bash_path(tmp_path),
                                 "GITHUB_WORKSPACE": bash_path(tmp_path)}, capture_output=True, text=True)
    assert result.returncode != 0


def test_patch_scan_detects_a_planted_secret_with_checkout_policy_ignored(tmp_path):
    trivy = shutil.which("trivy")
    if not trivy:
        pytest.skip("Trivy is required for the scanner integration test")
    scan = step("Secret-scan the patch before publication")
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    # Build a synthetic detector fixture, never a usable credential.
    token = "AKIA" + "Q7V3N9R2M8D5L6CW"
    (checkout / "autofix.patch").write_text("+access_key = '" + token + "'\n", encoding="utf-8")
    (checkout / "trivy.yaml").write_text("secret:\n  config: disabled.yaml\n", encoding="utf-8")
    (checkout / "disabled.yaml").write_text("disable-allow-rules: false\ndisable-rules: [aws-access-key-id]\n", encoding="utf-8")
    (checkout / ".trivyignore").write_text("aws-access-key-id\n", encoding="utf-8")
    binary_dir = tmp_path / "autofix-trivy"
    binary_dir.mkdir()
    shim = binary_dir / "trivy"
    shim.write_text("#!/bin/sh\nexec '" + bash_path(trivy) + "' \"$@\"\n", encoding="utf-8")
    shim.chmod(0o755)
    result = subprocess.run([shutil.which("bash"), "-c", scan["run"]], cwd=tmp_path,
                            env={**os.environ, "RUNNER_TEMP": bash_path(tmp_path),
                                 "GITHUB_WORKSPACE": bash_path(checkout)}, capture_output=True, text=True)
    assert result.returncode != 0
    assert token not in result.stdout + result.stderr
    (checkout / "autofix.patch").write_text("+answer = 42\n", encoding="utf-8")
    clean = subprocess.run([shutil.which("bash"), "-c", scan["run"]], cwd=tmp_path,
                           env={**os.environ, "RUNNER_TEMP": bash_path(tmp_path),
                                "GITHUB_WORKSPACE": bash_path(checkout)}, capture_output=True, text=True)
    assert clean.returncode == 0, clean.stderr


def test_only_the_supported_terraform_scan_workflows_remain():
    workflows = ROOT / ".github/workflows"
    assert not (workflows / "terraform-security-scan.yml").exists()
    assert (workflows / "reusable-scan.yml").is_file()
    assert (workflows / "reusable-scan-self-test.yml").is_file()


def test_agent_cleanup_does_not_become_part_of_the_patch(tmp_path):
    ws = tmp_path / "checkout"
    ws.mkdir()
    config = ws / "src/.claude"
    config.mkdir(parents=True)
    (config / "settings.json").write_text("{}\n", encoding="utf-8")
    (ws / "src/.mcp.json").write_text("{}\n", encoding="utf-8")
    code = ws / "src/code.py"
    code.write_text("answer = 1\n", encoding="utf-8")
    env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
           "RUNNER_TEMP": bash_path(tmp_path), "GITHUB_WORKSPACE": bash_path(ws),
           "GITHUB_OUTPUT": bash_path(tmp_path / "outputs")}
    def git(*args):
        return subprocess.run(["git", "-c", "core.autocrlf=false", *args], cwd=ws,
                              env=env, check=True, capture_output=True, text=True).stdout
    git("init")
    git("add", ".")
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "base")
    env["HEAD_SHA"] = git("rev-parse", "HEAD").strip()
    cleanup = subprocess.run([shutil.which("bash"), "-c", step("Remove the agent config files")["run"]],
                             cwd=ws, env=env, capture_output=True, text=True)
    assert cleanup.returncode == 0, cleanup.stderr
    assert not config.exists()
    assert not (ws / "src/.mcp.json").exists()
    code.write_text("answer = 2\n", encoding="utf-8")
    capture = subprocess.run([shutil.which("bash"), "-c", step("Capture fix")["run"]],
                             cwd=ws, env=env, capture_output=True, text=True)
    assert capture.returncode == 0, capture.stderr
    assert git("diff", "--cached", "--name-only").splitlines() == ["src/code.py"]
