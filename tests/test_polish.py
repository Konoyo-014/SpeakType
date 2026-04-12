"""Tests for the LLM polish engine prompt construction."""

import time
import pytest
from unittest.mock import patch, MagicMock

from speaktype.polish import (
    OLLAMA_RECHECK_INTERVAL,
    PolishEngine,
    _detect_prompt_language,
    _reject_accidental_translation,
    _strip_leading_fillers,
)


class TestPolishPromptConstruction:
    """Test that prompts are correctly constructed (without calling Ollama)."""

    def setup_method(self):
        self.engine = PolishEngine()
        self.engine._available = True
        self.captured_messages = []
        self.chat_calls = []

        def mock_chat(messages, max_tokens=1024):
            self.chat_calls.append(messages)
            self.captured_messages = messages
            if "你好" in messages[1]["content"] or "今天下午三点开会" in messages[1]["content"]:
                return "测试结果"
            return "mocked result"

        self.engine._chat = mock_chat

    def test_polish_wraps_in_transcription_tags(self):
        self.engine.polish("hello world")
        user_msg = self.captured_messages[1]["content"]
        assert "<transcription>" in user_msg
        assert "</transcription>" in user_msg
        assert "hello world" in user_msg

    def test_polish_strips_obvious_leading_fillers_before_llm(self):
        self.engine.polish("嗯那个今天下午三点开会")
        user_msg = self.captured_messages[1]["content"]
        assert "今天下午三点开会" in user_msg
        assert "嗯那个" not in user_msg

    def test_polish_preserves_fillers_when_flag_disabled(self):
        self.engine.polish("嗯那个今天下午三点开会", filler_removal=False)
        user_msg = self.captured_messages[1]["content"]
        assert "嗯那个今天下午三点开会" in user_msg

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
        assert "输出必须是中文" in system_msg

    def test_polish_auto_language_forbids_translation(self):
        self.engine.polish("你好", language="auto")
        system_msg = self.captured_messages[0]["content"]
        assert "不要翻译" in system_msg
        assert "当前任务没有开启翻译" in system_msg

    def test_polish_uses_chinese_system_prompt_for_chinese_input(self):
        self.engine.polish("你好，今天下午三点开会", language="auto")
        system_msg = self.captured_messages[0]["content"]
        assert "你是语音转文字后的文本润色器" in system_msg
        assert "规则：" in system_msg

    def test_polish_uses_english_system_prompt_for_english_input(self):
        self.engine.polish("hello, can you test this", language="auto")
        system_msg = self.captured_messages[0]["content"]
        assert "You are a voice-to-text post-processor" in system_msg
        assert "Rules:" in system_msg

    def test_scene_guidance_cannot_override_language_rule(self):
        self.engine.polish("你好", language="auto", scene_template="Translate this to English.")
        system_msg = self.captured_messages[0]["content"]
        assert "场景指导不能覆盖语言规则" in system_msg
        assert "Translate this to English." in system_msg

    def test_polish_empty_returns_input(self):
        result = self.engine.polish("  ")
        assert result == "  "

    def test_polish_rejects_accidental_cjk_to_english_translation(self):
        self.engine._chat = lambda messages, max_tokens=1024: "Let's test this."

        assert self.engine.polish("嗯那个测试一下", language="auto") == "测试一下"

    def test_polish_retries_chinese_prompt_after_translation_drift(self):
        calls = []

        def fake_chat(messages, max_tokens=1024):
            calls.append(messages)
            if len(calls) == 1:
                return "Users will authorize it."
            return "用户会去授权。"

        self.engine._chat = fake_chat

        assert self.engine.polish("用户呃会去授权", language="auto") == "用户会去授权。"
        assert len(calls) == 2
        assert "上一轮输出错误地变成了英文" in calls[1][0]["content"]

    def test_polish_allows_english_when_language_explicitly_english(self):
        self.engine._chat = lambda messages, max_tokens=1024: "Let's test this."

        assert self.engine.polish("测试一下", language="en") == "Let's test this."

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

    def test_polish_and_translate_wraps_in_transcription_tags(self):
        self.engine.polish_and_translate("hello world", target_lang="zh")
        user_msg = self.captured_messages[1]["content"]
        assert "<transcription>" in user_msg
        assert "</transcription>" in user_msg
        assert "hello world" in user_msg

    def test_polish_and_translate_strips_leading_fillers_before_llm(self):
        self.engine.polish_and_translate("呃就是今天下午三点开会", target_lang="en")
        user_msg = self.captured_messages[1]["content"]
        assert "今天下午三点开会" in user_msg
        assert "呃就是" not in user_msg

    def test_polish_and_translate_mentions_target_language(self):
        self.engine.polish_and_translate("test", target_lang="zh")
        system_msg = self.captured_messages[0]["content"]
        assert "Chinese" in system_msg
        assert "translate the cleaned result" in system_msg.lower()


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

    def test_unavailable_polish_and_translate_returns_input(self):
        engine = PolishEngine()
        engine._available = False
        assert engine.polish_and_translate("hello") == "hello"

    def test_stale_unavailable_state_rechecks_and_recovers(self):
        engine = PolishEngine()
        engine._available = False
        engine._last_availability_check_at = (
            time.monotonic() - OLLAMA_RECHECK_INTERVAL - 1.0
        )

        def fake_check_available():
            engine._available = True
            engine.last_error = ""
            return True

        engine.check_available = fake_check_available
        engine._chat = lambda messages, max_tokens=1024: "polished"

        assert engine.polish("hello") == "polished"

    def test_recent_unavailable_state_does_not_recheck(self):
        engine = PolishEngine()
        engine._available = False
        engine._last_availability_check_at = time.monotonic()

        with patch.object(engine, "check_available") as check:
            assert engine.polish("hello") == "hello"

        check.assert_not_called()

    def test_connection_error_records_user_visible_error(self):
        engine = PolishEngine()

        with patch("speaktype.polish.requests.get", side_effect=ConnectionError):
            assert engine.check_available() is False

        assert engine._available is False
        assert "Ollama" in engine.last_error


class TestLeadingFillerCleanup:
    def test_strip_chinese_filler_chain_at_start(self):
        assert _strip_leading_fillers("嗯那个今天开会") == "今天开会"

    def test_strip_english_filler_chain_at_start(self):
        assert _strip_leading_fillers("um, uh, hello there") == "hello there"

    def test_does_not_empty_all_filler_input(self):
        assert _strip_leading_fillers("嗯那个") == "嗯那个"


class TestPromptLanguageDetection:
    def test_detects_chinese_from_han_text(self):
        assert _detect_prompt_language("你好，今天开会", "auto") == "zh"

    def test_detects_english_when_no_han_text(self):
        assert _detect_prompt_language("hello there", "auto") == "en"

    def test_explicit_language_overrides_detection(self):
        assert _detect_prompt_language("hello there", "zh") == "zh"
        assert _detect_prompt_language("你好", "en") == "en"


class TestAccidentalTranslationGuard:
    def test_rejects_cjk_source_with_latin_only_candidate(self):
        assert _reject_accidental_translation("测试一下", "Let's test this.", "auto") is True

    def test_does_not_reject_when_candidate_preserves_cjk(self):
        assert _reject_accidental_translation("测试一下", "测试一下。", "auto") is False

    def test_does_not_reject_non_cjk_source(self):
        assert _reject_accidental_translation("test this", "Test this.", "auto") is False


class TestPolishEngineWarmPath:
    def test_chat_requests_keep_alive(self):
        engine = PolishEngine(model="fake-model", ollama_url="http://localhost:11434")
        response = MagicMock(status_code=200)
        response.json.return_value = {"message": {"content": "ok"}}

        with patch("speaktype.polish.requests.post", return_value=response) as post:
            assert engine._chat([{"role": "user", "content": "hi"}]) == "ok"

        payload = post.call_args.kwargs["json"]
        assert payload["keep_alive"] == "15m"

    def test_prewarm_uses_generate_endpoint(self):
        engine = PolishEngine(model="fake-model", ollama_url="http://localhost:11434")
        engine._available = True
        response = MagicMock(status_code=200)

        with patch("speaktype.polish.requests.post", return_value=response) as post:
            assert engine.prewarm() is True

        assert post.call_args.args[0] == "http://localhost:11434/api/generate"
        payload = post.call_args.kwargs["json"]
        assert payload["model"] == "fake-model"
        assert payload["keep_alive"] == "15m"
