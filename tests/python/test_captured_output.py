"""Captured tool output must survive decoding and forwarding on Windows."""
import ast
import io
import json
import sys
from pathlib import Path

import pytest

import scan
import setup_scanning


@pytest.mark.parametrize("runner", [scan, setup_scanning], ids=["scan", "setup-scanning"])
@pytest.mark.parametrize("exit_code", [0, 7])
def test_run_cmd_decodes_utf8_and_replaces_invalid_bytes(runner, exit_code):
    # Write raw bytes so the child's console/locale encoding cannot change the test.
    command = [sys.executable, "-c",
               "import sys; "
               "sys.stdout.buffer.write(bytes.fromhex('e697a5e69cace8aa9e20ff')); "
               "sys.stderr.buffer.write(bytes.fromhex('e8ada6e5918a20ff')); "
               f"sys.exit({exit_code})"]
    kwargs = {"check": True} if runner is setup_scanning else {}

    assert runner.run_cmd(command, **kwargs) == (exit_code, "日本語 �", "警告 �")


@pytest.mark.parametrize("tool_exit", [0, 2])
def test_scan_forwards_non_ascii_output_on_narrow_streams(monkeypatch, tmp_path, tool_exit):
    text = "日本語 �"
    report = {"Results": [{"Target": "main.tf", "Misconfigurations": [
        {"ID": "AVD-TEST-0001", "Severity": "HIGH", "Title": text}]}]}
    monkeypatch.setattr(scan, "run_cmd", lambda *args, **kwargs:
                        (tool_exit, json.dumps(report), text))
    monkeypatch.setattr(sys, "argv", ["scan.py", str(tmp_path), "--tools", "trivy",
                                     "--output-file", str(tmp_path / "report.json")])
    stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    stderr = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)

    with pytest.raises(SystemExit) as exc:
        scan.main()

    assert exc.value.code == (2 if tool_exit else 1)
    for stream in (stdout, stderr):
        assert stream.errors == "replace"
        stream.flush()
    forwarded = stderr if tool_exit else stdout
    assert text.encode("cp1252", errors="replace") in forwarded.buffer.getvalue()


def test_setup_forwards_non_ascii_output_on_narrow_streams(monkeypatch, tmp_path):
    text = "日本語 �"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["setup-scanning.py", "--cloud-provider", "aws"])
    monkeypatch.setattr(setup_scanning, "tools_installed", 0)
    monkeypatch.setattr(setup_scanning, "tools_failed", 0)
    monkeypatch.setattr(setup_scanning, "command_exists", lambda cmd: False)
    monkeypatch.setattr(setup_scanning, "run_cmd", lambda *args, **kwargs: (1, "", text))

    def install_tools(*args, **kwargs):
        setup_scanning.install_pip_tool("checkov", "Checkov")
        setup_scanning.install_pinned_binary("trivy", "Trivy")

    monkeypatch.setattr(setup_scanning, "install_tools", install_tools)
    for name in ("copy_configs", "copy_tier_template", "init_tflint", "install_hooks",
                 "verify_installation"):
        monkeypatch.setattr(setup_scanning, name, lambda *args, **kwargs: None)
    stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    stderr = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)

    with pytest.raises(SystemExit) as exc:
        setup_scanning.main()

    assert exc.value.code == 1
    for stream in (stdout, stderr):
        assert stream.errors == "replace"
        stream.flush()
        assert text.encode("cp1252", errors="replace") in stream.buffer.getvalue()


def test_text_subprocess_calls_have_explicit_encoding():
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    for name in ("scan.py", "setup-scanning.py", "setup-scan-fix.py"):
        tree = ast.parse((scripts / name).read_text(encoding="utf-8"))
        calls = [node for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                 and isinstance(node.func.value, ast.Name)
                 and node.func.value.id == "subprocess"
                 and node.func.attr in {"run", "check_output", "Popen"}]
        text_calls = [call for call in calls if any(
            keyword.arg in {"text", "universal_newlines"}
            and isinstance(keyword.value, ast.Constant) and keyword.value.value is True
            for keyword in call.keywords)]
        assert text_calls, f"{name}: expected subprocess calls that decode text"
        for call in text_calls:
            keywords = {keyword.arg: keyword.value for keyword in call.keywords}
            assert "encoding" in keywords, f"{name}:{call.lineno} lacks encoding="
            assert isinstance(keywords["encoding"], ast.Constant)
            assert keywords["encoding"].value == "utf-8", f"{name}:{call.lineno} lacks UTF-8"
            assert isinstance(keywords.get("errors"), ast.Constant)
            assert keywords["errors"].value == "replace", f"{name}:{call.lineno} lacks replacement"
