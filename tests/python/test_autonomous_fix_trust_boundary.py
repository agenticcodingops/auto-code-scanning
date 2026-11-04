"""Trust-boundary tests for the reusable agentic fix-loop (autonomous-fix.yml).

These assert the security properties of the workflow STRUCTURE (the loop's real
enforcement), so a future edit cannot silently reintroduce the privilege-escalation
path where a labelled PR sets a malicious fix_loop.build_verify_cmd at its head and
runs it while the push token is on disk.

Properties asserted:
  * fix_loop config is read from the TRUSTED base ref (never the PR head).
  * build_verify_cmd executed by the verify job comes from the config job's output
    (base-sourced), NOT from a head-read value -> a PR cannot change what runs.
  * the apply checkout never writes the token to disk (persist-credentials: false,
    no `token:` input); only the final push step holds AUTOFIX_TOKEN.
  * the allowlist gate (analyze + apply) reads the trusted base config artifact.
  * project code (the build command, the PR head's files) runs only in a job that
    holds no secret and hands nothing to the push job but its result; the push job
    commits the content-addressed tree that passed the gate and the secret scan.
  * the model credentials reach only the agent step, whose tools cannot run
    build, test or package commands, and whose start-up config comes from base.
  * the job that runs project code has no Actions cache access (cache-mode: none),
    so nothing it runs can save a cache entry that another job or workflow restores.
  * the fix-loop is never started by the shared github-actions[bot] identity.
"""
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WF = REPO_ROOT / ".github" / "workflows" / "autonomous-fix.yml"
CALLER = REPO_ROOT / "templates" / "fix-loop" / "autonomous-fix.yml"

SHARED_BOT = "github-actions[bot]"
MODEL_SECRETS = ("secrets.ANTHROPIC_API_KEY", "secrets.CLAUDE_CODE_OAUTH_TOKEN")


@pytest.fixture(scope="module")
def wf():
    return yaml.safe_load(WF.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def raw():
    return WF.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def caller():
    return yaml.safe_load(CALLER.read_text(encoding="utf-8"))


def test_caller_grants_exactly_the_reusable_jobs_permissions(wf, caller):
    """The caller is the permission ceiling, including inherited job defaults."""
    levels = {"none": 0, "read": 1, "write": 2}
    granted = caller["jobs"]["fix"]["permissions"]
    required = {}
    for job_id, job in wf["jobs"].items():
        permissions = job.get("permissions", wf.get("permissions", {}))
        for scope, access in permissions.items():
            assert levels[granted.get(scope, "none")] >= levels[access], (
                f"caller fix job does not cover {job_id}: {scope}: {access}"
            )
            if levels[access] > levels[required.get(scope, "none")]:
                required[scope] = access
    assert granted == required, "caller fix job must grant no extra permissions"


def _step(job, name_contains):
    for s in job["steps"]:
        if name_contains.lower() in s.get("name", "").lower():
            return s
    return None


def _require_step(job, name_contains):
    step = _step(job, name_contains)
    assert step is not None, f"no step named like {name_contains!r}"
    return step


def _dump(obj):
    return yaml.safe_dump(obj, sort_keys=False)


def _bash():
    """Return a POSIX bash (Git Bash on Windows, never the WSL launcher), or None."""
    if os.name == "nt":
        git = shutil.which("git")
        if git:
            for rel in ("../bin/bash.exe", "../../bin/bash.exe", "../usr/bin/bash.exe"):
                cand = (Path(git).parent / rel).resolve()
                if cand.exists():
                    return str(cand)
        return None
    return shutil.which("bash")


def _posix(p):
    return Path(p).as_posix()


def _run_step(step, cwd, env, bash, expect_ok=True):
    """Run a workflow step's `run:` script the way the runner would (env + bash)."""
    full_env = os.environ.copy()
    for key in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE"):
        full_env.pop(key, None)
    full_env.update({k: str(v) for k, v in env.items()})
    proc = subprocess.run(
        [bash, "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", step["run"]],
        cwd=str(cwd), env=full_env, capture_output=True, text=True,
    )
    if expect_ok:
        assert proc.returncode == 0, f"{step['name']} failed:\n{proc.stdout}\n{proc.stderr}"
    return proc


def _outputs(path):
    out = {}
    if Path(path).exists():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                out[k] = v
    return out


def _git(*args, cwd, env=None):
    full_env = os.environ.copy()
    full_env.update({
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    })
    if env:
        full_env.update(env)
    return subprocess.run(
        ["git", "-c", "core.autocrlf=false", *args], cwd=str(cwd), env=full_env,
        check=True, capture_output=True, text=True,
    ).stdout


@pytest.mark.skipif(_bash() is None, reason="needs compatible Bash")
@pytest.mark.parametrize("binary", [True, False])
def test_capture_publishes_text_patches_only(wf, tmp_path, binary):
    """A binary hunk would hide content from the patch secret scan, so capture refuses it."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-q", cwd=repo)
    (repo / "notes.txt").write_text("before\n", encoding="utf-8")
    _git("add", ".", cwd=repo)
    _git("commit", "-qm", "base", cwd=repo)
    head = _git("rev-parse", "HEAD", cwd=repo).strip()
    if binary:
        # The pull request can mark any file as binary for diff purposes.
        (repo / ".gitattributes").write_text("notes.txt -diff\n", encoding="utf-8")
    (repo / "notes.txt").write_text("after\n", encoding="utf-8")
    script = _require_step(wf["jobs"]["analyze"], "Capture fix as a patch")["run"]
    out = tmp_path / "github-output"
    env = os.environ.copy()
    env.update({"HEAD_SHA": head, "RUNNER_TEMP": _posix(tmp_path), "GITHUB_OUTPUT": _posix(out)})
    bash = _bash()
    result = subprocess.run([bash, "-c", script], cwd=repo, env=env, capture_output=True, text=True)
    patch = repo / "autofix.patch"
    if binary:
        assert result.returncode != 0, result.stdout + result.stderr
        assert "binary files" in result.stdout + result.stderr
        assert not patch.exists() or patch.stat().st_size == 0
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        text = patch.read_text(encoding="utf-8")
        assert "+after" in text and "GIT binary patch" not in text
        assert "has_changes=true" in out.read_text(encoding="utf-8")


@pytest.mark.skipif(os.name != "nt" or _bash() is None, reason="needs Windows with compatible Bash")
def test_capture_ignores_an_incompatible_bash_on_path(wf, tmp_path, monkeypatch):
    original = shutil.which
    monkeypatch.setattr(shutil, "which", lambda name: "unusable-wsl-launcher" if name == "bash" else original(name))
    test_capture_publishes_text_patches_only(wf, tmp_path, False)


@pytest.mark.skipif(_bash() is None, reason="needs compatible Bash")
@pytest.mark.parametrize("control", [1, 6, 11, 14, 26, 28, 31, 127])
def test_capture_rejects_unscannable_content(wf, tmp_path, control):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-q", cwd=repo)
    (repo / "notes.txt").write_bytes(b"before\n")
    _git("add", ".", cwd=repo)
    _git("commit", "-qm", "base", cwd=repo)
    head = _git("rev-parse", "HEAD", cwd=repo).strip()
    token = "AKIA" + "Q7V3N9R2M8D5L6CW"
    (repo / "notes.txt").write_bytes(bytes([control]) + ("access_key = '" + token + "'\n").encode())
    proc = _run_step(_require_step(wf["jobs"]["analyze"], "Capture fix as a patch"), repo,
                     {"HEAD_SHA": head, "RUNNER_TEMP": _posix(tmp_path),
                      "GITHUB_OUTPUT": _posix(tmp_path / "output")}, _bash(), expect_ok=False)
    assert proc.returncode != 0
    assert "unsupported content" in proc.stdout + proc.stderr
    assert token not in proc.stdout + proc.stderr
    assert not (repo / "autofix.patch").exists()
    assert not _outputs(tmp_path / "output").get("has_changes")


# ---------------------------------------------------------------------------
# Base-sourced config and token handling
# ---------------------------------------------------------------------------

def test_config_read_from_base_ref(wf):
    checkout = next(s for s in wf["jobs"]["config"]["steps"] if "checkout" in str(s.get("uses", "")))
    ref = checkout["with"]["ref"]
    assert "pull_request.base.sha" in ref, "config job must check out the BASE ref, not PR head"
    assert checkout["with"]["persist-credentials"] is False


def test_build_verify_cmd_is_base_sourced(wf):
    bv = _require_step(wf["jobs"]["verify"], "build verify")
    cmd_ref = bv["env"]["BUILD_VERIFY_CMD"]
    # Must come from the config job (which read base), NOT inputs/head config.
    assert "needs.config.outputs.build_verify_cmd" in cmd_ref


def test_apply_checkout_has_no_token_on_disk(wf):
    checkout = wf["jobs"]["apply-and-push"]["steps"][0]
    assert "checkout" in checkout["uses"]
    assert checkout["with"].get("persist-credentials") is False
    assert "token" not in checkout["with"], "apply checkout must NOT persist AUTOFIX_TOKEN to .git/config"


def test_only_push_step_holds_the_token(wf):
    offenders = []
    for s in wf["jobs"]["apply-and-push"]["steps"]:
        env = s.get("env", {}) or {}
        if any("AUTOFIX_TOKEN" in str(v) or k == "AUTOFIX_TOKEN" for k, v in env.items()):
            offenders.append(s.get("name", "?"))
    assert offenders == [] or all("push" in o.lower() for o in offenders), \
        f"AUTOFIX_TOKEN must only be present in the push step, found in: {offenders}"
    push = _step(wf["jobs"]["apply-and-push"], "Push")
    assert push is not None and "AUTOFIX_TOKEN" in (push.get("env", {}) or {})


def test_push_injects_token_into_url_not_config(raw):
    assert "x-access-token:${AUTOFIX_TOKEN}@github.com" in raw, \
        "push must inject the token into the URL, never via persisted git config"


def test_gate_uses_trusted_base_config(wf, raw):
    # Both analyze and apply gates must read the trusted base config artifact.
    assert _require_step(wf["jobs"]["analyze"], "Safety gate")["env"]["TRUSTED_CONFIG"] == (
        "${{ runner.temp }}/autofix-trusted-config/trusted-scan-config.yaml"
    )
    assert _require_step(wf["jobs"]["apply-and-push"], "Re-enforce allowlist gate")["env"]["TRUSTED_CONFIG"] == (
        ".trusted/trusted-scan-config.yaml"
    )
    assert "name: trusted-config" in raw
    # The gate must NOT read inputs.config_path (the PR-head file) anymore.
    for job in ("analyze", "apply-and-push"):
        gate = _step(wf["jobs"][job], "gate")
        assert gate is not None
        assert "inputs.config_path" not in yaml.safe_dump(gate)


def test_pyyaml_is_ensured_where_yaml_is_parsed(raw):
    # config job + both gate jobs install pyyaml so a missing dep can't silently break it.
    assert raw.count("pip install --quiet --disable-pip-version-check PyYAML==6.0.3") >= 3


# ---------------------------------------------------------------------------
# Push integrity: what is pushed is exactly what passed the gate and the scan
# ---------------------------------------------------------------------------

def _jobs_running_build_verify(wf):
    return [
        name for name, job in wf["jobs"].items()
        if any("build_verify_cmd" in _dump(s.get("env", {}) or {}) and "run" in s for s in job.get("steps", []))
    ]


def test_build_verify_runs_only_in_a_job_without_credentials(wf):
    assert _jobs_running_build_verify(wf) == ["verify"], \
        "build_verify_cmd must run in its own job, never in the job that pushes"
    job = wf["jobs"]["verify"]
    assert "secrets." not in _dump(job), "the build job must hold no secret"
    assert not job.get("outputs"), "the build job must hand the push job nothing but its result"
    assert not any("upload-artifact" in str(s.get("uses", "")) for s in job["steps"]), \
        "the build job must not upload anything the push job could pick up"
    assert job.get("permissions") == {"contents": "read"}
    for s in job["steps"]:
        if "checkout" in str(s.get("uses", "")):
            assert s["with"].get("persist-credentials") is False


def test_push_job_runs_no_project_code(wf):
    job = wf["jobs"]["apply-and-push"]
    text = _dump(job)
    assert "build_verify_cmd" not in text, "the push job must not run the project's build"
    assert "verify" in job["needs"], "the push job must wait for the build job's result"
    head_checkout = job["steps"][0]
    path = head_checkout["with"].get("path", "")
    assert path not in ("", ".", "./"), \
        "the PR head must be checked out outside the working directory that tools read config from"
    for s in job["steps"]:
        assert "working-directory" not in s, "steps must not run inside the PR checkout"
        run = s.get("run", "")
        assert "git apply --index" not in run and "git commit " not in run, \
            "the push job must not build the commit from the mutable index"


def test_push_job_checks_artifact_digests(wf):
    job = wf["jobs"]["apply-and-push"]
    step = _require_step(job, "digest")
    env = _dump(step.get("env", {}))
    assert "needs.analyze.outputs.patch_sha256" in env
    assert "needs.config.outputs.config_sha256" in env
    names = [s.get("name", "") for s in job["steps"]]
    assert names.index(step["name"]) < names.index(_require_step(job, "Build the vetted tree")["name"])
    verify_digest = _require_step(wf["jobs"]["verify"], "digest")
    assert "needs.analyze.outputs.patch_sha256" in _dump(verify_digest.get("env", {}))


def test_push_disables_hooks_and_pushes_the_explicit_commit(wf):
    push = _require_step(wf["jobs"]["apply-and-push"], "Push")
    run = push["run"]
    assert "core.hooksPath=/dev/null" in run
    assert re.search(r'"\$\{COMMIT\}:refs/heads/\$\{HEAD_REF\}"', run), \
        "push the vetted commit by SHA, never whatever HEAD points at"
    assert "HEAD:" not in run


@pytest.fixture
def push_job_sandbox(tmp_path):
    """A PR head checkout at ws/pr-head, a remote holding its branch, and a vetted patch."""
    bash = _bash()
    if not bash:
        pytest.skip("bash is not available")
    ws = tmp_path / "ws"
    repo = ws / "pr-head"
    repo.mkdir(parents=True)
    _git("init", "-q", cwd=repo)
    (repo / "src").mkdir()
    (repo / "src" / "app.txt").write_bytes(b"hello\n")
    (repo / "README.md").write_bytes(b"readme\n")
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "base", cwd=repo)
    head_sha = _git("rev-parse", "HEAD", cwd=repo).strip()

    (repo / "src" / "app.txt").write_bytes(b"hello fixed\n")
    patch = tmp_path / "artifact" / "autofix.patch"
    patch.parent.mkdir()
    patch.write_bytes(_git("diff", "--binary", cwd=repo).encode())
    _git("checkout", "--", ".", cwd=repo)

    remote_root = tmp_path / "remote"
    bare = remote_root / "o" / "r.git"
    bare.mkdir(parents=True)
    _git("init", "-q", "--bare", cwd=bare)
    _git("push", "-q", str(bare), f"{head_sha}:refs/heads/feature", cwd=repo)

    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    return {
        "bash": bash, "ws": ws, "repo": repo, "head_sha": head_sha, "patch": patch,
        "bare": bare, "remote_root": remote_root, "runner_temp": runner_temp, "tmp": tmp_path,
    }


@pytest.mark.parametrize("control", [1, 11, 127])
@pytest.mark.parametrize("offset", [0, 400])
def test_export_rejects_unscannable_tree_content(wf, push_job_sandbox, control, offset):
    sb = push_job_sandbox
    token = "AKIA" + "Q7V3N9R2M8D5L6CW"
    target = sb["repo"] / "src/app.txt"
    target.write_bytes(b"x" * offset + bytes([control]) + ("access_key = '" + token + "'\n").encode())
    _git("add", ".", cwd=sb["repo"])
    tree = _git("write-tree", cwd=sb["repo"]).strip()
    target.write_bytes(b"benign worktree\n")
    env_file = sb["tmp"] / "export-env"
    proc = _run_step(_require_step(wf["jobs"]["apply-and-push"], "Export the vetted files"), sb["ws"],
                     {"RUNNER_TEMP": _posix(sb["runner_temp"]), "HEAD_SHA": sb["head_sha"],
                      "PATCH_TREE": tree, "GITHUB_ENV": _posix(env_file)}, sb["bash"], expect_ok=False)
    assert proc.returncode != 0
    assert "unsupported content" in proc.stdout + proc.stderr
    assert token not in proc.stdout + proc.stderr
    assert "SCAN_TMP" not in _outputs(env_file)


@pytest.mark.parametrize("name", ["diagram.svg", "package-lock.json", "node_modules/code.js"])
def test_export_uses_scan_names_without_default_exclusions(wf, push_job_sandbox, name):
    sb = push_job_sandbox
    target = sb["repo"] / name
    target.parent.mkdir(parents=True, exist_ok=True)
    content = b"synthetic content for scanning\n"
    target.write_bytes(content)
    _git("add", ".", cwd=sb["repo"])
    tree = _git("write-tree", cwd=sb["repo"]).strip()
    env_file = sb["tmp"] / "export-env"
    _run_step(_require_step(wf["jobs"]["apply-and-push"], "Export the vetted files"), sb["ws"],
              {"RUNNER_TEMP": _posix(sb["runner_temp"]), "HEAD_SHA": sb["head_sha"],
               "PATCH_TREE": tree, "GITHUB_ENV": _posix(env_file)}, sb["bash"])
    scan_dir = Path(_outputs(env_file)["SCAN_TMP"])
    files = sorted(p.relative_to(scan_dir).as_posix() for p in scan_dir.rglob("*") if p.is_file())
    assert files == ["content/1.txt", "original/" + name]
    assert (scan_dir / "content/1.txt").read_bytes() == content
    assert (scan_dir / "original" / name).read_bytes() == content


def test_export_preserves_path_sensitive_scan_inputs(wf, push_job_sandbox):
    sb = push_job_sandbox
    target = sb["repo"] / "settings.xml"
    content = b"<settings>scan with the original filename</settings>\n"
    target.write_bytes(content)
    _git("add", ".", cwd=sb["repo"])
    tree = _git("write-tree", cwd=sb["repo"]).strip()
    env_file = sb["tmp"] / "export-env"
    _run_step(_require_step(wf["jobs"]["apply-and-push"], "Export the vetted files"), sb["ws"],
              {"RUNNER_TEMP": _posix(sb["runner_temp"]), "HEAD_SHA": sb["head_sha"],
               "PATCH_TREE": tree, "GITHUB_ENV": _posix(env_file)}, sb["bash"])
    scan_dir = Path(_outputs(env_file)["SCAN_TMP"])
    assert (scan_dir / "original/settings.xml").read_bytes() == content
    assert (scan_dir / "content/1.txt").read_bytes() == content


def _tamper(repo, marker):
    """What hostile project code would do to the job state if it ever ran there."""
    hook = f"#!/bin/sh\necho ran > '{_posix(marker)}'\n"
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / ".github" / "workflows" / "evil.yml").write_bytes(b"name: evil\n")
    (repo / "src" / "app.txt").write_bytes(b"tampered\n")
    _git("add", "-A", cwd=repo)
    for hooks_dir in (repo / ".git" / "hooks", repo / "evilhooks"):
        hooks_dir.mkdir(exist_ok=True)
        for name in ("pre-push", "pre-commit", "reference-transaction"):
            (hooks_dir / name).write_bytes(hook.encode())
            # A hook must be executable to run; owner-only, in a temp directory.
            (hooks_dir / name).chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    _git("config", "core.hooksPath", "evilhooks", cwd=repo)


def test_pushed_commit_is_exactly_the_scanned_tree(wf, push_job_sandbox):
    sb = push_job_sandbox
    job = wf["jobs"]["apply-and-push"]
    rt = _posix(sb["runner_temp"])
    base_env = {"RUNNER_TEMP": rt, "HEAD_SHA": sb["head_sha"]}

    out = sb["tmp"] / "out-tree"
    _run_step(_require_step(job, "Build the vetted tree"), sb["ws"],
              {**base_env, "GITHUB_OUTPUT": _posix(out), "PATCH_FILE": _posix(sb["patch"])}, sb["bash"])
    patch_tree = _outputs(out)["tree"]

    marker = sb["tmp"] / "hook-ran"
    _tamper(sb["repo"], marker)

    gh_env = sb["tmp"] / "gh-env"
    _run_step(_require_step(job, "Export the vetted files"), sb["ws"],
              {**base_env, "GITHUB_ENV": _posix(gh_env), "PATCH_TREE": patch_tree}, sb["bash"])
    scan_dir = Path(_outputs(gh_env)["SCAN_TMP"])
    exported = sorted(p.relative_to(scan_dir).as_posix() for p in scan_dir.rglob("*") if p.is_file())
    assert exported == ["content/1.txt", "original/src/app.txt"], "scan only the vetted bytes in both layouts"
    assert (scan_dir / "content/1.txt").read_bytes() == b"hello fixed\n"
    assert (scan_dir / "original/src/app.txt").read_bytes() == b"hello fixed\n"

    out = sb["tmp"] / "out-commit"
    _run_step(_require_step(job, "Commit the vetted tree"), sb["ws"],
              {**base_env, "GITHUB_OUTPUT": _posix(out), "PATCH_TREE": patch_tree,
               "ATTEMPTS": "0", "PR": "7"}, sb["bash"])
    commit_out = _outputs(out)

    remote_url = "file://" + ("" if _posix(sb["remote_root"]).startswith("/") else "/") + _posix(sb["remote_root"]) + "/"
    _run_step(_require_step(job, "Push"), sb["ws"], {
        **base_env, "AUTOFIX_TOKEN": "tok", "REPO": "o/r", "HEAD_REF": "feature",
        "COMMIT": commit_out["commit"], "FINAL_TREE": commit_out["tree"],
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": f"url.{remote_url}.insteadOf",
        "GIT_CONFIG_VALUE_0": "https://x-access-token:tok@github.com/",
    }, sb["bash"])

    bare = sb["bare"]
    files = _git("ls-tree", "-r", "--name-only", "feature", cwd=bare).split()
    assert sorted(files) == [".fix-attempts", "README.md", "src/app.txt"], \
        "nothing staged after the gate may reach the pushed commit"
    assert _git("show", "feature:src/app.txt", cwd=bare) == "hello fixed\n"
    assert _git("show", "feature:.fix-attempts", cwd=bare) == "1\n"
    assert _git("rev-parse", "feature^", cwd=bare).strip() == sb["head_sha"]
    assert not marker.exists(), "no repository hook may run during commit or push"


def test_push_refuses_a_commit_that_is_not_the_vetted_one(wf, push_job_sandbox):
    sb = push_job_sandbox
    job = wf["jobs"]["apply-and-push"]
    rt = _posix(sb["runner_temp"])
    out = sb["tmp"] / "out-tree"
    _run_step(_require_step(job, "Build the vetted tree"), sb["ws"],
              {"RUNNER_TEMP": rt, "HEAD_SHA": sb["head_sha"], "GITHUB_OUTPUT": _posix(out),
               "PATCH_FILE": _posix(sb["patch"])}, sb["bash"])
    head_tree = _git("rev-parse", "HEAD^{tree}", cwd=sb["repo"]).strip()
    proc = _run_step(_require_step(job, "Push"), sb["ws"], {
        "RUNNER_TEMP": rt, "HEAD_SHA": sb["head_sha"], "AUTOFIX_TOKEN": "tok", "REPO": "o/r",
        "HEAD_REF": "feature", "COMMIT": sb["head_sha"], "FINAL_TREE": _outputs(out)["tree"],
    }, sb["bash"], expect_ok=False)
    assert proc.returncode != 0
    assert head_tree != _outputs(out)["tree"]


# ---------------------------------------------------------------------------
# Model credentials never meet code from the pull request
# ---------------------------------------------------------------------------

def _steps_with_model_secrets(wf):
    found = []
    for job_name, job in wf["jobs"].items():
        for s in job.get("steps", []):
            if any(sec in _dump(s) for sec in MODEL_SECRETS):
                found.append((job_name, s.get("name", "?")))
    return found


def _claude_args(step):
    args = step["with"]["claude_args"]
    allowed = re.search(r'--allowedTools "([^"]*)"', args).group(1)
    disallowed = re.search(r'--disallowedTools "([^"]*)"', args).group(1)
    split = lambda s: [t.strip() for t in re.split(r",(?![^()]*\))", s) if t.strip()]
    return split(allowed), split(disallowed)


def test_model_credentials_reach_only_the_agent_step(wf):
    found = _steps_with_model_secrets(wf)
    assert len(found) == 1 and found[0][0] == "analyze", found
    agent = _require_step(wf["jobs"]["analyze"], "Run Claude Code")
    assert found[0][1] == agent["name"]


def test_agent_cannot_run_build_test_or_package_commands(wf):
    agent = _require_step(wf["jobs"]["analyze"], "Run Claude Code")
    allowed, disallowed = _claude_args(agent)
    for tool in allowed:
        if tool.startswith("Bash("):
            assert tool.startswith("Bash(gh pr view") or tool.startswith("Bash(gh pr diff") \
                or tool.startswith("Bash(gh api repos/"), \
                f"{tool} would run project code next to the model credentials"
        else:
            assert tool in ("Read", "Edit", "Glob", "Grep"), f"unexpected tool {tool}"
    for runner in ("npm", "npx", "node", "dotnet", "semgrep", "make", "python", "python3", "bash", "sh"):
        assert f"Bash({runner}:*)" in disallowed, f"{runner} must be explicitly denied"


def test_agent_loads_no_repository_config(wf):
    """Project settings, hooks and MCP servers in the checkout (base copy or PR copy)
    can run the PR's files, so the agent session must load none of them."""
    job = wf["jobs"]["analyze"]
    names = [s.get("name", "") for s in job["steps"]]
    remove = _require_step(job, "agent config files")
    agent = _require_step(job, "Run Claude Code")
    assert names.index(remove["name"]) < names.index(agent["name"])
    assert "git checkout" not in remove["run"], "remove the files; do not restore another copy"
    for path in (".claude", ".mcp.json", "CLAUDE.md"):
        assert path in remove["run"]
        assert path in _require_step(job, "Capture fix")["run"], f"{path} must stay out of the patch"
    args = agent["with"]["claude_args"]
    assert "--setting-sources user" in args, "load user-level settings only, never the project's"
    assert "--strict-mcp-config" in args, "start only the action's own MCP servers"
    assert '"PreToolUse"' in agent["with"]["settings"]
    assert "disableAllHooks" not in agent["with"]["settings"]


def _effective_cache_mode(wf, job_name):
    job = wf["jobs"][job_name]
    return job.get("cache-mode", wf.get("cache-mode"))


def test_project_code_job_cannot_write_the_actions_cache(wf):
    """The verify job runs the PR's code. On a manual dispatch its cache scope is the
    branch the run is on, which other workflows restore from, so the job's cache token
    must allow no save at all. cache-mode is enforced by the cache service with scoped
    tokens, not by the job's steps, so the build cannot get around it."""
    jobs = _jobs_running_build_verify(wf)
    assert jobs == ["verify"], jobs
    verify = wf["jobs"]["verify"]
    assert verify.get("cache-mode") == "none", \
        "the job that runs project code must declare cache-mode: none at job level"
    assert wf.get("cache-mode") == "none", \
        "no job here uses the cache, so the workflow grants none by default"
    for name in wf["jobs"]:
        mode = _effective_cache_mode(wf, name)
        assert mode == "none", f"{name}: cache-mode {mode!r}; no job in this workflow needs the cache"


def test_cache_mode_is_a_job_key_not_a_step_or_env_setting(wf, raw):
    """A step-level key or an env var would not reach the cache token; only the
    workflow and job keys do, so the declaration must sit there."""
    assert re.search(r"(?m)^cache-mode: none\s*(#.*)?$", raw), "workflow-level cache-mode: none"
    assert re.search(r"(?m)^    cache-mode: none\s*(#.*)?$", raw), "job-level cache-mode: none"
    for name, job in wf["jobs"].items():
        for s in job.get("steps", []):
            assert "cache-mode" not in s, f"{name} / {s.get('name')}: cache-mode belongs on the job"
            assert "ACTIONS_CACHE_MODE" not in _dump(s.get("env", {}) or {}), \
                f"{name} / {s.get('name')}: setting ACTIONS_CACHE_MODE in a step grants or removes nothing"


def test_credential_jobs_restore_nothing_from_the_actions_cache(wf, raw):
    """Pull-request code can write Actions cache entries outside this workflow (for
    example the PR's own CI runs), so no job that holds a credential may restore an
    executable or data from that cache."""
    assert "actions/cache" not in raw
    trivy = _require_step(wf["jobs"]["apply-and-push"], "Authoritative secret scan")
    assert str(trivy["with"].get("cache")).lower() == "false"
    analyze = wf["jobs"]["analyze"]
    bun = _require_step(analyze, "checksum-verified Bun")
    assert re.fullmatch(r"[0-9a-f]{64}", bun["env"]["BUN_SHA256"])
    assert "sha256sum -c" in bun["run"]
    agent = _require_step(analyze, "Run Claude Code")
    assert agent["with"].get("path_to_bun_executable") == "${{ steps.bun.outputs.path }}", \
        "the agent action must use the verified Bun, not one restored from the cache"
    names = [s.get("name", "") for s in analyze["steps"]]
    assert names.index(bun["name"]) < names.index(agent["name"])


def test_python_never_imports_from_the_checkout(wf):
    """`python3 -m` puts the working directory first on sys.path; -I keeps it off."""
    calls = []
    for job_name, job in wf["jobs"].items():
        for s in job.get("steps", []):
            for m in re.finditer(r"\bpython3?\b(?!\.)([^\n|;&]*)", s.get("run", "")):
                calls.append((job_name, s.get("name"), m.group(0)))
    assert calls, "expected python calls in the workflow"
    for job_name, name, call in calls:
        assert re.match(r'python3?"? -I\b', call), f"{job_name} / {name}: {call!r} must run isolated (-I)"


def test_pyyaml_lives_in_a_venv_outside_the_checkout(wf):
    """-I disables the user site, so pip needs a writable environment; and every
    interpreter that imports yaml must be the one it was installed into."""
    venv_python = '"${RUNNER_TEMP}/autofix-py/bin/python" -I'
    for job_name in ("config", "analyze", "apply-and-push"):
        job = wf["jobs"][job_name]
        install = _require_step(job, "Ensure PyYAML")["run"]
        assert 'python3 -I -m venv "${RUNNER_TEMP}/autofix-py"' in install
        assert f"{venv_python} -m pip install" in install
        for s in job["steps"]:
            run = s.get("run", "")
            if "check-fix-allowlist.py" in run or "import yaml" in run:
                assert venv_python in run, f"{job_name} / {s.get('name')} must use the venv Python"


# ---------------------------------------------------------------------------
# Trigger: specific apps, never the shared workflow identity
# ---------------------------------------------------------------------------

def test_caller_trusts_no_shared_workflow_identity(caller):
    cond = caller["jobs"]["fix"]["if"]
    for listed in re.findall(r"fromJSON\('(\[[^']*\])'\)", cond):
        assert SHARED_BOT not in listed, "github-actions[bot] is every workflow's identity, not one reviewer"
    dispatch = re.search(r"github\.event_name == 'workflow_dispatch'[^)]*\)", cond)
    assert dispatch, "the dispatch branch must be its own parenthesised clause"
    for who in ("github.actor", "github.triggering_actor"):
        assert f"{who} != '{SHARED_BOT}'" in dispatch.group(0), \
            "a dispatch sent with a workflow's GITHUB_TOKEN must not start the loop"


def test_caller_passes_only_the_declared_secrets(caller, wf):
    secrets = caller["jobs"]["fix"]["secrets"]
    assert isinstance(secrets, dict), "never `secrets: inherit`: it hands over every secret"
    declared = set(wf[True]["workflow_call"]["secrets"]) if True in wf else set(wf["on"]["workflow_call"]["secrets"])
    assert set(secrets) == declared


@pytest.mark.parametrize("env,ok", [
    ({"REVIEW_LOGIN": "coderabbitai[bot]", "COMMENT_LOGIN": "", "ACTOR": "coderabbitai[bot]", "TRIGGERING_ACTOR": "coderabbitai[bot]"}, True),
    ({"REVIEW_LOGIN": "", "COMMENT_LOGIN": "", "ACTOR": "maintainer", "TRIGGERING_ACTOR": "maintainer"}, True),
    ({"REVIEW_LOGIN": SHARED_BOT, "COMMENT_LOGIN": "", "ACTOR": SHARED_BOT, "TRIGGERING_ACTOR": SHARED_BOT}, False),
    ({"REVIEW_LOGIN": "", "COMMENT_LOGIN": SHARED_BOT, "ACTOR": "x", "TRIGGERING_ACTOR": "x"}, False),
    ({"REVIEW_LOGIN": "", "COMMENT_LOGIN": "", "ACTOR": SHARED_BOT, "TRIGGERING_ACTOR": SHARED_BOT}, False),
    ({"REVIEW_LOGIN": "", "COMMENT_LOGIN": "", "ACTOR": "maintainer", "TRIGGERING_ACTOR": SHARED_BOT}, False),
])
def test_reusable_workflow_refuses_the_shared_identity(wf, tmp_path, env, ok):
    bash = _bash()
    if not bash:
        pytest.skip("bash is not available")
    step = _require_step(wf["jobs"]["config"], "shared workflow identity")
    assert wf["jobs"]["config"]["steps"].index(step) == 0, "refuse before anything else runs"
    for key in env:
        assert key in step["env"]
    proc = _run_step(step, tmp_path, env, bash, expect_ok=False)
    assert (proc.returncode == 0) is ok, proc.stdout + proc.stderr
