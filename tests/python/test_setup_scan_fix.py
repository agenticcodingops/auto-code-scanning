"""Tests for the cross-platform setup-scan-fix scripts."""

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


def test_powershell_setup_vendors_schemas(repo_root: Path):
    """The PowerShell twin also copies the schema directory."""
    powershell_setup = (repo_root / "scripts/setup-scan-fix.ps1").read_text()

    assert 'Join-Path $PlatformRoot "schemas"' in powershell_setup
