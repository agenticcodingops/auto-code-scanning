#!/usr/bin/env python3
"""check-fix-allowlist.py — enforce the fix_loop path gate (allowlist, not denylist).

The autonomous fix-loop may only touch files that BOTH:
  1. start with one of fix_loop.allowlist_paths (an inclusive allowlist), AND
  2. do NOT contain any fix_loop.gated_paths substring (case-insensitive denylist
     for security-sensitive areas — fail-closed even inside an allowlisted dir).

Used by autonomous-fix.yml (analyze + apply jobs, defense in depth) and by tests.

Inputs:
  - scan-config.yaml resolved from --config or cwd (fix_loop.allowlist_paths / gated_paths)
  - changed files: positional args, or one-per-line on stdin

Exit codes:
  0 = every file is allowed
  1 = at least one file is gated (prints "GATED: <reason>")
  2 = config missing/unreadable (treated as gated → fail closed)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _load_fix_loop(config_path: Path):
    try:
        import yaml
    except ImportError:
        print("GATED: PyYAML not available to read fix_loop config (fail closed)")
        sys.exit(2)
    if not config_path.is_file():
        print(f"GATED: {config_path} not found (fail closed)")
        sys.exit(2)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    fix_loop = data.get("fix_loop") or {}
    allow = [str(p) for p in (fix_loop.get("allowlist_paths") or [])]
    gated = [str(p).lower() for p in (fix_loop.get("gated_paths") or [])]
    return allow, gated


def _norm(path: str) -> str:
    p = path.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def check(files, allow, gated):
    """Return (ok: bool, reason: str)."""
    for raw in files:
        f = _norm(raw)
        if not f:
            continue
        if not any(f.startswith(_norm(a)) for a in allow):
            return False, f"non-fixable path (outside allowlist): {f}"
        low = f.lower()
        for g in gated:
            if g and g in low:
                return False, f"security-sensitive path (gated): {f}"
    return True, ""


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", help="changed files (or pass on stdin, one per line)")
    ap.add_argument("--config", default="scan-config.yaml")
    args = ap.parse_args(argv[1:])

    files = list(args.files)
    if not files and not sys.stdin.isatty():
        files = [line for line in sys.stdin.read().splitlines() if line.strip()]

    allow, gated = _load_fix_loop(Path(args.config))
    if not allow:
        print("GATED: fix_loop.allowlist_paths is empty (fail closed)")
        return 1

    ok, reason = check(files, allow, gated)
    if ok:
        print(f"OK: all {len(files)} changed file(s) within allowlist and clear of gated paths")
        return 0
    print(f"GATED: {reason}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
