"""Run each setup script's real secret-check section against a local gh stub."""
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest
import setup_scan_fix

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("implementation", ["py", "ps1"])
@pytest.mark.parametrize("scenario,names", [
    ("api", ["AUTOFIX_TOKEN", "ANTHROPIC_API_KEY"]),
    ("oauth", ["AUTOFIX_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"]),
    ("both", ["AUTOFIX_TOKEN", "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"]),
    ("neither", ["AUTOFIX_TOKEN"]),
    ("missing-token", ["CLAUDE_CODE_OAUTH_TOKEN"]),
    ("empty", []),
    ("failure", []),
    ("old-gh", ["AUTOFIX_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"]),
])
def test_secret_checks_accept_either_model_credential(tmp_path, monkeypatch, capsys, implementation, scenario, names):
    stub = tmp_path / "gh.py"
    stub.write_text(
        'import json, os, sys\n'
        'args = sys.argv[1:]\n'
        'if args[:2] != ["secret", "list"]: sys.exit(0)\n'
        'with open(os.environ["GH_TRACE"], "a") as f: f.write(json.dumps(args)+"\\n")\n'
        'scenario = os.environ["GH_SCENARIO"]\n'
        'if scenario == "failure": sys.exit(1)\n'
        'if scenario == "old-gh" and "--json" in args: sys.exit(1)\n'
        'names = json.loads(os.environ["GH_NAMES"])\n'
        'if "--json" in args: print(json.dumps([{"name": n} for n in names]))\n'
        'else: print("\\n".join(n+"  2026-01-01T00:00:00Z" for n in names))\n', encoding="utf-8")
    trace = tmp_path / "trace.jsonl"
    environment = {**os.environ, "GH_SCENARIO": scenario, "GH_NAMES": json.dumps(names),
                   "GH_TRACE": str(trace), "GH_STUB": str(tmp_path / "gh.ps1"), "STUB_PY": sys.executable}
    if implementation == "py":
        # Execute the whole labelled section from the script, without installation
        # or account access. Only the gh process is redirected to our local stub.
        source = (ROOT / "scripts/setup-scan-fix.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
        check = next(n for n in main.body if isinstance(n, ast.If)
                     and any(isinstance(c, ast.Constant) and c.value == "Fix-loop: labels + secret verification"
                             for c in ast.walk(n)))
        run = subprocess.run
        def stub_run(cmd, **kwargs):
            assert cmd[0] == str(stub)
            return run([sys.executable, *cmd], env=environment, **kwargs)
        monkeypatch.setattr(subprocess, "run", stub_run)
        scope = dict(vars(setup_scan_fix), args=SimpleNamespace(enable_fix_loop=True),
                     tools={"gh": str(stub)}, repo=tmp_path)
        exec(compile(ast.Module(body=[check], type_ignores=[]), str(ROOT / "scripts/setup-scan-fix.py"), "exec"), scope)
        output = capsys.readouterr().out
    else:
        pwsh = shutil.which("pwsh")
        if not pwsh:
            pytest.skip("PowerShell unavailable")
        (tmp_path / "gh.ps1").write_text('& $env:STUB_PY ($PSScriptRoot + "/gh.py") @args\nexit $LASTEXITCODE\n', encoding="utf-8")
        source = (ROOT / "scripts/setup-scan-fix.ps1").read_text(encoding="utf-8")
        start = source.index('if ($EnableFixLoop) {', source.index('# 6) Labels'))
        end = source.index('# 8) Verify', start)
        script = tmp_path / "check.ps1"
        script.write_text(
            '$ErrorActionPreference = "Stop"\n'
            'function Ok { param($m) Write-Output "[OK] $m" }\n'
            'function Warn { param($m) Write-Output "[WARN] $m" }\n'
            'function Info { param($m) Write-Output "[INFO] $m" }\n'
            'function Step { param($m) }\n'
            '$setupTools = @{ gh = $env:GH_STUB }\n'
            '$RepoPath = $PSScriptRoot\n$EnableFixLoop = $true\n'
            + source[start:end] + '\nexit 0\n', encoding="utf-8")
        result = subprocess.run([pwsh, "-NoProfile", "-File", str(script)], env=environment,
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        output = result.stdout + result.stderr
        assert result.returncode == 0, output
    calls = [json.loads(line) for line in trace.read_text().splitlines()]
    assert calls[0] == ["secret", "list", "--json", "name"]
    if scenario in ("old-gh", "failure"):
        assert calls == [["secret", "list", "--json", "name"], ["secret", "list"]]
    else:
        assert len(calls) == 1
    assert "organisation secrets are not listed" in output.lower()
    if scenario == "failure":
        assert "could not verify secrets" in output.lower()
        assert "MISSING" not in output
        return
    assert ("secret AUTOFIX_TOKEN present" in output) == ("AUTOFIX_TOKEN" in names)
    assert ("secret AUTOFIX_TOKEN MISSING" in output) == ("AUTOFIX_TOKEN" not in names)
    model_names = [n for n in names if n != "AUTOFIX_TOKEN"]
    for name in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"):
        assert (f"secret {name} present" in output) == (name in model_names)
    warnings = [line for line in output.splitlines() if "[WARN]" in line and "MISSING" in line
                and ("ANTHROPIC_API_KEY" in line or "CLAUDE_CODE_OAUTH_TOKEN" in line)]
    assert len(warnings) == (0 if model_names else 1)
    if warnings:
        assert "ANTHROPIC_API_KEY" in warnings[0] and "CLAUDE_CODE_OAUTH_TOKEN" in warnings[0]
