"""Regression coverage for fix-loop configuration reporting and compatibility."""
import json
import os
from pathlib import Path

import pytest
import yaml

import render_scan_config as renderer

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("tier", ["starter", "standard", "strict"])
@pytest.mark.parametrize("flag", [False, True])
def test_render_reports_written_value_without_changing_bytes(tmp_path, capsys, tier, flag):
    out = tmp_path / "scan-config.yaml"
    template = (ROOT / "templates/scan-config" / f"{tier}.yaml").read_text(encoding="utf-8")
    expected = renderer.enable_fix_loop(template) if flag else template
    args = ["render", "--tier", tier, "--templates-dir", str(ROOT / "templates/scan-config"), "--out", str(out)]
    assert renderer.main(args + (["--enable-fix-loop"] if flag else [])) == 0
    assert out.read_bytes() == expected.replace("\n", os.linesep).encode("utf-8")
    output = capsys.readouterr().out
    enabled = yaml.safe_load(expected)["fix_loop"]["enabled"]
    assert f"fix_loop={str(enabled).lower()}" in output
    assert ("WARNING:" in output) == (enabled and not flag)
    if enabled and not flag:
        assert "--enable-fix-loop" in output
        assert "caller" in output and "labels" in output and "secret" in output
        assert "already" in output
        output.encode("ascii")


@pytest.mark.parametrize("content,value", [
    (b"fix_loop:\n  enabled: true\n", "true"),
    (b"fix_loop: {enabled: false}\n", "false"),
    (b"fix_loop:\n  enabled: 'false'\n", "unknown"),
    (b"languages: {}\n", "unknown"),
    (b"fix_loop: [broken\n", "unknown"),
    (b"\xff", "unknown"),
])
@pytest.mark.parametrize("flag", [False, True])
def test_existing_config_reports_actual_value_and_is_unchanged(tmp_path, capsys, content, value, flag):
    out = tmp_path / "scan-config.yaml"
    out.write_bytes(content)
    args = ["render", "--tier", "standard", "--out", str(out)]
    assert renderer.main(args + (["--enable-fix-loop"] if flag else [])) == 0
    output = capsys.readouterr().out
    assert f"fix_loop={value}" in output
    assert out.read_bytes() == content
    assert ("WARNING:" in output) == ((value == "true" and not flag) or (value == "false" and flag))
    output.encode("ascii")


def test_unreadable_existing_config_is_unknown_and_successful(tmp_path, monkeypatch, capsys):
    out = tmp_path / "scan-config.yaml"
    out.write_text("fix_loop: {enabled: true}\n", encoding="utf-8")
    original = Path.read_text
    def unreadable(path, *args, **kwargs):
        if path == out:
            raise PermissionError("not readable")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", unreadable)
    assert renderer.main(["render", "--tier", "standard", "--out", str(out)]) == 0
    assert "fix_loop=unknown" in capsys.readouterr().out
