"""Tests for the release automation (release-please).

These assert the properties a release depends on, so an edit cannot silently break
the next release:

  * tags stay `vX.Y.Z`, the package is the `simple` type, and the release PR's
    footer is the neutral one, not release-please's default.
  * the manifest, version.txt and every `x-release-please-version` line agree.
  * release-please inserts a new CHANGELOG entry above the latest release's heading,
    so the hand-written history below it is never touched.
  * release.yml pins the action to a commit SHA, never cancels a run in progress,
    and never runs on pull_request_target.
  * release.yml writes with a token minted from the release GitHub App, for this
    repository only and with only the permissions release-please needs.
  * every published release starts the scan self-test on its own tag.
"""
import json
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

# release-please 17.x inserts a new entry before the first match of this pattern
# (DEFAULT_VERSION_HEADER_REGEX in its updaters/changelog.ts).
CHANGELOG_INSERT_POINT = re.compile(r"\n###? v?[0-9[]")
SEMVER = re.compile(r"\d+\.\d+\.\d+")

# A pin of this repository in a shipped template: a `uses:` of one of its workflows at a tag, or its
# `scanning-repo-ref` / `scanning_repo_ref` input set to a tag. A pre-commit entry is two lines: the
# `repo:` and the `rev:` under it.
TEMPLATE_PIN = re.compile(
    r"auto-code-scanning/\.github/workflows/[\w.-]+\.yml@v\d"
    r"|scanning[-_]repo[-_]ref:\s*\"?v\d"
)
TEMPLATE_REPO = re.compile(r"repo:\s*https://github\.com/[^\s/]+/auto-code-scanning\s*$")


@pytest.fixture(scope="module")
def config():
    return json.loads((REPO_ROOT / "release-please-config.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def package(config):
    return config["packages"]["."]


@pytest.fixture(scope="module")
def manifest_version():
    manifest = json.loads((REPO_ROOT / ".release-please-manifest.json").read_text(encoding="utf-8"))
    return manifest["."]


def _workflow(name):
    data = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    # PyYAML reads the bare key `on` as the boolean True.
    data["on"] = data.pop(True, data.get("on"))
    return data


def _step_using(steps, prefix):
    matches = [s for s in steps if s.get("uses", "").startswith(prefix)]
    assert len(matches) == 1, f"expected one step using {prefix}"
    return matches[0]


def test_tags_keep_the_v_prefix_and_no_component(config):
    assert config["include-v-in-tag"] is True
    assert config["include-component-in-tag"] is False


def test_package_is_simple_with_the_existing_changelog(package):
    assert package["release-type"] == "simple"
    assert package["changelog-path"] == "CHANGELOG.md"
    assert package["version-file"] == "version.txt"


def test_pull_request_footer_is_neutral(config):
    footer = config.get("pull-request-footer", "")
    assert footer, "an unset footer falls back to release-please's default"
    assert not footer.startswith("This PR was generated with")


def test_changelog_sections(config):
    sections = {s["type"]: s for s in config["changelog-sections"]}
    for visible in ("feat", "fix", "perf", "revert"):
        assert not sections[visible].get("hidden", False), visible
    for hidden in ("docs", "chore", "ci", "test", "style", "refactor"):
        assert sections[hidden].get("hidden") is True, hidden


def test_versions_agree(package, manifest_version):
    assert (REPO_ROOT / "version.txt").read_text(encoding="utf-8") == manifest_version + "\n"
    for extra in package["extra-files"]:
        marked = [
            line for line in (REPO_ROOT / extra).read_text(encoding="utf-8").splitlines()
            if "x-release-please-version" in line
        ]
        assert marked, f"{extra} has no x-release-please-version line"
        for line in marked:
            assert SEMVER.findall(line)[:1] == [manifest_version], f"{extra}: {line}"


def _template_pins():
    """(path, line number, line) for each line of a shipped template that pins this repository to a tag."""
    for path in sorted((REPO_ROOT / "templates").rglob("*")):
        if path.suffix not in (".yml", ".yaml"):
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, start=1):
            if line.lstrip().startswith("#"):
                continue
            if TEMPLATE_PIN.search(line):
                yield path, number, line
            elif TEMPLATE_REPO.search(line.strip()):
                following = lines[number]
                assert following.strip().startswith("rev:"), f"{path}:{number + 1}: expected the rev: of this repository"
                yield path, number + 1, following


def test_every_template_pin_of_this_repository_is_a_marked_line_in_extra_files(package):
    # A template that pins a tag no release moves goes stale: the callers said v2.0.0 and the pre-commit
    # templates v1.0.0, a tag that does not exist, through v2.3.1.
    pins = list(_template_pins())
    assert len(pins) >= 11, f"found only {len(pins)} pins; the search no longer matches the templates"
    listed = set(package["extra-files"])
    for path, number, line in pins:
        rel = path.relative_to(REPO_ROOT).as_posix()
        assert "x-release-please-version" in line, f"{rel}:{number} pins a tag no release moves: {line.strip()}"
        assert rel in listed, f"{rel} has a marked pin but is not under extra-files"


def test_new_changelog_entries_land_above_the_latest_release(manifest_version):
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = CHANGELOG_INSERT_POINT.search(changelog)
    assert match, "release-please would rewrite the whole file"
    first_heading = changelog[match.start():].lstrip("\n").splitlines()[0]
    assert first_heading.startswith(f"## [{manifest_version}]"), first_heading


def test_release_workflow():
    wf = _workflow("release.yml")
    assert "pull_request_target" not in wf["on"]
    assert wf["on"]["push"]["branches"] == ["main"]
    assert "workflow_dispatch" in wf["on"]
    assert wf["concurrency"]["cancel-in-progress"] is False
    assert "${{" not in wf["concurrency"]["group"], "one group for every release run"

    steps = wf["jobs"]["release-please"]["steps"]
    action = _step_using(steps, "googleapis/release-please-action@")
    assert re.fullmatch(r"googleapis/release-please-action@[0-9a-f]{40}", action["uses"])
    # No step script may read the release notes or the release PR.
    for step in steps:
        for value in (step.get("env") or {}).values():
            assert "outputs.body" not in value and "outputs.pr" not in value


def test_release_token_is_minted_from_the_app():
    steps = _workflow("release.yml")["jobs"]["release-please"]["steps"]
    mint = _step_using(steps, "actions/create-github-app-token@")
    assert re.fullmatch(r"actions/create-github-app-token@[0-9a-f]{40}", mint["uses"])
    inputs = mint["with"]
    assert inputs["client-id"] == "${{ vars.RELEASE_APP_CLIENT_ID }}"
    assert inputs["private-key"] == "${{ secrets.RELEASE_APP_PRIVATE_KEY }}"
    # Without owner or repositories the token covers this repository only.
    assert "owner" not in inputs and "repositories" not in inputs
    assert str(inputs.get("skip-token-revoke", "false")).lower() == "false"
    requested = {k: v for k, v in inputs.items() if k.startswith("permission-")}
    assert requested == {
        "permission-contents": "write",
        "permission-pull-requests": "write",
        "permission-issues": "write",
    }

    action = _step_using(steps, "googleapis/release-please-action@")
    assert steps.index(mint) < steps.index(action)
    assert action["with"]["token"] == "${{ steps.%s.outputs.token }}" % mint["id"]


def test_every_published_release_runs_the_self_test_on_its_tag():
    wf = _workflow("release-verify.yml")
    assert wf["on"]["release"]["types"] == ["published"]
    assert "concurrency" not in wf, "it would equal reusable-scan.yml's group"
    job = wf["jobs"]["self-test"]
    assert job["uses"] == "./.github/workflows/reusable-scan-self-test.yml"
    assert "refs/tags/" in job["if"]

    self_test = _workflow("reusable-scan-self-test.yml")
    assert "workflow_call" in self_test["on"]
    assert "${{ github.sha }}" in self_test["jobs"]["scan"]["with"]["scanning-repo-ref"]
