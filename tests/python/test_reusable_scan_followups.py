"""Two behaviours of reusable-scan.yml that one bad input used to break.

Both tests read the code out of the workflow file and run it, so they test what ships:

* the Aggregate step applies each suppression on its own. One entry with an unquoted date
  (PyYAML reads `2026-12-31` as a date object), a malformed date, or a wrong shape used to make
  the whole `try` fail, so every suppression in the file was dropped.
* the PR comment lists CRITICAL findings first. `order[x] || 4` turned CRITICAL's rank of 0
  into 4, which sorted it after LOW.
"""

import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "reusable-scan.yml"

TODAY = datetime.now(timezone.utc).date()
FUTURE = (TODAY + timedelta(days=30)).isoformat()
PAST = (TODAY - timedelta(days=30)).isoformat()


def workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def suppression_section():
    steps = workflow()["jobs"]["aggregate"]["steps"]
    script = next(step["run"] for step in steps if step.get("id") == "aggregate")
    return script.split("# Apply suppressions", 1)[1].split("# Apply baseline", 1)[0]


def finding(rule, tool="checkov"):
    return {"rule_id": rule, "tool": tool, "suppressed": False, "baseline": False}


def apply(tmp_path, monkeypatch, capsys, contents, findings, enabled="true"):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APPLY_SUPPRESSIONS", enabled)
    (tmp_path / ".scan-suppressions.yaml").write_text(contents, encoding="utf-8")
    namespace = {"os": os, "datetime": datetime, "timezone": timezone, "findings": findings}
    # The text run here is this repository's own workflow file, read from the same checkout: it is
    # the thing under test, not input from outside. The existing aggregate test does the same.
    exec(suppression_section(), namespace)  # nosemgrep
    return namespace["suppressions_applied"], capsys.readouterr().out


def suppressed(findings):
    return [f["rule_id"] for f in findings if f["suppressed"]]


GOOD = f"""
checkov_suppressions:
  - {{rule_id: CKV_GOOD, tool: checkov, expires_date: "{FUTURE}"}}
"""


def test_a_valid_entry_is_applied(tmp_path, monkeypatch, capsys):
    findings = [finding("CKV_GOOD"), finding("CKV_OTHER")]
    applied, out = apply(tmp_path, monkeypatch, capsys, GOOD, findings)
    assert applied == 1
    assert suppressed(findings) == ["CKV_GOOD"]
    assert "::warning::" not in out


def test_an_expired_entry_is_not_applied(tmp_path, monkeypatch, capsys):
    contents = f'checkov_suppressions:\n  - {{rule_id: CKV_OLD, tool: checkov, expires_date: "{PAST}"}}\n'
    findings = [finding("CKV_OLD")]
    applied, _ = apply(tmp_path, monkeypatch, capsys, contents, findings)
    assert applied == 0
    assert suppressed(findings) == []


def test_an_unquoted_date_skips_that_entry_only(tmp_path, monkeypatch, capsys):
    # Before the fix this raised TypeError, and every suppression in the file was dropped.
    contents = (
        "checkov_suppressions:\n"
        f"  - {{rule_id: CKV_UNQUOTED, tool: checkov, expires_date: {FUTURE}}}\n"
        f'  - {{rule_id: CKV_GOOD, tool: checkov, expires_date: "{FUTURE}"}}\n'
    )
    findings = [finding("CKV_UNQUOTED"), finding("CKV_GOOD")]
    applied, out = apply(tmp_path, monkeypatch, capsys, contents, findings)
    assert suppressed(findings) == ["CKV_GOOD"]
    assert applied == 1
    assert "::warning::Ignored checkov_suppressions entry CKV_UNQUOTED" in out
    assert "quoted" in out


def test_a_malformed_date_is_reported_and_the_rest_apply(tmp_path, monkeypatch, capsys):
    # Before the fix a ValueError here was swallowed with no message.
    contents = (
        "checkov_suppressions:\n"
        '  - {rule_id: CKV_BAD, tool: checkov, expires_date: "31/12/2030"}\n'
        f'  - {{rule_id: CKV_GOOD, tool: checkov, expires_date: "{FUTURE}"}}\n'
    )
    findings = [finding("CKV_BAD"), finding("CKV_GOOD")]
    applied, out = apply(tmp_path, monkeypatch, capsys, contents, findings)
    assert suppressed(findings) == ["CKV_GOOD"]
    assert "Ignored checkov_suppressions entry CKV_BAD" in out


def test_an_entry_that_is_not_a_mapping_is_skipped(tmp_path, monkeypatch, capsys):
    contents = f'checkov_suppressions:\n  - just-a-string\n  - {{rule_id: CKV_GOOD, tool: checkov, expires_date: "{FUTURE}"}}\n'
    findings = [finding("CKV_GOOD")]
    applied, out = apply(tmp_path, monkeypatch, capsys, contents, findings)
    assert applied == 1
    assert "entry 1" in out
    assert "not a mapping" in out


def test_an_entry_without_a_rule_id_is_skipped(tmp_path, monkeypatch, capsys):
    contents = f'checkov_suppressions:\n  - {{tool: checkov, expires_date: "{FUTURE}"}}\n  - {{rule_id: CKV_GOOD, tool: checkov, expires_date: "{FUTURE}"}}\n'
    findings = [finding("CKV_GOOD")]
    applied, out = apply(tmp_path, monkeypatch, capsys, contents, findings)
    assert applied == 1
    assert "rule_id is missing" in out


def test_a_missing_expiry_keeps_its_existing_message(tmp_path, monkeypatch, capsys):
    contents = "checkov_suppressions:\n  - {rule_id: CKV_TF_1, tool: checkov}\n"
    _, out = apply(tmp_path, monkeypatch, capsys, contents, [])
    assert "::warning::Ignored checkov_suppressions entry CKV_TF_1: missing expires_date" in out


def test_a_section_that_is_not_a_list_is_skipped_and_the_others_apply(tmp_path, monkeypatch, capsys):
    contents = (
        "trivy_suppressions: not-a-list\n"
        f'checkov_suppressions:\n  - {{rule_id: CKV_GOOD, tool: checkov, expires_date: "{FUTURE}"}}\n'
    )
    findings = [finding("CKV_GOOD")]
    applied, out = apply(tmp_path, monkeypatch, capsys, contents, findings)
    assert applied == 1
    assert "Ignored trivy_suppressions: it is not a list" in out


def test_entries_in_every_section_are_applied(tmp_path, monkeypatch, capsys):
    contents = "".join(
        f'{section}:\n  - {{rule_id: R_{tool}, tool: {tool}, expires_date: "{FUTURE}"}}\n'
        for section, tool in (("trivy_suppressions", "trivy"), ("checkov_suppressions", "checkov"),
                              ("tflint_suppressions", "tflint"), ("snyk_suppressions", "snyk")))
    findings = [finding(f"R_{tool}", tool) for tool in ("trivy", "checkov", "tflint", "snyk")]
    applied, _ = apply(tmp_path, monkeypatch, capsys, contents, findings)
    assert applied == 4


@pytest.mark.parametrize("contents", ["checkov_suppressions: [", "- a\n- b\n", "just a string"])
def test_an_unreadable_file_warns_and_applies_nothing(tmp_path, monkeypatch, capsys, contents):
    findings = [finding("CKV_GOOD")]
    applied, out = apply(tmp_path, monkeypatch, capsys, contents, findings)
    assert applied == 0
    assert suppressed(findings) == []
    assert "::warning::Could not parse/apply .scan-suppressions.yaml" in out


@pytest.mark.parametrize("contents", ["[]", "false", "0", '""', "[]\n", "0.0"])
def test_a_falsy_document_that_is_not_a_mapping_still_warns(tmp_path, monkeypatch, capsys, contents):
    # `yaml.safe_load(f) or {}` used to turn these into an empty mapping, so nothing was reported.
    applied, out = apply(tmp_path, monkeypatch, capsys, contents, [finding("CKV_GOOD")])
    assert applied == 0
    assert "::warning::Could not parse/apply .scan-suppressions.yaml" in out


@pytest.mark.parametrize("value", ["false", "0", '""', "{}", "0.0"])
def test_a_falsy_section_that_is_not_a_list_still_warns(tmp_path, monkeypatch, capsys, value):
    contents = f"trivy_suppressions: {value}\n" + GOOD
    findings = [finding("CKV_GOOD")]
    applied, out = apply(tmp_path, monkeypatch, capsys, contents, findings)
    assert applied == 1
    assert "Ignored trivy_suppressions: it is not a list" in out


@pytest.mark.parametrize("contents", ["", "# only a comment\n", "~\n", "trivy_suppressions:\n", "trivy_suppressions: []\n"])
def test_an_empty_document_or_section_is_not_an_error(tmp_path, monkeypatch, capsys, contents):
    applied, out = apply(tmp_path, monkeypatch, capsys, contents, [finding("CKV_GOOD")])
    assert applied == 0
    assert out == ""


def test_text_from_the_file_cannot_start_a_workflow_command(tmp_path, monkeypatch, capsys):
    contents = 'checkov_suppressions:\n  - {rule_id: "X\\n::error::pwn 100%", tool: checkov}\n'
    _, out = apply(tmp_path, monkeypatch, capsys, contents, [])
    assert out.count("\n") == 1, out
    assert "%0A" in out
    assert "%25" in out


def test_nothing_is_applied_when_the_input_is_off(tmp_path, monkeypatch, capsys):
    findings = [finding("CKV_GOOD")]
    applied, out = apply(tmp_path, monkeypatch, capsys, GOOD, findings, enabled="false")
    assert applied == 0
    assert out == ""


# --- the PR comment's sort ---------------------------------------------------------------------

def comparator_body():
    steps = workflow()["jobs"]["pr-comment"]["steps"]
    script = next(step["with"]["script"] for step in steps if "github-script" in step.get("uses", ""))
    match = re.search(r"\.sort\(\(a, b\) => \{(.*?)\n\s*\}\)", script, re.S)
    assert match, "the PR comment's sort was not found"
    return match.group(1)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_pr_comment_lists_critical_findings_first():
    program = (
        "const cmp = (a, b) => {" + comparator_body() + "};\n"
        "const f = ['LOW', 'CRITICAL', 'MEDIUM', 'HIGH', 'UNKNOWN', 'CRITICAL']"
        ".map((severity) => ({ severity }));\n"
        "console.log(f.sort(cmp).map((x) => x.severity).join(','));\n"
    )
    result = subprocess.run(["node", "-e", program], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "CRITICAL,CRITICAL,HIGH,MEDIUM,LOW,UNKNOWN"


def test_the_sort_uses_nullish_coalescing_not_or():
    body = comparator_body()
    assert "?? 4" in body
    assert "|| 4" not in body
