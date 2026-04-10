"""Tests for the polish prompt-builder flags (auto_punctuation / filler / scene)."""

from unittest.mock import patch

import pytest

from speaktype.polish import SCENE_PROMPTS, PolishEngine


@pytest.fixture
def engine():
    eng = PolishEngine(model="fake-model", ollama_url="http://localhost:0")
    eng._available = True
    return eng


def _capture(engine, **polish_kwargs):
    """Drive ``engine.polish`` with mocked ``_chat`` and return the system prompt."""
    captured = {}

    def fake_chat(messages, max_tokens=1024):
        captured["messages"] = messages
        return "ok"

    with patch.object(engine, "_chat", side_effect=fake_chat):
        engine.polish("hello world", **polish_kwargs)

    system_msg = captured["messages"][0]
    assert system_msg["role"] == "system"
    return system_msg["content"]


class TestFlagWiring:
    def test_default_flags_remove_fillers(self, engine):
        prompt = _capture(engine)
        assert "Remove filler words" in prompt
        assert "Fix grammar and add natural punctuation" in prompt

    def test_filler_removal_off_keeps_fillers(self, engine):
        prompt = _capture(engine, filler_removal=False)
        assert "Preserve filler words" in prompt
        assert "Remove filler words" not in prompt

    def test_auto_punctuation_off_freezes_punctuation(self, engine):
        prompt = _capture(engine, auto_punctuation=False)
        assert "Do NOT add or change punctuation" in prompt
        assert "Fix grammar and add natural punctuation" not in prompt

    def test_both_flags_off(self, engine):
        prompt = _capture(engine, auto_punctuation=False, filler_removal=False)
        assert "Preserve filler words" in prompt
        assert "Do NOT add or change punctuation" in prompt


class TestScenePrompts:
    def test_default_scene_has_no_section(self, engine):
        prompt = _capture(engine)
        assert "Scene guidance:" not in prompt

    def test_email_scene_inserted(self, engine):
        prompt = _capture(engine, scene="email")
        assert "Scene guidance:" in prompt
        assert "polished email body" in prompt

    def test_code_scene_preserves_terms(self, engine):
        prompt = _capture(engine, scene="code")
        assert "Scene guidance:" in prompt
        assert "code editor" in prompt or "Preserve all technical terms" in prompt

    def test_explicit_template_overrides_scene(self, engine):
        prompt = _capture(engine, scene="email", scene_template="MY CUSTOM TEMPLATE")
        assert "MY CUSTOM TEMPLATE" in prompt
        assert "polished email body" not in prompt

    def test_unknown_scene_id_falls_through_silently(self, engine):
        prompt = _capture(engine, scene="not-a-real-scene")
        # No scene guidance section because the lookup returned ""
        assert "Scene guidance:" not in prompt

    def test_default_scene_id_has_empty_string(self):
        assert SCENE_PROMPTS["default"] == ""

    def test_all_known_scene_ids_present(self):
        assert "email" in SCENE_PROMPTS
        assert "chat" in SCENE_PROMPTS
        assert "code" in SCENE_PROMPTS
        assert "notes" in SCENE_PROMPTS


class TestEarlyOuts:
    def test_polish_returns_empty_for_blank_input(self, engine):
        assert engine.polish("   ") == "   "

    def test_polish_returns_text_when_unavailable(self, engine):
        engine._available = False
        assert engine.polish("hello") == "hello"
