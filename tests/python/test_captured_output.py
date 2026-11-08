"""Captured tool output must survive decoding and forwarding on Windows."""
import ast
import io
import json
import re
import subprocess
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
    repo_root = Path(__file__).resolve().parents[2]
    scripts = repo_root / "scripts"
    targets: list[tuple[str, ast.AST]] = []
    for name in ("scan.py", "setup-scanning.py", "setup-scan-fix.py", "scan_policy.py"):
        targets.append((name, ast.parse((scripts / name).read_text(encoding="utf-8"))))

    hooks_lib = repo_root / "hooks" / "lib"
    for sh_path in hooks_lib.glob("*.sh"):
        content = sh_path.read_text(encoding="utf-8")
        for tag, code in re.findall(r"<<'?(PY[A-Z]*)'?.*?\n(.*?)\n\1", content, re.DOTALL):
            targets.append((f"{sh_path.name}:{tag}", ast.parse(code)))

    for label, tree in targets:
        calls = [node for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                 and isinstance(node.func.value, ast.Name)
                 and node.func.value.id == "subprocess"
                 and node.func.attr in {"run", "check_output", "Popen"}]
        text_calls = [call for call in calls if any(
            keyword.arg in {"text", "universal_newlines"}
            and isinstance(keyword.value, ast.Constant) and keyword.value.value is True
            for keyword in call.keywords)]
        if not text_calls:
            continue
        for call in text_calls:
            keywords = {keyword.arg: keyword.value for keyword in call.keywords}
            assert "encoding" in keywords, f"{label}:{call.lineno} lacks encoding="
            assert isinstance(keywords["encoding"], ast.Constant)
            assert keywords["encoding"].value == "utf-8", f"{label}:{call.lineno} lacks UTF-8"
            assert isinstance(keywords.get("errors"), ast.Constant)
            assert keywords["errors"].value == "replace", f"{label}:{call.lineno} lacks replacement"


def test_hook_assert_external_path_non_ascii_checkout(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    common = (repo_root / "hooks" / "lib" / "common.sh").read_text(encoding="utf-8")
    m = re.search(r"<<'PYEXTERNAL'.*?\n(.*?)\nPYEXTERNAL", common, re.DOTALL)
    assert m, "PYEXTERNAL block not found in common.sh"
    py_code = m.group(1)

    checkout = tmp_path / "checkout-日本語-テスト"
    checkout.mkdir()
    subprocess.run(["git", "init"], cwd=checkout, check=True, capture_output=True)
    external = tmp_path / "external-tool.sh"
    external.write_text("tool")

    res = subprocess.run([sys.executable, "-I", "-", str(external)],
                         input=py_code, cwd=checkout, text=True, capture_output=True)
    assert res.returncode == 0, res.stderr

    inside = checkout / "inside-tool.sh"
    inside.write_text("tool")
    res_inside = subprocess.run([sys.executable, "-I", "-", str(inside)],
                                input=py_code, cwd=checkout, text=True, capture_output=True)
    assert res_inside.returncode != 0
    assert "Trusted path must be outside" in res_inside.stderr
