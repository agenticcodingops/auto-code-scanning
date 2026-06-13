"""Trust-boundary tests for the reusable agentic fix-loop (autonomous-fix.yml).

These assert the security properties of the workflow STRUCTURE (the loop's real
enforcement), so a future edit cannot silently reintroduce the privilege-escalation
path where a labelled PR sets a malicious fix_loop.build_verify_cmd at its head and
runs it while the push token is on disk.

Properties asserted:
  * fix_loop config is read from the TRUSTED base ref (never the PR head).
  * build_verify_cmd executed by apply-and-push comes from the config job's output
    (base-sourced), NOT from a head-read value -> a PR cannot change what runs.
  * the apply checkout never writes the token to disk (persist-credentials: false,
    no `token:` input); only the final push step holds AUTOFIX_TOKEN.
  * the allowlist gate (analyze + apply) reads the trusted base config artifact.
"""
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WF = REPO_ROOT / ".github" / "workflows" / "autonomous-fix.yml"


@pytest.fixture(scope="module")
def wf():
    return yaml.safe_load(WF.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def raw():
    return WF.read_text(encoding="utf-8")


def _step(job, name_contains):
    for s in job["steps"]:
        if name_contains.lower() in s.get("name", "").lower():
            return s
    return None


def test_config_read_from_base_ref(wf):
    checkout = wf["jobs"]["config"]["steps"][0]
    ref = checkout["with"]["ref"]
    assert "pull_request.base.sha" in ref, "config job must check out the BASE ref, not PR head"
    assert checkout["with"]["persist-credentials"] is False


def test_build_verify_cmd_is_base_sourced(wf):
    bv = _step(wf["jobs"]["apply-and-push"], "build verify")
    assert bv is not None
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
    assert raw.count("TRUSTED_CONFIG: .trusted/trusted-scan-config.yaml") == 2
    assert "name: trusted-config" in raw
    # The gate must NOT read inputs.config_path (the PR-head file) anymore.
    for job in ("analyze", "apply-and-push"):
        gate = _step(wf["jobs"][job], "gate")
        assert gate is not None
        assert "inputs.config_path" not in yaml.safe_dump(gate)


def test_pyyaml_is_ensured_where_yaml_is_parsed(raw):
    # config job + both gate jobs install pyyaml so a missing dep can't silently break it.
    assert raw.count("pip install --quiet --disable-pip-version-check pyyaml") >= 3
