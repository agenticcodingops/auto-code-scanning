"""Regression coverage for fix-loop configuration reporting and compatibility."""
import json
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
    # Line endings belong to safe_io and its own tests; the content is what must not change.
    assert out.read_bytes().replace(b"\r\n", b"\n") == expected.encode("utf-8")
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


CONFIG_PATHS = [ROOT / "scan-config.yaml", *sorted((ROOT / "templates/scan-config").glob("*.yaml")),
                *sorted((ROOT / "examples").glob("*/scan-config.yaml"))]


@pytest.mark.parametrize("path", CONFIG_PATHS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_shipped_configs_omit_retired_keys_but_keep_mirror(path):
    loop = yaml.safe_load(path.read_text(encoding="utf-8"))["fix_loop"]
    assert "label" not in loop
    assert "required_secrets" not in loop
    assert "claude_code_action_ref" in loop


def test_all_action_ref_mirrors_match_the_executed_pin():
    workflow = yaml.safe_load((ROOT / ".github/workflows/autonomous-fix.yml").read_text(encoding="utf-8"))
    pins = [s["uses"] for s in workflow["jobs"]["analyze"]["steps"]
            if s.get("uses", "").startswith("anthropics/claude-code-action@")]
    assert len(pins) == 1
    for path in CONFIG_PATHS:
        assert yaml.safe_load(path.read_text(encoding="utf-8"))["fix_loop"]["claude_code_action_ref"] == pins[0], path
    import re
    refs = re.findall(r'claude_code_action_ref: "([^"]+)"', (ROOT / "docs/FIX-LOOP.md").read_text(encoding="utf-8"))
    assert refs == pins


@pytest.mark.parametrize("example,languages", [("app-repo", "csharp,typescript"), ("terraform-repo", "terraform")])
def test_examples_are_byte_identical_to_rendered_starter(tmp_path, monkeypatch, example, languages):
    rendered = []
    # Capture the renderer's UTF-8 output before the host's newline translation.
    monkeypatch.setattr(renderer, "write_text", lambda path, text: rendered.append(text.encode("utf-8")))
    assert renderer.main(["render", "--tier", "starter", "--languages", languages,
                          "--out", str(tmp_path / "config.yaml")]) == 0
    assert (ROOT / "examples" / example / "scan-config.yaml").read_bytes() == rendered[0]


def test_retired_keys_remain_valid_and_deprecated():
    import jsonschema
    schema = json.loads((ROOT / "schemas/scan-config.schema.json").read_text(encoding="utf-8"))
    loop_schema = schema["$defs"]["fix_loop"]
    for key in ("label", "required_secrets"):
        assert loop_schema["properties"][key]["deprecated"] is True
        verb = {"label": "uses", "required_secrets": "reads"}[key]
        assert f"Ignored: nothing {verb} it" in loop_schema["properties"][key]["description"]
    assert loop_schema["additionalProperties"] is False
    assert "mirror" in loop_schema["properties"]["claude_code_action_ref"]["description"].lower()
    config = yaml.safe_load((ROOT / "templates/scan-config/starter.yaml").read_text(encoding="utf-8"))
    config["fix_loop"].update(enabled=True, label="custom-label", required_secrets=["LEGACY_SECRET"])
    jsonschema.validate(config, schema)
    del config["fix_loop"]["claude_code_action_ref"]
    with pytest.raises(jsonschema.ValidationError, match="claude_code_action_ref"):
        jsonschema.validate(config, schema)
