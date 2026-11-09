"""Keep scheduled dependency updates aligned with the pin-update policy."""
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG = yaml.safe_load((REPO_ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8"))


def test_only_supported_manifest_locations_are_configured():
    assert CONFIG["version"] == 2
    assert [(entry["package-ecosystem"], entry["directory"]) for entry in CONFIG["updates"]] == [
        ("github-actions", "/"), ("pre-commit", "/scripts"),
    ]
    assert (REPO_ROOT / "scripts" / ".pre-commit-config.yaml").is_file()


@pytest.mark.parametrize("entry", CONFIG["updates"], ids=lambda entry: entry["package-ecosystem"])
def test_weekly_update_policy(entry):
    assert entry["schedule"] == {
        "interval": "weekly", "day": "monday", "time": "06:00", "timezone": "Etc/UTC",
    }
    assert entry["commit-message"] == {"prefix": "chore(deps)"}
    assert entry["labels"] == ["dependencies"]
    assert entry["open-pull-requests-limit"] == 5
    groups = list(entry["groups"].values())
    assert len(groups) == 1
    assert groups[0] == {"patterns": ["*"], "update-types": ["patch", "minor"]}
    # Majors match no group and therefore get individual PRs.


def test_conditional_actions_and_release_managed_hooks_are_never_updated():
    entries = {entry["package-ecosystem"]: entry for entry in CONFIG["updates"]}
    assert entries["github-actions"]["ignore"] == [
        {"dependency-name": "anthropics/claude-code-action"},
        {"dependency-name": "bridgecrewio/checkov-action"},
        {"dependency-name": "aquasecurity/trivy-action"},
    ]
    # Omitting versions/update-types ignores every version and update type.
    assert entries["pre-commit"]["ignore"] == [
        {"dependency-name": "https://github.com/agenticcodingops/auto-code-scanning"},
    ]
