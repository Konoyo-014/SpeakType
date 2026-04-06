"""Tests for AppleScript execution helpers."""

from types import SimpleNamespace

from speaktype.applescript import run_osascript


def test_run_osascript_decodes_utf8_output(monkeypatch):
    def fake_run(cmd, capture_output, timeout):
        assert cmd == ["osascript", "-e", 'return "ok"']
        assert capture_output is True
        assert timeout == 2
        return SimpleNamespace(
            returncode=1,
            stdout="你好".encode("utf-8"),
            stderr="错误".encode("utf-8"),
        )

    monkeypatch.setattr("speaktype.applescript.subprocess.run", fake_run)

    result = run_osascript('return "ok"')

    assert result.returncode == 1
    assert result.stdout == "你好"
    assert result.stderr == "错误"
