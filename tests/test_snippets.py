"""Tests for snippet library."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest


class TestSnippetLibrary:
    def _make_lib(self, tmp_path, snippets=None):
        snippets_file = tmp_path / "snippets.json"
        if snippets is not None:
            snippets_file.write_text(json.dumps(snippets))
        with patch("speaktype.snippets.SNIPPETS_FILE", snippets_file), \
             patch("speaktype.snippets.CONFIG_DIR", tmp_path), \
             patch("speaktype.config.CONFIG_DIR", tmp_path):
            from speaktype.snippets import SnippetLibrary
            return SnippetLibrary()

    def test_default_snippets(self, tmp_path):
        lib = self._make_lib(tmp_path)
        all_snippets = lib.get_all()
        assert len(all_snippets) > 0
        triggers = [s["trigger"] for s in all_snippets]
        assert "best regards" in triggers

    def test_match_found(self, tmp_path):
        lib = self._make_lib(tmp_path, [
            {"trigger": "my email", "text": "user@example.com", "description": ""},
        ])
        result = lib.match("my email")
        assert result == "user@example.com"

    def test_match_case_insensitive(self, tmp_path):
        lib = self._make_lib(tmp_path, [
            {"trigger": "my email", "text": "user@example.com", "description": ""},
        ])
        assert lib.match("My Email") == "user@example.com"

    def test_match_not_found(self, tmp_path):
        lib = self._make_lib(tmp_path, [
            {"trigger": "my email", "text": "user@example.com", "description": ""},
        ])
        assert lib.match("hello world") is None

    def test_match_empty_text_returns_none(self, tmp_path):
        lib = self._make_lib(tmp_path, [
            {"trigger": "my email", "text": "", "description": ""},
        ])
        assert lib.match("my email") is None

    def test_add_snippet(self, tmp_path):
        lib = self._make_lib(tmp_path, [])
        lib.add("test", "test text", "a test")
        assert lib.match("test") == "test text"

    def test_remove_snippet(self, tmp_path):
        lib = self._make_lib(tmp_path, [
            {"trigger": "test", "text": "hello", "description": ""},
        ])
        lib.remove(0)
        assert lib.match("test") is None

    def test_update_snippet(self, tmp_path):
        lib = self._make_lib(tmp_path, [
            {"trigger": "test", "text": "old", "description": ""},
        ])
        lib.update(0, "test", "new", "updated")
        assert lib.match("test") == "new"
