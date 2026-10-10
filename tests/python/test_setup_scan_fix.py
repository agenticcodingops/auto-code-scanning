"""Tests for the cross-platform setup-scan-fix scripts."""

import os
import subprocess
import sys
from pathlib import Path

import setup_scan_fix


def test_python_setup_vendors_schemas(tmp_path: Path, monkeypatch):
    """The Python setup copies every schema beside the copied validator."""
    monkeypatch.setattr(setup_scan_fix, "have", lambda _command: False)
    monkeypatch.setattr(setup_scan_fix.subprocess, "run", lambda *args, **kwargs: None)

    assert setup_scan_fix.main(["setup-scan-fix.py", "--repo-path", str(tmp_path)]) == 0

    source_names = {path.name for path in (setup_scan_fix.PLATFORM_ROOT / "schemas").iterdir()}
    copied_names = {path.name for path in (tmp_path / "schemas").iterdir()}
    assert copied_names == source_names
    assert (tmp_path / "scripts/validate-scan-config.py").is_file()


def test_copied_validator_uses_vendored_schema(tmp_path: Path, repo_root: Path):
    """The copied validator finds its schema and enforces it in strict mode."""
    setup = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts/setup-scan-fix.py"),
            "--repo-path",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert setup.returncode == 0, setup.stdout + setup.stderr

    validator = tmp_path / "scripts/validate-scan-config.py"
    environment = {**os.environ, "STRICT": "1"}
    valid = subprocess.run(
        [sys.executable, str(validator), str(tmp_path / "scan-config.yaml")],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert valid.returncode == 0, valid.stdout + valid.stderr

    invalid_config = tmp_path / "invalid-scan-config.yaml"
    invalid_config.write_text('schema_version: "1.0"\nlanguages: []\n', encoding="utf-8")
    invalid = subprocess.run(
        [sys.executable, str(validator), str(invalid_config)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert invalid.returncode == 1, invalid.stdout + invalid.stderr


def test_powershell_setup_vendors_schemas(repo_root: Path):
    """The PowerShell twin also copies the schema directory."""
    powershell_setup = (repo_root / "scripts/setup-scan-fix.ps1").read_text()

    assert 'Join-Path $PlatformRoot "schemas"' in powershell_setup
