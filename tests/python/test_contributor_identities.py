"""Tests for .github/contributor-identities/check.py.

Each test builds a throwaway repository with real commits and runs the shipped
script against it. Most tests use the shipped deny list; the error cases write
their own.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LISTS = REPO_ROOT / ".github" / "contributor-identities"
SCRIPT = LISTS / "check.py"
DENY_LIST = "ai-assistants.txt"

MEMBER = ("Dev", "dev@example.org")

# Identities that must pass: people and the bots K1 allows.
ALLOWED = [
    ("Unlisted Person", "someone@unrelated.example"),
    ("Jules Verne", "jules@example.org"),
    ("Devin Smith", "devin.smith@example.org"),
    ("coderabbitai[bot]", "136622811+coderabbitai[bot]@users.noreply.github.com"),
    ("semgrep-app[bot]", "63493438+semgrep-app[bot]@users.noreply.github.com"),
    ("Semgrep", "support@semgrep.com"),
    ("sonarqubecloud[bot]", "39514782+sonarqubecloud[bot]@users.noreply.github.com"),
    ("dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com"),
    ("agenticcodingops-release[bot]",
     "337425099+agenticcodingops-release[bot]@users.noreply.github.com"),
    ("github-actions[bot]", "41898282+github-actions[bot]@users.noreply.github.com"),
    ("auto-code-scanning-autofix[bot]", "autofix@auto-code-scanning.invalid"),
    ("GitHub", "noreply@github.com"),
]

# Identities that must fail, by name, by address, or both.
ASSISTANTS = [
    ("Claude", "noreply@anthropic.com"),
    ("claude[bot]", "209825114+claude[bot]@users.noreply.github.com"),
    ("Claude", "dev@example.org"),
    ("Dev", "noreply@anthropic.com"),
    ("chatgpt-codex-connector[bot]",
     "199175422+chatgpt-codex-connector[bot]@users.noreply.github.com"),
    ("Codex", "codex@example.org"),
    ("Dev", "codex@openai.com"),
    ("Copilot", "198982749+Copilot@users.noreply.github.com"),
    ("Cursor Agent", "cursoragent@cursor.com"),
    ("gemini-code-assist[bot]", "176961590+gemini-code-assist[bot]@users.noreply.github.com"),
    ("Grok", "grok@example.org"),
    ("Jules", "jules@example.org"),
    ("google-labs-jules[bot]", "161369871+google-labs-jules[bot]@users.noreply.github.com"),
    ("devin-ai-integration[bot]",
     "158243242+devin-ai-integration[bot]@users.noreply.github.com"),
    ("Kiro", "kiro@example.org"),
    ("aider (gpt-4o)", "noreply@aider.chat"),
    ("Antigravity", "agent@example.org"),
]

# Co-authored-by lines that name only a model.
MODEL_COAUTHORS = [
    "Co-authored-by: Opus 5.5 <dev@example.org>",
    "Co-authored-by: Sonnet <bot@example.org>",
    "Co-authored-by: Haiku 4 <bot@example.org>",
    "Co-authored-by: Fable <bot@example.org>",
    "Co-authored-by: GPT-5 <bot@example.org>",
    "Co-authored-by: gpt 4.1 <bot@example.org>",
]


def _git(repo, *args, author=MEMBER, committer=MEMBER):
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update({
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": author[0], "GIT_AUTHOR_EMAIL": author[1],
        "GIT_COMMITTER_NAME": committer[0], "GIT_COMMITTER_EMAIL": committer[1],
    })
    return subprocess.run(["git", *args], cwd=repo, env=env, check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "-q")
    _git(path, "commit", "-q", "--allow-empty", "-m", "base")
    return path


def _commit(path, message, **identity):
    _git(path, "commit", "-q", "--allow-empty", "-m", message, **identity)


def _check(path, lists=LISTS, revs=("HEAD^!",)):
    return subprocess.run([sys.executable, "-I", str(SCRIPT), "--lists", str(lists), *revs],
                          cwd=path, capture_output=True, text=True, check=False)


def _id(identity):
    return f"{identity[0]} <{identity[1]}>"


@pytest.mark.parametrize("identity", ALLOWED, ids=_id)
@pytest.mark.parametrize("role", ["author", "committer"])
def test_non_assistant_may_author_or_commit(repo, role, identity):
    _commit(repo, "fix: x", **{role: identity})
    result = _check(repo)
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize("identity", ALLOWED, ids=_id)
def test_non_assistant_may_coauthor(repo, identity):
    _commit(repo, f"fix: x\n\nCo-authored-by: {_id(identity)}")
    result = _check(repo)
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize("identity", ASSISTANTS, ids=_id)
@pytest.mark.parametrize("role", ["author", "committer"])
def test_assistant_author_or_committer_is_reported(repo, role, identity):
    _commit(repo, "fix: x", **{role: identity})
    result = _check(repo)
    assert result.returncode == 1
    assert f"{role} {identity[0]} <{identity[1]}> is an AI assistant" in result.stdout


@pytest.mark.parametrize("identity", ASSISTANTS, ids=_id)
def test_assistant_coauthor_is_reported(repo, identity):
    _commit(repo, f"fix: x\n\nCo-authored-by: {_id(identity)}")
    result = _check(repo)
    assert result.returncode == 1
    assert "co-author is an AI assistant" in result.stdout


@pytest.mark.parametrize("line", MODEL_COAUTHORS)
def test_model_name_coauthor_is_reported(repo, line):
    _commit(repo, f"fix: x\n\n{line}")
    result = _check(repo)
    assert result.returncode == 1
    assert "co-author is an AI assistant" in result.stdout


@pytest.mark.parametrize("line", [
    "co-authored-by: Claude <noreply@anthropic.com>",
    "CO-AUTHORED-BY: Claude <noreply@anthropic.com>",
    "Coauthored-by: Claude <noreply@anthropic.com>",
    "   Co-authored-by: Claude <noreply@anthropic.com>",
    "Co-authored-by: Claude",
    "Co-authored-by: Dev <noreply@ANTHROPIC.com>",
])
def test_coauthor_variants_are_reported(repo, line):
    _commit(repo, f"fix: x\n\n{line}")
    assert _check(repo).returncode == 1


@pytest.mark.parametrize("message", [
    "docs: document the Claude hook and the Codex review",
    "fix: x\n\nThe Copilot and Gemini reviews asked for this; see CLAUDE.md.",
    "fix: x\n\nSigned-off-by: Claude <noreply@anthropic.com>",
    "fix: x\n\nGenerated with an assistant",
    "fix: x\n\nCo-authored-by: Claudette Dupont <claudette@example.org>",
    "fix: x\n\nCo-authored-by: No Address",
])
def test_free_text_and_sign_off_are_not_checked(repo, message):
    """Only identities and Co-authored-by lines are read, never the message text."""
    _commit(repo, message)
    result = _check(repo)
    assert result.returncode == 0, result.stdout


def test_crlf_message_is_read(repo):
    _commit(repo, "fix: x\r\n\r\nCo-authored-by: Claude <noreply@anthropic.com>\r\n")
    assert _check(repo).returncode == 1


def test_range_reports_every_commit(repo):
    _commit(repo, "fix: a", author=("Codex", "codex@example.org"))
    _commit(repo, "fix: b", author=("Claude", "claude@example.org"))
    result = _check(repo, revs=("HEAD~2..HEAD",))
    assert result.returncode == 1
    assert "codex@example.org" in result.stdout and "claude@example.org" in result.stdout


@pytest.mark.parametrize("separator", ["\x1e", "\x1f", "\x1d"])
def test_control_bytes_in_a_message_hide_no_other_commit(repo, separator):
    _commit(repo, "fix: older", author=("Codex", "codex@example.org"))
    _commit(repo, f"fix: newer\n\npayload{separator}tail")
    result = _check(repo, revs=("HEAD~2..HEAD",))
    assert result.returncode == 1, result.stderr
    assert "author Codex <codex@example.org>" in result.stdout


def test_missing_deny_list_is_an_error(repo, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = _check(repo, lists=empty)
    assert result.returncode == 2
    assert DENY_LIST in result.stderr


def test_deny_list_without_patterns_is_an_error(repo, tmp_path):
    lists = tmp_path / "lists"
    lists.mkdir()
    (lists / DENY_LIST).write_text("# only a comment\n\n", encoding="utf-8")
    assert _check(repo, lists=lists).returncode == 2


def test_invalid_pattern_is_an_error(repo, tmp_path):
    lists = tmp_path / "lists"
    lists.mkdir()
    (lists / DENY_LIST).write_text("\\bclaude\\b\n(unclosed\n", encoding="utf-8")
    result = _check(repo, lists=lists)
    assert result.returncode == 2
    assert ":2:" in result.stderr


def test_bad_revision_is_an_error(repo):
    assert _check(repo, revs=("no-such-revision",)).returncode == 2


def test_shipped_deny_list_names_every_assistant_in_the_policy():
    """Each assistant and model family the policy names is matched by some pattern."""
    lines = [line.strip() for line in
             (LISTS / DENY_LIST).read_text(encoding="utf-8").splitlines()]
    patterns = [re.compile(line, re.IGNORECASE)
                for line in lines if line and not line.startswith("#")]
    for name in ("Claude", "Anthropic", "Codex", "OpenAI", "ChatGPT", "Copilot", "Cursor",
                 "Gemini", "Grok", "Antigravity", "Jules", "Kiro", "Devin", "Aider",
                 "Opus", "Sonnet", "Haiku", "Fable", "GPT-5"):
        assert any(pattern.search(name) for pattern in patterns), name
