"""Consumer controls fail closed and skipped SARIF never reaches the uploader."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

import checkov_consumer_options as options


@pytest.mark.parametrize("value", ["CKV_AZURE_35", "CKV2_AZURE_1", "CKV_TF_1", "CKV_K8S_21"])
def test_valid_id(value):
    assert options.validate_skip_checks(value) == [value]


@pytest.mark.parametrize("value", [
    "CKV_AZURE_35, CKV_AZURE_36", "CKV_AZURE_35,", ",CKV_TF_1",
    "CKV_AZURE_35,,CKV_AZURE_36", "ckv_AZURE_35", "CKV3_AZURE_35",
    "CKV_AZURE_x", "CKV_AZURE_35\n", "CKV_AZURE_٣٥", "CKV__35",
    "CKV_AZURE_35;echo x", "HIGH", "CKV_AZURE_*", "BC_AZURE_GENERAL_35",
])
def test_invalid_id_names_rejected_value(value):
    with pytest.raises(ValueError, match="Invalid checkov-skip-checks ID") as exc:
        options.validate_skip_checks(value)
    invalid = next(part for part in value.split(",") if not options.CHECK_ID.fullmatch(part))
    assert repr(invalid) in str(exc.value)


def test_empty_id_list():
    assert options.validate_skip_checks("") == []


@pytest.mark.parametrize("configured", [["CKV_AZURE_35", "CKV_AZURE_35"], "CKV_AZURE_35,CKV_AZURE_35"])
def test_merge_deduplicates_preserving_order(configured):
    assert options.merge_skip_checks(configured, ["CKV_AZURE_36", "CKV_AZURE_35"]) == [
        "CKV_AZURE_35", "CKV_AZURE_36",
    ]


def test_merge_empty_and_existing_config_selectors():
    assert options.merge_skip_checks(None, []) == []
    assert options.merge_skip_checks([], []) == []
    assert options.merge_skip_checks(["CKV_AZURE_*"], []) == ["CKV_AZURE_*"]


@pytest.mark.parametrize("configured", [42, [42], [""], {"id": "CKV_TF_1"}])
def test_invalid_config_list(configured):
    with pytest.raises(ValueError, match="Config skip-check"):
        options.merge_skip_checks(configured, [])


@pytest.mark.parametrize("value", ["", "1", "20", "001"])
def test_valid_render_count(value):
    assert options.validate_render_count(value) == value


@pytest.mark.parametrize("value", ["0", "000", "-1", "+1", "1.0", "1e2", "true", " 2", "2\n", "٢"])
def test_invalid_render_count(value):
    with pytest.raises(ValueError, match="checkov-render-iter-count"):
        options.validate_render_count(value)


def test_sarif_fixture_keeps_failed_result_and_rule(fixtures_dir):
    sarif = json.loads((fixtures_dir / "checkov-suppressed.sarif").read_text())
    rules = copy.deepcopy(sarif["runs"][0]["tool"])
    assert options.filter_sarif(sarif) == 1
    assert [result["message"]["text"] for result in sarif["runs"][0]["results"]] == ["Failed resource"]
    assert sarif["runs"][0]["tool"] == rules
    assert options.filter_sarif(sarif) == 0


@pytest.mark.parametrize("marker", [
    {"suppressions": [{"kind": "external"}]},
    {"properties": {"check_result": {"result": "SKIPPED"}}},
    {"check_result": {"result": "SKIPPED"}},
    {"properties": {"status": "suppressed"}},
    {"properties": {"skipped": True}}, {"suppressed": True},
])
def test_skip_status_removed_across_runs(marker):
    failed = {"ruleId": "CKV_TF_1", "properties": {"suppressed": False}, "suppressions": []}
    sarif = {"runs": [{"results": [marker, failed]}, {"results": [marker]}, {}]}
    assert options.filter_sarif(sarif) == 2
    assert sarif["runs"][0]["results"] == [failed]
    assert sarif["runs"][1]["results"] == []


def run_helper(repo_root, args, **env):
    return subprocess.run(
        [sys.executable, str(repo_root / "scripts/checkov-consumer-options.py"), *map(str, args)],
        env={**os.environ, **env}, text=True, capture_output=True,
    )


@pytest.mark.parametrize("skip,render", [("", ""), ("CKV_AZURE_36,CKV_AZURE_35", "20")])
def test_prepare_outputs_summary_and_unset_default(repo_root, tmp_path, skip, render):
    config, output, summary = (tmp_path / name for name in ("config.yaml", "output", "summary"))
    config.write_text("skip-check: [CKV_AZURE_35]\n")
    result = run_helper(repo_root, ["prepare", config], CHECKOV_SKIP_CHECKS=skip,
                        CHECKOV_RENDER_ITER_COUNT=render, GITHUB_OUTPUT=str(output),
                        GITHUB_STEP_SUMMARY=str(summary))
    assert result.returncode == 0, result.stderr
    outputs = dict(line.split("=", 1) for line in output.read_text().splitlines())
    expected = "CKV_AZURE_35,CKV_AZURE_36" if skip else "CKV_AZURE_35"
    assert outputs["skip-checks"] == expected
    assert json.loads(outputs["render-env"]) == ({"RENDER_EDGES_DUPLICATE_ITER_COUNT": render} if render else {})
    assert expected in summary.read_text()
    assert (render or "unset (Checkov default)") in summary.read_text()


@pytest.mark.parametrize("skip,render", [("BAD", ""), ("", "0")])
def test_prepare_fails_closed(repo_root, tmp_path, skip, render):
    output = tmp_path / "output"
    result = run_helper(repo_root, ["prepare", tmp_path / "missing"], CHECKOV_SKIP_CHECKS=skip,
                        CHECKOV_RENDER_ITER_COUNT=render, GITHUB_OUTPUT=str(output))
    assert result.returncode == 1
    assert "::error::Invalid checkov-" in result.stdout
    assert not output.exists()


@pytest.mark.parametrize("cloud", ["aws", "azure", "gcp"])
def test_empty_inputs_preserve_cloud_skip_selection(repo_root, tmp_path, cloud):
    config = repo_root / "configs" / cloud / ".checkov.yaml"
    output, summary = tmp_path / "output", tmp_path / "summary"
    result = run_helper(repo_root, ["prepare", config], CHECKOV_SKIP_CHECKS="",
                        CHECKOV_RENDER_ITER_COUNT="", GITHUB_OUTPUT=str(output),
                        GITHUB_STEP_SUMMARY=str(summary))
    assert result.returncode == 0, result.stderr
    settings = yaml.safe_load(config.read_text(encoding="utf-8"))
    outputs = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert outputs["skip-checks"] == ",".join(settings.get("skip-check") or [])
    assert json.loads(outputs["render-env"]) == {}


def test_malformed_sarif_fails_without_rewriting(repo_root, tmp_path):
    sarif = tmp_path / "bad.sarif"
    sarif.write_text("{invalid")
    result = run_helper(repo_root, ["filter-sarif", sarif])
    assert result.returncode == 1
    assert "::error::" in result.stdout
    assert sarif.read_text() == "{invalid"


def workflow(repo_root):
    return yaml.safe_load((repo_root / ".github/workflows/reusable-scan.yml").read_text())


def test_workflow_scopes_env_and_gates_upload_after_filter_failure(repo_root):
    jobs = workflow(repo_root)["jobs"]
    scan = next(step for step in jobs["scan-checkov"]["steps"] if step["name"] == "Run Checkov")
    assert scan["env"] == "${{ fromJSON(needs.setup.outputs.checkov-render-env) }}"
    assert scan["with"]["skip_check"] == "${{ needs.setup.outputs.checkov-skip-checks }}"
    assert scan["uses"].endswith("@444c9db6fa75e2d9c19ebf1fde7322089be9009e")
    for name, job in jobs.items():
        for step in job["steps"]:
            if step is not scan:
                assert "RENDER_EDGES_DUPLICATE_ITER_COUNT" not in (step.get("env") or {})
    upload = next(step for step in jobs["sarif-upload"]["steps"] if step.get("id") == "upload-checkov")
    assert "steps.filter-checkov.outcome == 'success'" in upload["if"]
    artifact = next(step for step in jobs["scan-checkov"]["steps"] if step["name"] == "Upload Checkov results")
    assert "steps.filter-checkov-artifact.outcome == 'success'" in artifact["if"]


@pytest.mark.parametrize("contents,warning", [
    ("checkov_suppressions: [{rule_id: CKV_TF_1, tool: checkov}]", "missing expires_date"),
    ("checkov_suppressions: [", "Could not parse/apply .scan-suppressions.yaml"),
])
def test_aggregate_warns_for_ignored_or_unparseable_suppressions(repo_root, tmp_path, monkeypatch, capsys, contents, warning):
    steps = workflow(repo_root)["jobs"]["aggregate"]["steps"]
    script = next(step["run"] for step in steps if step.get("id") == "aggregate")
    section = script.split("# Apply suppressions", 1)[1].split("# Apply baseline", 1)[0]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APPLY_SUPPRESSIONS", "true")
    Path(".scan-suppressions.yaml").write_text(contents)
    from datetime import datetime, timezone
    exec(section, {"os": os, "datetime": datetime, "timezone": timezone, "findings": []})
    output = capsys.readouterr().out
    assert "::warning::" in output
    assert warning in output
