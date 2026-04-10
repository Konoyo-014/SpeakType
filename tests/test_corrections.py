"""Tests for the user-defined correction store."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def store(tmp_path):
    corrections_file = tmp_path / "corrections.json"
    with patch("speaktype.corrections.CORRECTIONS_FILE", corrections_file), \
         patch("speaktype.config.CONFIG_DIR", tmp_path):
        from speaktype.corrections import CorrectionStore
        yield CorrectionStore(path=corrections_file)


class TestEmptyStore:
    def test_apply_passthrough_when_empty(self, store):
        assert store.apply("Hello, world.") == "Hello, world."

    def test_apply_handles_empty_text(self, store):
        assert store.apply("") == ""

    def test_get_all_empty(self, store):
        assert store.get_all() == []

    def test_len_zero(self, store):
        assert len(store) == 0


class TestAdd:
    def test_add_simple(self, store):
        store.add("PI thon", "Python")
        assert store.apply("I love PI thon programming") == "I love Python programming"

    def test_add_is_case_insensitive(self, store):
        store.add("python", "Python")
        assert store.apply("i love PYTHON") == "i love Python"
        assert store.apply("python rocks") == "Python rocks"

    def test_add_chinese_phrase(self, store):
        store.add("我 sql", "MySQL")
        assert store.apply("用 我 sql 做查询") == "用 MySQL 做查询"

    def test_add_strips_whitespace(self, store):
        store.add("  spaced  ", "  trimmed  ")
        assert store.apply("look spaced here") == "look trimmed here"

    def test_add_empty_wrong_is_noop(self, store):
        store.add("", "anything")
        assert len(store) == 0

    def test_add_updates_existing(self, store):
        store.add("foo", "bar")
        store.add("foo", "baz")
        assert len(store) == 1
        assert store.apply("foo") == "baz"


class TestApply:
    def test_word_boundary_avoids_substring_match(self, store):
        store.add("py", "Python")
        # "py" inside "happy" should NOT be replaced
        assert store.apply("I am happy") == "I am happy"

    def test_multiple_corrections_apply(self, store):
        store.add("py", "Python")
        store.add("js", "JavaScript")
        result = store.apply("py and js")
        assert "Python" in result
        assert "JavaScript" in result

    def test_correction_handles_punctuation(self, store):
        store.add("py", "Python")
        # "py," should still match "py" as a whole word
        assert store.apply("I love py, you know.") == "I love Python, you know."


class TestRemove:
    def test_remove(self, store):
        store.add("foo", "bar")
        store.remove("foo")
        assert len(store) == 0
        assert store.apply("foo") == "foo"

    def test_remove_case_insensitive(self, store):
        store.add("foo", "bar")
        store.remove("FOO")
        assert len(store) == 0

    def test_remove_unknown_is_noop(self, store):
        store.add("foo", "bar")
        store.remove("nope")
        assert len(store) == 1


class TestReplaceAll:
    def test_replace_all_resets_collection(self, store):
        store.add("foo", "bar")
        store.replace_all([
            {"wrong": "alpha", "right": "ALPHA"},
            {"wrong": "beta", "right": "BETA"},
        ])
        assert len(store) == 2
        assert store.apply("foo") == "foo"
        assert store.apply("alpha and beta") == "ALPHA and BETA"

    def test_replace_all_skips_empty_wrong(self, store):
        store.replace_all([
            {"wrong": "", "right": "x"},
            {"wrong": "ok", "right": "OK"},
        ])
        assert len(store) == 1


class TestPersistence:
    def test_save_and_reload(self, store, tmp_path):
        store.add("foo", "bar")
        # Spin up a fresh store pointing at the same file.
        from speaktype.corrections import CorrectionStore
        new_store = CorrectionStore(path=store._path)
        assert len(new_store) == 1
        assert new_store.apply("foo") == "bar"

    def test_load_handles_corrupt_file(self, tmp_path):
        corrupt = tmp_path / "corrections.json"
        corrupt.write_text("not json{{{", encoding="utf-8")
        with patch("speaktype.config.CONFIG_DIR", tmp_path):
            from speaktype.corrections import CorrectionStore
            store = CorrectionStore(path=corrupt)
            assert len(store) == 0

    def test_clear_persists(self, store):
        store.add("foo", "bar")
        store.clear()
        from speaktype.corrections import CorrectionStore
        new_store = CorrectionStore(path=store._path)
        assert len(new_store) == 0
