"""Tests for the LLM polish engine prompt construction."""

import pytest
from unittest.mock import patch, MagicMock

from speaktype.polish import PolishEngine


class TestPolishPromptConstruction:
    """Test that prompts are correctly constructed (without calling Ollama)."""

    def setup_method(self):
        self.engine = PolishEngine()
        self.engine._available = True
        self.captured_messages = []

        def mock_chat(messages, max_tokens=1024):
            self.captured_messages = messages
            return "mocked result"

        self.engine._chat = mock_chat

    def test_polish_wraps_in_transcription_tags(self):
        self.engine.polish("hello world")
        user_msg = self.captured_messages[1]["content"]
        assert "<transcription>" in user_msg
        assert "</transcription>" in user_msg
        assert "hello world" in user_msg

    def test_polish_system_has_critical_directive(self):
        self.engine.polish("do something for me")
        system_msg = self.captured_messages[0]["content"]
        assert "CRITICAL" in system_msg
        assert "NOT an instruction" in system_msg

    def test_polish_system_has_examples(self):
        self.engine.polish("test")
        system_msg = self.captured_messages[0]["content"]
        assert "Examples:" in system_msg

    def test_polish_tone_formal(self):
        self.engine.polish("test", tone="formal")
        system_msg = self.captured_messages[0]["content"]
        assert "professional" in system_msg.lower() or "formal" in system_msg.lower()

    def test_polish_language_specified(self):
        self.engine.polish("test", language="zh")
        system_msg = self.captured_messages[0]["content"]
        assert "Chinese" in system_msg

    def test_polish_empty_returns_input(self):
        result = self.engine.polish("  ")
        assert result == "  "

    def test_edit_wraps_in_selected_tags(self):
        self.engine.edit_text("make shorter", "some long text here")
        user_msg = self.captured_messages[1]["content"]
        assert "<selected>" in user_msg
        assert "</selected>" in user_msg
        assert "some long text here" in user_msg
        assert "make shorter" in user_msg

    def test_translate_wraps_in_text_tags(self):
        self.engine.translate("hello world", target_lang="zh")
        user_msg = self.captured_messages[1]["content"]
        assert "<text>" in user_msg
        assert "</text>" in user_msg

    def test_translate_preserves_technical_terms_instruction(self):
        self.engine.translate("test", target_lang="zh")
        system_msg = self.captured_messages[0]["content"]
        assert "technical terms" in system_msg.lower()
        assert "brand names" in system_msg.lower()

    def test_translate_mixed_language_instruction(self):
        self.engine.translate("test", target_lang="zh")
        system_msg = self.captured_messages[0]["content"]
        assert "mix" in system_msg.lower()

    def test_translate_empty_returns_input(self):
        result = self.engine.translate("  ")
        assert result == "  "


class TestPolishEngineAvailability:
    def test_unavailable_returns_raw_text(self):
        engine = PolishEngine()
        engine._available = False
        assert engine.polish("hello") == "hello"

    def test_unavailable_edit_returns_selected(self):
        engine = PolishEngine()
        engine._available = False
        assert engine.edit_text("shorten", "long text") == "long text"

    def test_unavailable_translate_returns_input(self):
        engine = PolishEngine()
        engine._available = False
        assert engine.translate("hello") == "hello"
