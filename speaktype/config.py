"""Configuration management for SpeakType."""

import json
import os
from pathlib import Path

DEFAULT_CONFIG = {
    "hotkey": "right_cmd",  # Push-to-talk key: right_cmd, fn, ctrl+shift+space, etc.
    "dictation_mode": "push_to_talk",  # "push_to_talk" or "toggle"
    "asr_model": "mlx-community/Qwen3-ASR-1.7B-8bit",
    "asr_backend": "qwen",  # "qwen" (mlx-audio) or "whisper" (openai-whisper / mlx-whisper)
    "whisper_model": "base",  # Whisper model size: tiny, base, small, medium, large
    "llm_model": "huihui_ai/qwen3.5-abliterated:9b-Claude",
    "ollama_url": "http://localhost:11434",
    "sample_rate": 16000,
    "audio_device": None,  # None = system default, or device name/index
    "polish_enabled": True,
    "auto_punctuation": True,
    "filler_removal": True,
    "context_aware_tone": True,
    "language": "auto",  # "auto" for auto-detect, or specific like "zh", "en", "ja"
    "voice_commands_enabled": True,
    "sound_feedback": True,
    "max_recording_seconds": 360,  # 6 minutes
    "history_enabled": True,
    "history_max_entries": 1000,
    "insert_method": "paste",  # "paste" (clipboard+Cmd+V) or "type" (key-by-key)
    "translate_enabled": False,
    "translate_target": "en",  # Target language for translation: "en", "zh", "ja", "ko", etc.
    "streaming_preview": False,  # Show real-time transcription preview while recording
    "plugins_enabled": False,  # Enable plugin system
    "plugins_dir": "",  # Custom plugins directory (empty = use default ~/.speaktype/plugins/)
}

CONFIG_DIR = Path.home() / ".speaktype"
CONFIG_FILE = CONFIG_DIR / "config.json"
HISTORY_FILE = CONFIG_DIR / "history.json"
CUSTOM_DICT_FILE = CONFIG_DIR / "custom_dictionary.json"


def ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    ensure_config_dir()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                saved = json.load(f)
            config = {**DEFAULT_CONFIG, **saved}
            return config
        except (json.JSONDecodeError, IOError):
            pass
    return dict(DEFAULT_CONFIG)


def save_config(config: dict):
    ensure_config_dir()
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def load_custom_dictionary() -> list:
    if CUSTOM_DICT_FILE.exists():
        try:
            with open(CUSTOM_DICT_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return []


def save_custom_dictionary(words: list):
    ensure_config_dir()
    with open(CUSTOM_DICT_FILE, "w") as f:
        json.dump(words, f, indent=2, ensure_ascii=False)
