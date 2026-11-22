"""Text helpers preserve the caller's exact newline bytes on every platform."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import safe_io


@pytest.mark.parametrize('helper', ['write_text', 'append_text'])
def test_text_stream_disables_platform_newline_translation(tmp_path, monkeypatch, helper):
    original = safe_io.os.fdopen
    opened = []

    def capture(*args, **kwargs):
        opened.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(safe_io.os, 'fdopen', capture)
    getattr(safe_io, helper)(tmp_path / 'output', 'one\ntwo\r\nthree\r')
    # This assertion also fails on Linux with the Windows-only defect.
    assert opened[0].get('newline') == ''


@pytest.mark.parametrize('helper', ['write_text', 'append_text'])
def test_text_helpers_preserve_exact_bytes(tmp_path, helper):
    output = tmp_path / 'output'
    output.write_bytes(b'existing\r\n')
    text = 'one\ntwo\r\nthree\r\nUnicode: \u00e9\n'
    getattr(safe_io, helper)(output, text)
    prefix = b'existing\r\n' if helper == 'append_text' else b''
    assert output.read_bytes() == prefix + text.encode('utf-8')
