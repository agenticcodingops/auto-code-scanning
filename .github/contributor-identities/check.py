#!/usr/bin/env python3
"""Report commits whose author, committer or co-author is an AI assistant.

GitHub lists every author and every co-author (a ``Co-authored-by`` line) of a
commit on the default branch as a contributor. The maintainer's rule is that an
AI assistant must never appear there: it may not author or commit a commit, and
no ``Co-authored-by`` line may name one. Every other identity passes: people,
code-quality bots, dependency and release bots, and this repository's own
workflow bots.

The assistants are listed in ``ai-assistants.txt``, one case-insensitive Python
regular expression per line, ``#`` comments allowed. Each pattern is searched in
the name and, separately, in the address of the author, the committer and every
co-author. A match on either is a finding.

Only identity fields and ``Co-authored-by`` lines are read. The subject and the
rest of the message are never scanned, and a ``Signed-off-by`` line is not a
contributor credit, so neither is checked.

The script changes nothing. A finding exits 1, which fails the Contributor
identities check that the main ruleset requires, so it blocks the merge.

Usage: check.py [--lists DIR] REV [REV ...]
REV arguments go to ``git log``, for example ``BASE..HEAD`` or ``SHA^!``.
Exit status: 0 clean, 1 findings, 2 a missing, empty or invalid list, or a git
error.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DENY_LIST = "ai-assistants.txt"
COAUTHOR = re.compile(r"^\s*co-?authored-?by\s*:(.*)$", re.IGNORECASE)
NAME_ADDRESS = re.compile(r"^(.*?)\s*<([^<>]*)>\s*$")


class ListError(Exception):
    """The deny list is missing, empty or holds a pattern that does not compile."""


def load(path):
    """Return the compiled patterns in the deny list."""
    if not path.is_file():
        raise ListError(f"{path} is missing")
    patterns = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            patterns.append(re.compile(line, re.IGNORECASE))
        except re.error as exc:
            raise ListError(f"{path}:{number}: invalid pattern {line!r}: {exc}") from exc
    if not patterns:
        raise ListError(f"{path} lists no pattern")
    return patterns


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                          check=True).stdout.decode("utf-8", "replace")


def commits(revs, cwd=None):
    """Yield (sha, author, committer, message) for each commit.

    Author and committer are (name, address) pairs. Each commit is read on its
    own, so no byte in a message can be mistaken for a separator between
    commits. The identity fields are split on NUL, which none can contain.
    """
    for sha in _git(["rev-list", *revs, "--"], cwd).split():
        fields = _git(
            ["show", "-s", "--no-show-signature", "--format=%an%x00%ae%x00%cn%x00%ce", sha],
            cwd).rstrip("\n").split("\0")
        message = _git(["show", "-s", "--no-show-signature", "--format=%B", sha], cwd)
        yield sha, (fields[0], fields[1]), (fields[2], fields[3]), message


def _assistant(patterns, name, address):
    """Return True if any pattern matches the name or the address."""
    for value in (name.strip(), address.strip()):
        if value and any(pattern.search(value) for pattern in patterns):
            return True
    return False


def _coauthor(value):
    """Split a Co-authored-by value into (name, address); the address may be empty."""
    match = NAME_ADDRESS.match(value.strip())
    if match:
        return match.group(1), match.group(2)
    return value, ""


def findings(revs, patterns, cwd=None):
    """Yield one line per identity that names an AI assistant."""
    for sha, author, committer, message in commits(revs, cwd):
        short = sha[:7]
        for role, (name, address) in (("author", author), ("committer", committer)):
            if _assistant(patterns, name, address):
                yield f"{short}: {role} {name} <{address}> is an AI assistant"
        for line in message.replace("\r", "").splitlines():
            match = COAUTHOR.match(line)
            if match and _assistant(patterns, *_coauthor(match.group(1))):
                yield f"{short}: co-author is an AI assistant: {line.strip()}"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--lists", type=Path, default=HERE,
                        help=f"directory holding {DENY_LIST}")
    parser.add_argument("revs", nargs="+", help="revisions passed to git log")
    args = parser.parse_args(argv)

    try:
        patterns = load(args.lists / DENY_LIST)
    except ListError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        found = list(findings(args.revs, patterns))
    except subprocess.CalledProcessError as exc:
        print(f"error: git failed: {exc.stderr.decode('utf-8', 'replace').strip()}",
              file=sys.stderr)
        return 2
    for line in found:
        print(line)
    if found:
        print(f"{len(found)} identity finding(s). See CONTRIBUTING.md, "
              "\"Commit identities\".", file=sys.stderr)
        return 1
    print("No author, committer or co-author is an AI assistant.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
