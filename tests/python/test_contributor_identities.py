"""Tests for .github/contributor-identities/check.py.

Each test builds a throwaway repository with real commits and runs the shipped
script against it, with list files written for the test.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LISTS = REPO_ROOT / ".github" / "contributor-identities"
SCRIPT = LISTS / "check.py"

MEMBER = "dev@example.org"
BOT = "1+release[bot]@users.noreply.github.com"
REVIEW_TOOL = "2+review[bot]@users.noreply.github.com"


def _git(repo, *args, author=MEMBER, committer=MEMBER):
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update({
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "A", "GIT_AUTHOR_EMAIL": author,
        "GIT_COMMITTER_NAME": "C", "GIT_COMMITTER_EMAIL": committer,
    })
    return subprocess.run(["git", *args], cwd=repo, env=env, check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "-q")
    _git(path, "commit", "-q", "--allow-empty", "-m", "base")
    lists = tmp_path / "lists"
    lists.mkdir()
    (lists / "allowed-identities.txt").write_text(
        f"# members\n{MEMBER.upper()}\n{BOT}\n", encoding="utf-8")
    (lists / "allowed-coauthors.txt").write_text(f"{REVIEW_TOOL}\n", encoding="utf-8")
    return path, lists


def _commit(path, message, **identity):
    _git(path, "commit", "-q", "--allow-empty", "-m", message, **identity)


def _check(path, lists, revs=("HEAD^!",)):
    return subprocess.run([sys.executable, "-I", str(SCRIPT), "--lists", str(lists), *revs],
                          cwd=path, capture_output=True, text=True)


def test_member_commit_passes(repo):
    path, lists = repo
    _commit(path, f"fix: x\n\nCo-authored-by: Dev <{MEMBER}>")
    assert _check(path, lists).returncode == 0


def test_workflow_bot_may_author(repo):
    path, lists = repo
    _commit(path, "chore: release", author=BOT)
    assert _check(path, lists).returncode == 0


@pytest.mark.parametrize("role", ["author", "committer"])
def test_unlisted_author_or_committer_is_reported(repo, role):
    path, lists = repo
    _commit(path, "fix: x", **{role: "agent@tool.example"})
    result = _check(path, lists)
    assert result.returncode == 1
    assert f"{role} agent@tool.example" in result.stdout


def test_review_tool_may_coauthor_but_not_author(repo):
    path, lists = repo
    _commit(path, f"fix: x\n\nCo-authored-by: R <{REVIEW_TOOL}>")
    assert _check(path, lists).returncode == 0
    _commit(path, "fix: y", author=REVIEW_TOOL)
    assert _check(path, lists).returncode == 1


@pytest.mark.parametrize("line", [
    "Co-authored-by: Assistant <noreply@assistant.example>",
    "co-authored-by: Agent <agent@tool.example>",
    "CO-AUTHORED-BY: Agent <agent@tool.example>",
    "Coauthored-by: Agent <agent@tool.example>",
    "   Co-authored-by: Agent <agent@tool.example>",
    "Co-authored-by: No Address",
    f"Co-authored-by: Dev <x{MEMBER}>",
    f"Co-authored-by: Dev <{MEMBER}.evil>",
])
def test_unapproved_coauthor_is_reported(repo, line):
    path, lists = repo
    _commit(path, f"fix: x\n\n{line}")
    result = _check(path, lists)
    assert result.returncode == 1
    assert "co-author is not approved" in result.stdout


def test_crlf_message_is_read(repo):
    path, lists = repo
    _commit(path, f"fix: x\r\n\r\nCo-authored-by: Dev <{MEMBER}>\r\n")
    assert _check(path, lists).returncode == 0


def test_range_reports_every_commit(repo):
    path, lists = repo
    _commit(path, "fix: a", author="one@tool.example")
    _commit(path, "fix: b", author="two@tool.example")
    result = _check(path, lists, ("HEAD~2..HEAD",))
    assert result.returncode == 1
    assert "one@tool.example" in result.stdout and "two@tool.example" in result.stdout


@pytest.mark.parametrize("separator", ["\x1e", "\x1f", "\x1d"])
def test_control_bytes_in_a_message_hide_no_other_commit(repo, separator):
    path, lists = repo
    _commit(path, "fix: older", author="agent@tool.example")
    _commit(path, f"fix: newer\n\npayload{separator}tail")
    result = _check(path, lists, ("HEAD~2..HEAD",))
    assert result.returncode == 1, result.stderr
    assert "author agent@tool.example" in result.stdout


def test_missing_identity_list_is_an_error(repo, tmp_path):
    path, _ = repo
    empty = tmp_path / "empty"
    empty.mkdir()
    assert _check(path, empty).returncode == 2


def test_bad_revision_is_an_error(repo):
    path, lists = repo
    assert _check(path, lists, ("no-such-revision",)).returncode == 2


def test_shipped_lists_cover_the_current_workflows():
    identities = (LISTS / "allowed-identities.txt").read_text(encoding="utf-8").lower()
    for address in (
        "noreply@github.com",
        "340677216+agenticcodingops-orchestrator@users.noreply.github.com",
        "337425099+agenticcodingops-release[bot]@users.noreply.github.com",
        "49699333+dependabot[bot]@users.noreply.github.com",
        "support@semgrep.com",
        "autofix@auto-code-scanning.invalid",
    ):
        assert address in identities.splitlines(), address


def test_shipped_coauthor_list_holds_only_the_allowed_tools():
    lines = [line.strip().lower() for line in
             (LISTS / "allowed-coauthors.txt").read_text(encoding="utf-8").splitlines()]
    addresses = [line for line in lines if line and not line.startswith("#")]
    assert addresses
    assert all(any(tool in a for tool in ("coderabbit", "semgrep", "sonar")) for a in addresses)
