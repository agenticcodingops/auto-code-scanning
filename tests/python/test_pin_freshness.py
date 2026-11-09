"""Freshness reporting is read-only except for one marker-bound issue upsert."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from unittest.mock import MagicMock, Mock
import urllib.error

import jsonschema
import pytest
import yaml

import pin_freshness as pf

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 9, 8, 23, tzinfo=timezone.utc)


def pin(files=("one.txt",), policy="exact"):
    return {"id": "sample", "locations": [
        {"file": f, "pattern": r"pin=(?P<value>[^\n]+)"} for f in files],
        "source": {"type": "github_releases", "repo": "owner/tool"}, "policy": policy}


def client(latest="2.0.0"):
    api = Mock()
    api.upstream.return_value = (latest, "https://github.com/owner/tool/releases/tag/v2.0.0", {})
    api.pages.return_value = []
    return api


@pytest.mark.parametrize("older,newer", [("1.9.9", "1.10.0"), ("v0.99.0", "1.0.0"),
                                         ("3.11", "3.12"), ("9", "10.0.1")])
def test_numeric_version_order(older, newer):
    assert pf.version(older) < pf.version(newer)


def test_zero_padding_and_build_metadata():
    assert pf.version("v1.0.0+build.1") == pf.version("1")
    assert pf.normalized("3, 11, 0") == "3.11.0"


@pytest.mark.parametrize("value", ["1.2.0rc1", "1.2.0-beta.1", "latest", "banana", ""])
def test_prerelease_and_unsupported_versions_fail(value):
    with pytest.raises(ValueError):
        pf.version(value)


def test_extract_all_occurrences_and_report_drift(tmp_path):
    (tmp_path / "one.txt").write_text("pin=1.0\npin=1.1\n", encoding="utf-8")
    (tmp_path / "two.txt").write_text("pin=1.2\n", encoding="utf-8")
    entry = pin(("one.txt", "two.txt"))
    entry["precondition"] = "re-measure before bumping"
    values, errors = pf.extract(tmp_path, entry)
    assert values == [("one.txt", 1, "1.0"), ("one.txt", 2, "1.1"), ("two.txt", 1, "1.2")]
    assert not errors
    body, failed = pf.report(tmp_path, [entry], client(), "owner/repo", NOW)
    assert not failed
    assert "1.0, 1.1, 1.2 → **2.0.0**" in body
    assert "two.txt:1 = 1.2" in body
    assert "Precondition: re-measure before bumping" in body
    assert "([release](https://github.com/owner/tool/releases/tag/v2.0.0))" in body


def test_multiline_pattern_reports_the_value_line(tmp_path):
    (tmp_path / "one.json").write_text('{\n  "tool": {\n    "version": "1.2"\n  }\n}\n', encoding="utf-8")
    entry = pin(("one.json",))
    entry["locations"][0]["pattern"] = r'(?s:"tool":\s*\{.*?"version":\s*")(?P<value>[0-9.]+)'
    values, errors = pf.extract(tmp_path, entry)
    assert not errors
    assert values == [("one.json", 3, "1.2")]


def test_drift_summarizes_the_majority_and_lists_each_outlier_once(tmp_path):
    (tmp_path / "one.txt").write_text("pin=1.0\n" * 5 + "pin=0.9\n", encoding="utf-8")
    entry = pin(("one.txt", "one.txt"))
    body, failed = pf.report(tmp_path, [entry], client(), "owner/repo", NOW)
    assert not failed
    drift = body.split("## Cross-file drift")[1].split("## Lookup")[0]
    assert "5 locations = 1.0 (for example one.txt:1)" in drift
    assert drift.count("one.txt:6 = 0.9") == 1
    assert "one.txt:2 = 1.0" not in drift


def test_versions_are_listed_in_numeric_order(tmp_path):
    (tmp_path / "one.txt").write_text("pin=10\npin=9\n", encoding="utf-8")
    body, failed = pf.report(tmp_path, [pin()], client("11"), "owner/repo", NOW)
    assert not failed
    assert "9, 10 → **11**" in body


def test_minimums_do_not_produce_upgrade_or_false_drift(tmp_path):
    (tmp_path / "one.txt").write_text("pin=1.0\npin=1.0.0\n", encoding="utf-8")
    body, failed = pf.report(tmp_path, [pin(policy="minimum")], client(), "owner/repo", NOW)
    assert not failed
    assert "## Outdated pins\n\nNone." in body
    assert "## Cross-file drift\n\nNone." in body
    assert "minimum 1.0, 1.0.0" in body


def test_sha_and_version_comment_must_agree(tmp_path):
    sha = "a" * 40
    (tmp_path / "one.txt").write_text(f"pin={sha}\npin=1.1\n", encoding="utf-8")
    api = client()
    api.upstream.return_value = ("2", "https://github.com/owner/tool/releases/tag/v2", {sha: "1"})
    body, failed = pf.report(tmp_path, [pin()], api, "owner/repo", NOW)
    assert not failed
    assert "one.txt:2 = 1.1" in body


def test_integrity_mirror_drift_is_independent_of_version(tmp_path):
    (tmp_path / "one.txt").write_text("pin=1\nsha=aaa\nsha=bbb\n", encoding="utf-8")
    entry = pin()
    entry["mirrors"] = [{"id": "asset-sha256", "locations": [
        {"file": "one.txt", "pattern": r"sha=(?P<value>\w+)"}]}]
    body, failed = pf.report(tmp_path, [entry], client("1"), "owner/repo", NOW)
    assert not failed
    assert "**sample/asset-sha256**" in body
    assert "one.txt:2 = aaa" in body and "one.txt:3 = bbb" in body
    assert "## Outdated pins\n\nNone." in body


def test_failures_not_silently_skipped(tmp_path):
    (tmp_path / "one.txt").write_text("pin=1\n", encoding="utf-8")
    api = client()
    api.upstream.side_effect = ValueError("HTTP 403")
    api.pages.side_effect = ValueError("HTTP 502")
    body, failed = pf.report(tmp_path, [pin(("one.txt", "missing.txt"))], api, "owner/repo", NOW)
    assert failed
    assert "missing.txt" in body and "HTTP 403" in body and "HTTP 502" in body
    assert "dependency PR lookup" in body


def test_no_match_is_an_extraction_failure(tmp_path):
    (tmp_path / "one.txt").write_text("other=1", encoding="utf-8")
    assert "pattern matched no values" in pf.extract(tmp_path, pin())[1][0]


@pytest.mark.parametrize("path", ["../outside", "/absolute", "C:/absolute", ".git/config", "dir\\file"])
def test_reject_unsafe_paths(tmp_path, path):
    with pytest.raises(ValueError):
        pf.safe_file(tmp_path, path)


def test_linked_files_are_rejected(tmp_path):
    target = tmp_path / "target"
    target.write_text("pin=1", encoding="utf-8")
    link = tmp_path / "one.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("host cannot create symlinks")
    assert pf.extract(tmp_path, pin())[1]


def test_marker_upsert_preserves_state_and_ignores_title_and_prs():
    api = client()
    api.pages.return_value = [{"number": 1, "title": "Weekly pin freshness", "body": "unrelated"},
                             {"number": 2, "pull_request": {}, "body": pf.MARKER},
                             {"number": 3, "state": "closed", "title": "renamed", "body": pf.MARKER + "\nold",
                              "user": {"login": pf.REPORT_AUTHOR}}]
    pf.upsert_issue(api, "owner/repo", "New title", pf.MARKER + "\nnew")
    api.request.assert_called_once_with(pf.API + "/repos/owner/repo/issues/3", "PATCH",
                                        {"title": "New title", "body": pf.MARKER + "\nnew"})


def test_marker_create_and_duplicate_refusal():
    api = client()
    pf.upsert_issue(api, "owner/repo", "title", pf.MARKER)
    assert api.request.call_args.args[1] == "POST"
    api.request.reset_mock()
    api.pages.return_value = [{"number": n, "body": pf.MARKER, "user": {"login": pf.REPORT_AUTHOR}}
                             for n in (1, 2)]
    with pytest.raises(ValueError, match="multiple"):
        pf.upsert_issue(api, "owner/repo", "title", pf.MARKER)
    api.request.assert_not_called()


@pytest.mark.parametrize("author", [pf.REPORT_AUTHOR, "local-maintainer"])
def test_spoofed_marker_issues_are_ignored_and_query_is_author_scoped(author):
    api = client()
    api.pages.return_value = [{"number": 1, "body": pf.MARKER, "user": {"login": "unrelated-user"}}]
    pf.upsert_issue(api, "owner/repo", "title", pf.MARKER, author=author)
    assert api.request.call_args.args[1] == "POST"
    assert api.pages.call_args.args[0].endswith("&creator=" + pf.urllib.parse.quote(author, safe=""))


def test_local_write_uses_authenticated_author(tmp_path, monkeypatch):
    (tmp_path / "manifest.json").write_text(json.dumps({"pins": [pin()]}), encoding="utf-8")
    (tmp_path / "one.txt").write_text("pin=1", encoding="utf-8")
    api = client()
    api.token = "token"
    api.request.return_value = {"login": "local-maintainer"}
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(pf, "Client", lambda _: api)
    monkeypatch.setattr(pf, "upsert_issue", Mock())
    assert pf.main(["--root", str(tmp_path), "--manifest", "manifest.json",
                    "--repository", "owner/repo"]) == 0
    api.request.assert_called_once_with(pf.API + "/user")
    assert pf.upsert_issue.call_args.kwargs == {"author": "local-maintainer"}


def pr(number, age, login="someone", labels=()):
    return {"number": number, "title": "update", "html_url": "https://github.com/owner/repo/pull/1",
            "created_at": (NOW - age).isoformat(), "user": {"login": login},
            "labels": [{"name": label} for label in labels]}


def test_stale_prs_strict_boundary_labels_and_dependency_bots():
    api = client()
    api.pages.return_value = [pr(1, timedelta(days=7), labels=["dependencies"]),
                             pr(2, timedelta(days=7, seconds=1), labels=["dependencies"]),
                             pr(3, timedelta(days=9), "dependabot[bot]"),
                             pr(4, timedelta(days=10), "unrelated[bot]"),
                             pr(5, timedelta(days=8), "renovate[bot]")]
    assert {p["number"] for p in pf.stale_prs(api, "owner/repo", NOW)} == {2, 3, 5}


def test_github_release_filtering_numeric_order_and_caching():
    api = pf.Client("token")
    api.pages = Mock(return_value=[{"tag_name": "v1.9.0"}, {"tag_name": "v1.10.0"},
                                  {"tag_name": "v9.0.0", "draft": True},
                                  {"tag_name": "v8.0.0", "prerelease": True},
                                  {"tag_name": "v2.0.0rc1"}])
    source = {"type": "github_releases", "repo": "owner/tool"}
    assert api.upstream(source)[0] == "1.10.0"
    api.upstream(source)
    api.pages.assert_called_once()


def test_tag_prefix_and_commit_mapping():
    api = pf.Client("")
    api.pages = Mock(return_value=[{"name": "tool-v2.0.0", "commit": {"sha": "a" * 40}}])
    latest, url, revisions = api.upstream({"type": "github_tags", "repo": "owner/tool",
                                         "tag_pattern": r"tool-v(?P<version>\d+\.\d+\.\d+)"})
    assert latest == "2.0.0" and revisions == {"a" * 40: "2.0.0"}
    assert url.endswith("tool-v2.0.0")


def test_major_alias_cannot_replace_exact_tag_for_same_commit():
    api = pf.Client("")
    api.pages = Mock(return_value=[{"name": tag, "commit": {"sha": "a" * 40}}
                                  for tag in ["v3.1.0", "v3"]])
    assert api.upstream({"type": "github_tags", "repo": "owner/tool"})[2] == {"a" * 40: "3.1.0"}


def test_pypi_excludes_prereleases_yanked_and_empty_releases():
    api = pf.Client("token")
    api.request = Mock(return_value={"releases": {"1.0": [{"yanked": False}],
                                                "2.0": [{"yanked": True}], "3.0": [],
                                                "4.0rc1": [{"yanked": False}]}})
    assert api.upstream({"type": "pypi", "package": "sample"})[0] == "1.0"


def test_empty_upstream_and_failures_are_cached():
    api = pf.Client("")
    api.pages = Mock(return_value=[])
    for _ in range(2):
        with pytest.raises(ValueError, match="no stable"):
            api.upstream({"type": "github_releases", "repo": "owner/tool"})
    api.pages.assert_called_once()


def test_pagination_reads_all_pages():
    api = pf.Client("")
    api.request = Mock(side_effect=[[{}] * 100, [{"number": 101}]])
    assert len(api.pages("/repos/owner/repo/issues?state=all")) == 101
    assert api.request.call_args.args[0].endswith("&per_page=100&page=2")


def test_token_only_sent_to_github_and_redirects_disabled(monkeypatch):
    requests = []
    opener = MagicMock()
    response = Mock()
    response.read.return_value = b'{}'
    opener.open.return_value.__enter__.return_value = response
    def build(handler):
        assert isinstance(handler, pf.NoRedirect)
        return opener
    monkeypatch.setattr(pf.urllib.request, "build_opener", build)
    api = pf.Client("sensitive")
    for url in [pf.API + "/repos/owner/tool", "https://pypi.org/pypi/sample/json"]:
        api.request(url)
        requests.append(opener.open.call_args.args[0])
    assert requests[0].get_header("Authorization") == "Bearer sensitive"
    assert requests[1].get_header("Authorization") is None
    with pytest.raises(ValueError, match="origin"):
        api.request("https://untrusted.example")
    assert pf.NoRedirect().redirect_request(None, None, 302, "", {}, "https://other") is None


def test_http_errors_do_not_expose_headers_or_response_body(monkeypatch):
    opener = Mock()
    opener.open.side_effect = urllib.error.HTTPError(pf.API, 403, "sensitive", {}, None)
    monkeypatch.setattr(pf.urllib.request, "build_opener", lambda _: opener)
    with pytest.raises(ValueError, match="^api.github.com: HTTP 403$"):
        pf.Client("token").request(pf.API)


def test_untrusted_markdown_is_escaped():
    assert "<" not in pf.md("<script>")
    assert pf.md("@person [link](url)") == r"\@person \[link\](url)"


def test_manifest_schema_and_all_real_patterns_match():
    data = json.loads((ROOT / ".github/pin-freshness.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "schemas/pin-freshness.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(data, schema)
    pins = pf.load_manifest(ROOT, ".github/pin-freshness.json")
    for entry in pins:
        values, errors = pf.extract(ROOT, entry)
        assert values and not errors, (entry["id"], errors)
        for mirror in entry.get("mirrors", []):
            observed, errors = pf.extract(ROOT, {**mirror, "id": entry["id"]})
            assert observed and not errors, (entry["id"], mirror["id"], errors)
            assert len({value for _, _, value in observed}) == 1


def test_real_gitleaks_patterns_do_not_capture_other_scanners():
    pins = pf.load_manifest(ROOT, ".github/pin-freshness.json")
    entry = next(p for p in pins if p["id"] == "gitleaks")
    lock = json.loads((ROOT / "scripts/scanner-downloads.json").read_text(encoding="utf-8"))
    values, errors = pf.extract(ROOT, entry)
    assert not errors
    assert {value for _, _, value in values} == {lock["gitleaks"]["version"]}
    assert any(file == ".github/workflows/ci.yml" for file, _, _ in values)


def test_future_pester_bump_is_observed_despite_unchanged_comments(tmp_path):
    pins = pf.load_manifest(ROOT, ".github/pin-freshness.json")
    entry = next(p for p in pins if p["id"] == "pester-minimum")
    for location in entry["locations"]:
        file = location["file"]
        text = (ROOT / file).read_text(encoding="utf-8")
        if file == ".github/workflows/copilot-setup-steps.yml":
            text = text.replace("Install-Module Pester -MinimumVersion 5.0.0",
                                "Install-Module Pester -MinimumVersion 5.7.1")
        path = tmp_path / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    body, failed = pf.report(tmp_path, [entry], client("6.2.0"), "owner/repo", NOW)
    assert not failed
    assert "5.7.1" in body.split("## Cross-file drift")[1].split("## Lookup")[0]


def test_historical_walkthrough_and_specifications_are_not_upgrade_targets():
    pins = pf.load_manifest(ROOT, ".github/pin-freshness.json")
    for entry in pins:
        files = {location["file"] for location in entry["locations"]}
        assert "docs/V3-WALKTHROUGH-RESULTS.md" not in files
        assert not any(file.startswith("specs/") for file in files)


def test_manual_selections_do_not_pretend_to_have_release_versions(tmp_path):
    (tmp_path / "one.txt").write_text("pin=floating-label", encoding="utf-8")
    entry = {**pin(policy="manual"), "review_reason": "Review the service catalog"}
    api = client()
    body, failed = pf.report(tmp_path, [entry], api, "owner/repo", NOW)
    assert not failed
    assert "Review the service catalog" in body
    api.upstream.assert_not_called()


def test_dry_run_never_writes_even_on_lookup_failure(tmp_path, monkeypatch, capsys):
    (tmp_path / "manifest.json").write_text(json.dumps({"pins": [pin()]}), encoding="utf-8")
    (tmp_path / "one.txt").write_text("pin=1", encoding="utf-8")
    api = client()
    api.upstream.side_effect = ValueError("lookup failed")
    monkeypatch.setattr(pf, "Client", lambda _: api)
    monkeypatch.setattr(pf, "upsert_issue", Mock())
    assert pf.main(["--root", str(tmp_path), "--manifest", "manifest.json",
                    "--repository", "owner/repo", "--dry-run"]) == 1
    pf.upsert_issue.assert_not_called()
    assert "lookup failed" in capsys.readouterr().out
    assert sorted(p.name for p in tmp_path.iterdir()) == ["manifest.json", "one.txt"]


def test_workflow_uses_reviewed_helpers_and_minimum_permissions():
    workflow = yaml.safe_load((ROOT / ".github/workflows/pin-freshness.yml").read_text(encoding="utf-8"))
    triggers = workflow.get("on", workflow.get(True))
    assert triggers["schedule"] == [{"cron": "23 8 * * 1"}]
    assert {"workflow_dispatch", "workflow_call"} <= triggers.keys()
    job = workflow["jobs"]["report"]
    assert job["permissions"] == {"contents": "read", "issues": "write", "pull-requests": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] is False
    steps = job["steps"]
    assert steps[1]["with"]["repository"] == "agenticcodingops/auto-code-scanning"
    assert "inputs.scanning-repo-ref" in steps[1]["with"]["ref"]
    assert all(s.get("with", {}).get("persist-credentials") is False for s in steps[:2])
    assert "python -I" in steps[-1]["run"] and "runpy.run_path" in steps[-1]["run"]
    assert "${{" not in steps[-1]["run"]
