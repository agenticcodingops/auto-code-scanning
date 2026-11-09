"""Captured tool output must survive decoding and forwarding on Windows."""
import ast
import io
import json
import os
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


ROOT = Path(__file__).resolve().parents[2]


def python_heredocs(path):
    # Hook Python delimiters start with PY. Ignore JSON heredocs and here-strings.
    pattern = r"(?m)^[^\n]*<<(?P<tabs>-?)[ \t]*['\"]?(?P<tag>PY\w*)['\"]?[^\n]*\n(?P<body>.*?)(?=^\t*(?P=tag)[ \t]*$)"
    for match in re.finditer(pattern, path.read_text(encoding="utf-8"), re.DOTALL):
        body = match["body"]
        if match["tabs"]:
            body = "\n".join(line.lstrip("\t") for line in body.splitlines())
        yield match["tag"], body


def text_capture_sources():
    for folder in ("scripts", "hooks"):
        for path in sorted((ROOT / folder).rglob("*.py")):
            yield path.relative_to(ROOT).as_posix(), path.read_text(encoding="utf-8")
    for path in sorted((ROOT / "hooks").rglob("*.sh")):
        for tag, body in python_heredocs(path):
            yield f"{path.relative_to(ROOT).as_posix()}:{tag}", body


@pytest.mark.parametrize("name,source", [
    pytest.param(name, source, id=name) for name, source in text_capture_sources()])
def test_text_subprocess_calls_have_explicit_encoding(name, source):
    tree = ast.parse(source, filename=name)
    calls = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and isinstance(node.func.value, ast.Name)
             and node.func.value.id == "subprocess"
             and node.func.attr in {"run", "check_output", "Popen"}]
    text_calls = [call for call in calls if any(
        keyword.arg in {"text", "universal_newlines"}
        and isinstance(keyword.value, ast.Constant) and keyword.value.value is True
        for keyword in call.keywords)]
    if name == "hooks/lib/common.sh:PYEXTERNAL":
        # The trusted-path boundary must see Git's exact root bytes; text mode
        # (or a strip) can name a different directory.
        assert calls and not text_calls, f"{name}: the Git root must be captured as bytes"
        return
    if name in {"scripts/scan.py", "scripts/setup-scanning.py", "scripts/setup-scan-fix.py",
                "scripts/scan_policy.py"}:
        assert text_calls, f"{name}: expected subprocess calls that decode text"
    for call in text_calls:
        keywords = {keyword.arg: keyword.value for keyword in call.keywords}
        captures = call.func.attr == "check_output" or any(
            # A variable flag can enable capture too (setup's run_cmd uses one).
            (key == "capture_output" and not (isinstance(value, ast.Constant) and not value.value))
            or (key in {"stdout", "stderr"} and isinstance(value, ast.Attribute)
                and isinstance(value.value, ast.Name) and value.value.id == "subprocess"
                and value.attr == "PIPE")
            for key, value in keywords.items())
        if not captures:
            continue
        assert "encoding" in keywords, f"{name}:{call.lineno} lacks encoding="
        assert isinstance(keywords["encoding"], ast.Constant)
        assert keywords["encoding"].value == "utf-8", f"{name}:{call.lineno} lacks UTF-8"
        assert isinstance(keywords.get("errors"), ast.Constant)
        assert keywords["errors"].value == "replace", f"{name}:{call.lineno} lacks replace errors"


def external_path_check(tmp_path, target, invalid_output=False):
    bodies = dict(python_heredocs(ROOT / "hooks/lib/common.sh"))
    # Force a narrow locale even on UTF-8 hosts, without mocking Git's real output:
    # with -X utf8=0, subprocess's default text encoding comes from locale.getencoding().
    prelude = "import locale; locale.getencoding = lambda: 'ascii'\n"
    if invalid_output:
        # Exercise the real subprocess decoder with a malformed root, not a raised mock error.
        prelude += ("import subprocess, sys\n"
                    "original = subprocess.check_output\n"
                    "subprocess.check_output = lambda *args, **kwargs: original(\n"
                    "    [sys.executable, '-c', \"import sys; sys.stdout.buffer.write(bytes.fromhex('2f6261642dff0a'))\"], **kwargs)\n")
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("SCAN_") and not key.startswith("GIT_")}
    return subprocess.run([sys.executable, "-I", "-X", "utf8=0", "-c",
                           prelude + bodies["PYEXTERNAL"], str(target)],
                          cwd=tmp_path, env=environment, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


@pytest.mark.parametrize("inside", [True, False], ids=["inside", "outside"])
def test_hook_path_check_non_ascii_checkout(tmp_path, inside):
    checkout = tmp_path / "checkout-日本語-é"
    try:
        checkout.mkdir()
    except (OSError, UnicodeError) as exc:
        pytest.skip(f"filesystem cannot create a non-ASCII checkout: {exc}")
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    nested = checkout / "nested"
    nested.mkdir()
    target = (checkout if inside else tmp_path) / "trusted-config"
    target.write_text("fixture", encoding="utf-8")

    result = external_path_check(nested, target)

    assert result.returncode == (1 if inside else 0), result.stderr
    assert "Traceback" not in result.stderr
    if inside:
        assert "Trusted path must be outside" in result.stderr


@pytest.mark.parametrize("inside", [True, False], ids=["inside", "outside"])
def test_hook_path_check_rejects_undecodable_git_root(tmp_path, inside):
    checkout = tmp_path / "checkout"
    nested = checkout / "nested"
    nested.mkdir(parents=True)
    target = (checkout if inside else tmp_path) / "trusted-config"

    result = external_path_check(nested, target, invalid_output=True)

    assert result.returncode == 1, result.stderr
    assert "Cannot decode Git checkout root as UTF-8" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("root_name", ["/checkout-café", "/checkout-café ", "/checkout-café "],
                         ids=["plain", "trailing-em-space", "trailing-space"])
@pytest.mark.parametrize("filesystem_encoding", ["utf-8", "latin-1"])
@pytest.mark.parametrize("inside", [True, False], ids=["inside", "outside"])
def test_hook_path_check_matches_filesystem_decoding(tmp_path, root_name, filesystem_encoding, inside):
    # Model a POSIX filesystem's view of UTF-8 filename bytes independently of
    # the host's installed locales. Candidate argv paths use filesystem decoding.
    # Trailing whitespace is part of the directory name and must survive.
    root_bytes = root_name.encode("utf-8")
    git_output = root_bytes + b"\n"
    root = root_bytes.decode(filesystem_encoding)
    target = root + "/trusted-config" if inside else "/external/trusted-config"
    prelude = f"""import os, pathlib, subprocess
class ResolvedPath(pathlib.PurePosixPath):
    def resolve(self):
        return self
    @classmethod
    def cwd(cls):
        return cls({root + '/nested'!r})
pathlib.Path = ResolvedPath
os.fsdecode = lambda value: value.decode({filesystem_encoding!r}) if isinstance(value, bytes) else value
def check_output(*args, **kwargs):
    assert not kwargs, kwargs  # Git's root must be read as raw bytes
    return {git_output!r}
subprocess.check_output = check_output
"""
    body = dict(python_heredocs(ROOT / "hooks/lib/common.sh"))["PYEXTERNAL"]
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("SCAN_") and not key.startswith("GIT_")}
    result = subprocess.run([sys.executable, "-I", "-c", prelude + body, target],
                            cwd=tmp_path, env=environment, capture_output=True,
                            text=True, encoding="utf-8", errors="replace")

    assert result.returncode == (1 if inside else 0), result.stderr
    if inside:
        assert "Trusted path must be outside" in result.stderr
