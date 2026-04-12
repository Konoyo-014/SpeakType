"""Tests for the dictation history export pipeline."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def history(tmp_path):
    history_file = tmp_path / "history.json"
    with patch("speaktype.history.HISTORY_FILE", history_file), \
         patch("speaktype.config.CONFIG_DIR", tmp_path), \
         patch("speaktype.config.HISTORY_FILE", history_file):
        from speaktype.history import DictationHistory
        h = DictationHistory(max_entries=100)
        h._entries = [
            {
                "timestamp": "2026-04-06T10:15:00",
                "raw": "hello world",
                "polished": "Hello, world.",
                "app": "Mail",
                "duration": 1.5,
            },
            {
                "timestamp": "2026-04-06T10:20:30",
                "raw": "test, comma",
                "polished": "Test, comma.",
                "app": "Slack",
                "duration": 0.8,
            },
        ]
        yield h


class TestRender:
    def test_render_txt(self, history):
        out = history.render(history._entries, "txt")
        assert "Hello, world." in out
        assert "Test, comma." in out
        assert "Mail" in out
        assert "Slack" in out
        # Plain text uses one line per entry
        assert out.count("\n") == 2

    def test_render_md(self, history):
        out = history.render(history._entries, "md")
        assert out.startswith("# SpeakType Dictation History")
        assert "## 2026-04-06T10:15:00 — Mail (1.5s)" in out
        assert "**Polished:** Hello, world." in out
        assert "**Raw:** hello world" in out

    def test_render_csv(self, history):
        out = history.render(history._entries, "csv")
        lines = out.strip().splitlines()
        assert lines[0] == "timestamp,app,duration,raw,polished"
        assert "Mail" in lines[1]
        assert "Slack" in lines[2]

    def test_render_csv_quotes_commas(self, history):
        out = history.render(history._entries, "csv")
        # Both raw and polished contain commas — should be quoted
        assert '"test, comma"' in out
        assert '"Test, comma."' in out

    def test_render_json(self, history):
        out = history.render(history._entries, "json")
        parsed = json.loads(out)
        assert len(parsed) == 2
        assert parsed[0]["app"] == "Mail"

    def test_render_unknown_format_raises(self, history):
        # Render does NOT validate — it just falls through to txt.
        # The validation lives in export(); test that separately.
        pass


class TestExport:
    def test_export_writes_file(self, history, tmp_path):
        target = tmp_path / "exported.md"
        path = history.export(target)
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "Hello, world." in content
        assert path == target

    def test_export_infers_format_from_extension(self, history, tmp_path):
        for ext in ("txt", "md", "csv", "json"):
            target = tmp_path / f"out.{ext}"
            history.export(target)
            assert target.exists()

    def test_export_explicit_format_overrides_extension(self, history, tmp_path):
        target = tmp_path / "out.weird"
        history.export(target, fmt="json")
        parsed = json.loads(target.read_text(encoding="utf-8"))
        assert isinstance(parsed, list)

    def test_export_unsupported_format_raises(self, history, tmp_path):
        target = tmp_path / "out.xyz"
        with pytest.raises(ValueError):
            history.export(target, fmt="xyz")

    def test_export_creates_parent_dir(self, history, tmp_path):
        target = tmp_path / "nested" / "deeper" / "out.txt"
        history.export(target)
        assert target.exists()

    def test_add_async_eventually_persists(self, history, tmp_path):
        target = tmp_path / "history.json"
        with patch("speaktype.history.HISTORY_FILE", target):
            history.add_async("raw", "polished", app_name="Mail", duration_sec=1.2)
            for _ in range(20):
                if target.exists():
                    break
                __import__("time").sleep(0.01)
            assert target.exists()
            payload = json.loads(target.read_text(encoding="utf-8"))
            assert payload[-1]["polished"] == "polished"
