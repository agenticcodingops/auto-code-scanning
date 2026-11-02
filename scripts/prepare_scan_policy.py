"""Materialize scanner configuration from a trusted Git commit before scanning."""
import os
from pathlib import Path
import re
import subprocess

POLICY_NAMES = {"scan-config.yaml", "trivy.yaml", "trivy.yml", ".trivyignore", ".trivyignore.yaml",
                ".checkov.yaml", ".checkov.yml", ".tflint.hcl", ".snyk", ".semgrepignore",
                ".semgrepignore2", ".gitignore", ".gitleaks.toml", "trivy-secret.yaml", "trivy-secret.yml"}


def git(*arguments):
    return subprocess.run(["git", *arguments], check=True, capture_output=True).stdout


def prepare(base, root="."):
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", base):
        raise ValueError("A full trusted commit SHA is required")
    root = Path(root).resolve()
    git("cat-file", "-e", base + "^{commit}")
    trusted = {p.decode("utf-8") for p in git("ls-tree", "-r", "-z", "--name-only", base, "--").split(b"\0") if p}
    current = {p.decode("utf-8") for p in git("ls-files", "-z", "--").split(b"\0") if p}
    for name in sorted(current | trusted):
        if Path(name).name not in POLICY_NAMES:
            continue
        target = root / name
        # Parent symlinks must not redirect writes beyond the scanned checkout.
        for parent in target.parents:
            if parent == root:
                break
            if parent.is_symlink():
                raise ValueError("Scanner policy parent must not be a symlink")
        if target.is_symlink():
            target.unlink()
        if name in trusted:
            mode = git("ls-tree", base, "--", name).split(b" ", 1)[0]
            if mode != b"100644" and mode != b"100755":
                raise ValueError("Scanner policy must be a regular file")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(git("show", f"{base}:{name}", "--"))
        elif target.exists():
            target.unlink()


if __name__ == "__main__":
    prepare(os.environ["TRUSTED_POLICY_SHA"])
