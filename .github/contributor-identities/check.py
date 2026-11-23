#!/usr/bin/env python3
"""Report commits whose author, committer or co-author is not an approved identity.

GitHub lists every author and every co-author (a ``Co-authored-by`` line) of a
commit on the default branch as a contributor. The maintainer's rule is that
only organisation members, the bots this repository's own workflows use, and
the tools the maintainer approves may appear there. This script reports any
identity missing from the approved lists below, an AI assistant's for example.
It changes nothing. A finding exits 1, which fails the Contributor identities
check that the main ruleset requires, so it blocks the merge.

Lists, one address per line, ``#`` comments allowed, matched exactly and
case-insensitively:

* ``allowed-identities.txt``: may author, commit or co-author.
* ``allowed-coauthors.txt``: may co-author only.

Usage: check.py [--lists DIR] REV [REV ...]
REV arguments go to ``git log``, for example ``BASE..HEAD`` or ``SHA^!``.
Exit status: 0 clean, 1 findings, 2 a missing list or a git error.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COAUTHOR = re.compile(r"^\s*co-?authored-?by\s*:(.*)$", re.IGNORECASE)
ADDRESS = re.compile(r"<([^<>]*)>\s*$")


def load(path):
    """Return the lower-cased addresses in a list file, or None if it is missing."""
    if not path.is_file():
        return None
    addresses = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            addresses.add(line.lower())
    return addresses


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                          check=True).stdout.decode("utf-8", "replace")


def commits(revs, cwd=None):
    """Yield (sha, author email, committer email, message) for each commit.

    Each commit is read on its own, so no byte in a message can be mistaken for
    a separator between commits. The two addresses are split on NUL, which an
    address cannot contain.
    """
    for sha in _git(["rev-list", *revs, "--"], cwd).split():
        author, committer = _git(
            ["show", "-s", "--no-show-signature", "--format=%ae%x00%ce", sha],
            cwd).rstrip("\n").split("\0", 1)
        message = _git(["show", "-s", "--no-show-signature", "--format=%B", sha], cwd)
        yield sha, author, committer, message


def findings(revs, identities, coauthors, cwd=None):
    """Yield one line per identity that is not approved."""
    may_coauthor = identities | coauthors
    for sha, author, committer, message in commits(revs, cwd):
        short = sha[:7]
        if author.strip().lower() not in identities:
            yield f"{short}: author {author} is not an approved identity"
        if committer.strip().lower() not in identities:
            yield f"{short}: committer {committer} is not an approved identity"
        for line in message.replace("\r", "").splitlines():
            match = COAUTHOR.match(line)
            if not match:
                continue
            address = ADDRESS.search(match.group(1))
            if not address or address.group(1).strip().lower() not in may_coauthor:
                yield f"{short}: co-author is not approved: {line.strip()}"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--lists", type=Path, default=HERE,
                        help="directory holding the two list files")
    parser.add_argument("revs", nargs="+", help="revisions passed to git log")
    args = parser.parse_args(argv)

    identities = load(args.lists / "allowed-identities.txt")
    coauthors = load(args.lists / "allowed-coauthors.txt")
    for name, loaded in (("allowed-identities.txt", identities),
                         ("allowed-coauthors.txt", coauthors)):
        if loaded is None:
            print(f"error: {args.lists / name} is missing", file=sys.stderr)
            return 2
    try:
        found = list(findings(args.revs, identities, coauthors))
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
    print("Every author, committer and co-author is approved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
