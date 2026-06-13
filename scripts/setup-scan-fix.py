#!/usr/bin/env python3
"""setup-scan-fix.py — ONE-command onboarding for the scan->fix platform (cross-platform twin).

Idempotent and re-runnable. Writes scan-config.yaml from a tier template, installs the chosen
local runner (Lefthook default | pre-commit), copies the Claude bundle + thin caller workflows,
creates the ai-autofix / needs-human-review labels, VERIFIES (never creates) required secrets,
and runs verify-scanning. See setup-scan-fix.ps1 for the PowerShell equivalent.

Example:
  python scripts/setup-scan-fix.py --languages csharp,typescript --tier standard --enable-fix-loop
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PLATFORM_ROOT = Path(__file__).resolve().parent.parent


def info(m): print(f"[INFO] {m}")
def ok(m): print(f"[OK]   {m}")
def warn(m): print(f"[WARN] {m}")
def step(m): print(f"\n=== {m} ===")


def have(cmd) -> bool:
    return shutil.which(cmd) is not None


def copy(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--languages", default="")
    ap.add_argument("--tier", default="standard", choices=["starter", "standard", "strict"])
    ap.add_argument("--hooks-runner", default="lefthook", choices=["lefthook", "pre-commit"])
    ap.add_argument("--enable-fix-loop", action="store_true")
    ap.add_argument("--cloud-provider", default="", choices=["", "aws", "azure", "gcp"])
    ap.add_argument("--repo-path", default=str(Path.cwd()))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv[1:])

    repo = Path(args.repo_path).resolve()
    langs = args.languages
    if args.cloud_provider and "terraform" not in langs:
        langs = ",".join([p for p in [langs, "terraform"] if p])

    print(f"\nOnboarding scan->fix platform into: {repo}")
    print(f"  tier={args.tier} runner={args.hooks_runner} languages={langs} fixLoop={args.enable_fix_loop}\n")

    # 1) scan-config.yaml
    step(f"scan-config.yaml ({args.tier} tier)")
    render = [sys.executable, str(PLATFORM_ROOT / "scripts/render-scan-config.py"),
              "--tier", args.tier, "--languages", langs,
              "--templates-dir", str(PLATFORM_ROOT / "templates/scan-config"),
              "--out", str(repo / "scan-config.yaml")]
    if args.enable_fix_loop:
        render.append("--enable-fix-loop")
    if args.force:
        render.append("--force")
    subprocess.run(render, check=False)

    # 2) Vendor hooks + scripts
    step("Vendoring shared hooks + scripts")
    if repo != PLATFORM_ROOT:
        shutil.copytree(PLATFORM_ROOT / "hooks", repo / "hooks", dirs_exist_ok=True)
        for s in ("scan-and-fix.ps1", "scan-and-fix.sh", "check-fix-allowlist.py",
                  "validate-scan-config.py", "render-scan-config.py"):
            copy(PLATFORM_ROOT / "scripts" / s, repo / "scripts" / s)
        ok("Copied hooks/ and shared scripts/")
    else:
        info("Running inside the platform repo; hooks/scripts already present")

    # 3) Runner
    step(f"Local runner: {args.hooks_runner}")
    if args.hooks_runner == "lefthook":
        copy(PLATFORM_ROOT / "templates/lefthook/lefthook.yml", repo / "lefthook.yml")
        if have("lefthook"):
            subprocess.run(["lefthook", "install"], cwd=repo, check=False)
            ok("lefthook installed")
        else:
            warn("lefthook not on PATH. Install it (choco/go/brew), then 'lefthook install'")
    else:
        pc_src = PLATFORM_ROOT / f"templates/{args.tier}/pre-commit-config.yaml"
        pc_dst = repo / ".pre-commit-config.yaml"
        if pc_src.exists() and not pc_dst.exists():
            copy(pc_src, pc_dst)
        if have("pre-commit"):
            subprocess.run(["pre-commit", "install"], cwd=repo, check=False)
            subprocess.run(["pre-commit", "install", "--hook-type", "pre-push"], cwd=repo, check=False)
            ok("pre-commit hooks installed")
        else:
            warn("pre-commit not on PATH. 'pip install pre-commit', then 'pre-commit install'")

    # 4) Claude bundle
    step("Claude Code in-session bundle (.claude/)")
    settings = repo / ".claude/settings.json"
    if not settings.exists():
        copy(PLATFORM_ROOT / "templates/claude/settings.json", settings)
    else:
        info(".claude/settings.json exists; leaving it")
    for h in ("posttooluse-scan.ps1", "posttooluse-scan.sh", "stop-scan.ps1", "stop-scan.sh"):
        copy(PLATFORM_ROOT / "templates/claude/hooks" / h, repo / ".claude/hooks" / h)
    ok("Claude bundle copied")

    # 5) Caller workflows
    step("CI caller workflows (.github/workflows/)")
    copy(PLATFORM_ROOT / "templates/workflows/code-security-scan.yml", repo / ".github/workflows/code-security-scan.yml")
    if "terraform" in langs:
        copy(PLATFORM_ROOT / "templates/workflows/terraform-scan.yml", repo / ".github/workflows/terraform-scan.yml")
    if args.enable_fix_loop:
        copy(PLATFORM_ROOT / "templates/fix-loop/autonomous-fix.yml", repo / ".github/workflows/autonomous-fix.yml")
    ok("Caller workflows copied (remember to pin @vX.Y.Z)")

    # 6+7) Labels + secret verification
    if args.enable_fix_loop:
        step("Fix-loop: labels + secret verification")
        if have("gh"):
            for name, color, desc in [
                ("ai-autofix", "1D76DB", "Opt this PR into the autonomous fix-loop"),
                ("needs-human-review", "B60205", "Autonomous fix loop stopped; needs a human"),
            ]:
                r = subprocess.run(["gh", "label", "create", name, "--color", color, "--description", desc, "--force"],
                                   cwd=repo, capture_output=True, text=True)
                ok(f"label {name}") if r.returncode == 0 else warn(f"could not create {name}: {r.stderr.strip()}")
            present = []
            r = subprocess.run(["gh", "secret", "list", "--json", "name"], cwd=repo, capture_output=True, text=True)
            if r.returncode == 0:
                try:
                    present = [s["name"] for s in json.loads(r.stdout)]
                except Exception:
                    present = []
            for need in ("AUTOFIX_TOKEN", "ANTHROPIC_API_KEY"):
                if need in present:
                    ok(f"secret {need} present")
                else:
                    warn(f"secret {need} MISSING — create it (this script never stores secrets):")
                    if need == "AUTOFIX_TOKEN":
                        print("    Fine-grained PAT (Contents RW + Pull-requests RW, THIS repo only):")
                        print("      gh secret set AUTOFIX_TOKEN")
                    else:
                        print("      gh secret set ANTHROPIC_API_KEY   # or CLAUDE_CODE_OAUTH_TOKEN")
        else:
            warn("gh CLI not found — cannot create labels or verify secrets. Install it, then re-run.")

    # 8) Verify
    step("Verify install")
    verify = PLATFORM_ROOT / "scripts/verify-scanning.ps1"
    if have("pwsh") and verify.exists():
        subprocess.run(["pwsh", "-NoProfile", "-File", str(verify)], cwd=repo, check=False)
    else:
        info("verify-scanning.ps1 not run (needs pwsh); review scan-config.yaml manually")

    print("\n=== SETUP COMPLETE ===")
    print("Next: review scan-config.yaml; pin caller workflows to a release tag; test a commit.")
    if args.enable_fix_loop:
        print("Add the 'ai-autofix' label to a PR to opt it into the fix-loop.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
