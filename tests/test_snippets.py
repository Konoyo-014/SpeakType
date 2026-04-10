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


class TestFuzzyMatching:
    def _make_lib(self, tmp_path, snippets):
        snippets_file = tmp_path / "snippets.json"
        snippets_file.write_text(json.dumps(snippets))
        with patch("speaktype.snippets.SNIPPETS_FILE", snippets_file), \
             patch("speaktype.snippets.CONFIG_DIR", tmp_path), \
             patch("speaktype.config.CONFIG_DIR", tmp_path):
            from speaktype.snippets import SnippetLibrary
            return SnippetLibrary()

    def test_punctuation_differences_match(self, tmp_path):
        lib = self._make_lib(tmp_path, [
            {"trigger": "best regards", "text": "Best regards,\n", "description": ""},
        ])
        assert lib.match("Best regards.") == "Best regards,\n"
        assert lib.match("best, regards") == "Best regards,\n"

    def test_chinese_punctuation_match(self, tmp_path):
        lib = self._make_lib(tmp_path, [
            {"trigger": "我的邮箱", "text": "user@example.com", "description": ""},
        ])
        assert lib.match("我的邮箱。") == "user@example.com"
        assert lib.match("我的邮箱！") == "user@example.com"

    def test_one_edit_distance_for_short_triggers(self, tmp_path):
        lib = self._make_lib(tmp_path, [
            {"trigger": "我的邮箱", "text": "user@example.com", "description": ""},
        ])
        # "我邮箱" — one missing character relative to the trigger
        assert lib.match("我邮箱") == "user@example.com"

    def test_long_trigger_does_not_fuzzy_match(self, tmp_path):
        long_trigger = "this is a very long trigger phrase that should not fuzzy match"
        lib = self._make_lib(tmp_path, [
            {"trigger": long_trigger, "text": "x", "description": ""},
        ])
        # A small typo in a long sentence should NOT match — that would
        # be too aggressive and break normal dictation.
        assert lib.match("this is a very long trigger phrase that should not fuzy match") is None

    def test_fuzzy_can_be_disabled(self, tmp_path):
        lib = self._make_lib(tmp_path, [
            {"trigger": "我的邮箱", "text": "user@example.com", "description": ""},
        ])
        assert lib.match("我邮箱", fuzzy=False) is None


class TestVariableExpansion:
    def _make_lib(self, tmp_path, snippets):
        snippets_file = tmp_path / "snippets.json"
        snippets_file.write_text(json.dumps(snippets))
        with patch("speaktype.snippets.SNIPPETS_FILE", snippets_file), \
             patch("speaktype.snippets.CONFIG_DIR", tmp_path), \
             patch("speaktype.config.CONFIG_DIR", tmp_path):
            from speaktype.snippets import SnippetLibrary
            return SnippetLibrary()

    def test_date_placeholder_expands(self, tmp_path):
        lib = self._make_lib(tmp_path, [
            {"trigger": "today", "text": "{date}", "description": ""},
        ])
        from datetime import datetime
        result = lib.match("today")
        # Result should look like a date — exact value depends on the
        # current day, but it must be 10 characters with two dashes.
        assert result is not None
        assert len(result) == 10
        assert result.count("-") == 2

    def test_env_placeholder_expands(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SPEAKTYPE_TEST_VAR", "hello-from-env")
        lib = self._make_lib(tmp_path, [
            {"trigger": "say env", "text": "value: {env:SPEAKTYPE_TEST_VAR}", "description": ""},
        ])
        assert lib.match("say env") == "value: hello-from-env"

    def test_sensitive_placeholders_do_not_expand_via_fuzzy_match(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SPEAKTYPE_TEST_VAR", "hello-from-env")
        lib = self._make_lib(tmp_path, [
            {"trigger": "say env", "text": "value: {env:SPEAKTYPE_TEST_VAR}", "description": ""},
        ])
        assert lib.match("sayen v") is None

    def test_clipboard_placeholder_requires_exact_match(self, tmp_path):
        lib = self._make_lib(tmp_path, [
            {"trigger": "paste secret", "text": "{clipboard}", "description": ""},
        ])
        with patch("speaktype.snippets._read_clipboard", return_value="secret-value"):
            assert lib.match("paste secret") == "secret-value"
            assert lib.match("paste, secret!") is None

    def test_unknown_placeholder_left_intact(self, tmp_path):
        lib = self._make_lib(tmp_path, [
            {"trigger": "weird", "text": "before {nope_unknown} after", "description": ""},
        ])
        assert lib.match("weird") == "before {nope_unknown} after"

    def test_text_without_placeholders_unchanged(self, tmp_path):
        lib = self._make_lib(tmp_path, [
            {"trigger": "hi", "text": "Hello!", "description": ""},
        ])
        assert lib.match("hi") == "Hello!"
