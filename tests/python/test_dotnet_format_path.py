"""dotnet-format path test — the solution/working-dir must come from CONFIG, never
hardcoded (the generic fix for the PR #145 api/ path bug).

Two checks:
  1. Static: the dotnet-format/dotnet-build hooks reference the config keys and
     contain no hardcoded solution name or consumer path (e.g. 'TrackRoutinely', 'api/').
  2. Functional: the shared config reader resolves build.solution/working_dir from a
     consumer scan-config.yaml (proving the path is config-driven end to end).
"""
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HOOKS = REPO_ROOT / "hooks"

HARDCODED_SMELLS = ["TrackRoutinely", "/api/", '"api"', "api/App", "MyApp.slnx"]


def _working_bash():
    """Return a bash that actually runs (skip the WSL stub on Windows)."""
    candidates = [
        shutil.which("bash"),
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        "/bin/bash",
    ]
    for c in candidates:
        if not c or not os.path.exists(c) and shutil.which(c) is None:
            continue
        try:
            r = subprocess.run([c, "-c", "echo ok"], capture_output=True, text=True, timeout=15)
            if r.returncode == 0 and "ok" in r.stdout:
                return c
        except Exception:
            continue
    return None


@pytest.mark.parametrize("hook", ["dotnet-format.sh", "dotnet-format.ps1", "dotnet-build.sh", "dotnet-build.ps1"])
def test_hook_reads_config_not_hardcoded(hook):
    text = (HOOKS / hook).read_text(encoding="utf-8")
    # References the per-project build settings from scan-config.yaml.
    assert "languages.csharp.build.working_dir" in text, f"{hook} should read working_dir from config"
    assert "languages.csharp.build.solution" in text, f"{hook} should read solution from config"
    # No consumer-specific hardcoded solution/path.
    for smell in HARDCODED_SMELLS:
        assert smell not in text, f"{hook} contains a hardcoded path/solution: {smell!r}"


def test_solution_resolved_from_config(tmp_path):
    bash = _working_bash()
    if not bash:
        pytest.skip("no working bash (WSL stub or absent)")
    cfg = tmp_path / "scan-config.yaml"
    cfg.write_text(textwrap.dedent("""\
        schema_version: "1.0"
        languages:
          csharp:
            enabled: true
            build:
              solution: "myproj/My.slnx"
              working_dir: "myproj"
            tools: {}
    """), encoding="utf-8")

    common = (HOOKS / "lib" / "common.sh").as_posix()
    script = (
        f'export SCAN_CONFIG_FILE="{cfg.as_posix()}"; '
        f'source "{common}"; '
        f'echo "sol=$(read_scan_config languages.csharp.build.solution NONE)"; '
        f'echo "wd=$(read_scan_config languages.csharp.build.working_dir NONE)"'
    )
    proc = subprocess.run([bash, "-c", script], capture_output=True, text=True)
    out = proc.stdout
    assert "sol=myproj/My.slnx" in out, out + proc.stderr
    assert "wd=myproj" in out, out + proc.stderr
