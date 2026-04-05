"""Tests for configuration management."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


class TestDefaultConfig:
    def test_has_required_keys(self):
        from speaktype.config import DEFAULT_CONFIG
        required = [
            "hotkey", "asr_model", "llm_model", "ollama_url",
            "sample_rate", "polish_enabled", "language",
            "voice_commands_enabled", "insert_method",
            "dictation_mode", "asr_backend", "whisper_model",
            "audio_device", "streaming_preview", "plugins_enabled",
        ]
        for key in required:
            assert key in DEFAULT_CONFIG, f"Missing config key: {key}"

    def test_default_values(self):
        from speaktype.config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["hotkey"] == "right_cmd"
        assert DEFAULT_CONFIG["dictation_mode"] == "push_to_talk"
        assert DEFAULT_CONFIG["asr_backend"] == "qwen"
        assert DEFAULT_CONFIG["audio_device"] is None
        assert DEFAULT_CONFIG["streaming_preview"] is False
        assert DEFAULT_CONFIG["plugins_enabled"] is False


class TestLoadSaveConfig:
    def test_load_creates_default(self, tmp_path):
        config_file = tmp_path / "config.json"
        with patch("speaktype.config.CONFIG_FILE", config_file), \
             patch("speaktype.config.CONFIG_DIR", tmp_path):
            from speaktype.config import load_config, DEFAULT_CONFIG
            config = load_config()
            assert config["hotkey"] == DEFAULT_CONFIG["hotkey"]

    def test_save_and_load(self, tmp_path):
        config_file = tmp_path / "config.json"
        with patch("speaktype.config.CONFIG_FILE", config_file), \
             patch("speaktype.config.CONFIG_DIR", tmp_path):
            from speaktype.config import load_config, save_config
            config = load_config()
            config["hotkey"] = "f5"
            save_config(config)
            reloaded = load_config()
            assert reloaded["hotkey"] == "f5"

    def test_load_handles_corrupt_file(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("not json{{{")
        with patch("speaktype.config.CONFIG_FILE", config_file), \
             patch("speaktype.config.CONFIG_DIR", tmp_path):
            from speaktype.config import load_config, DEFAULT_CONFIG
            config = load_config()
            assert config["hotkey"] == DEFAULT_CONFIG["hotkey"]

    def test_load_merges_with_defaults(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"hotkey": "f6"}')
        with patch("speaktype.config.CONFIG_FILE", config_file), \
             patch("speaktype.config.CONFIG_DIR", tmp_path):
            from speaktype.config import load_config
            config = load_config()
            assert config["hotkey"] == "f6"
            assert "polish_enabled" in config  # merged from default


class TestCustomDictionary:
    def test_load_empty(self, tmp_path):
        dict_file = tmp_path / "custom_dictionary.json"
        with patch("speaktype.config.CUSTOM_DICT_FILE", dict_file), \
             patch("speaktype.config.CONFIG_DIR", tmp_path):
            from speaktype.config import load_custom_dictionary
            words = load_custom_dictionary()
            assert words == []

    def test_save_and_load(self, tmp_path):
        dict_file = tmp_path / "custom_dictionary.json"
        with patch("speaktype.config.CUSTOM_DICT_FILE", dict_file), \
             patch("speaktype.config.CONFIG_DIR", tmp_path):
            from speaktype.config import save_custom_dictionary, load_custom_dictionary
            save_custom_dictionary(["TensorFlow", "PyTorch"])
            loaded = load_custom_dictionary()
            assert loaded == ["TensorFlow", "PyTorch"]
