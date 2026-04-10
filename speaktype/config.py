"""Configuration management for SpeakType."""

import json
import os
import tempfile
from pathlib import Path

DEFAULT_CONFIG = {
    "hotkey": "right_cmd",  # Push-to-talk key: right_cmd, fn, ctrl+shift+space, etc.
    "dictation_mode": "push_to_talk",  # "push_to_talk" or "toggle"
    "asr_model": "mlx-community/Qwen3-ASR-1.7B-8bit",
    # Kept for backward-compatible config migration. v2.1 is Qwen-only.
    "asr_backend": "qwen",
    "whisper_model": "base",
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
    "streaming_preview": True,  # Show real-time transcription preview while recording
    "plugins_enabled": False,  # Enable plugin system
    "plugins_dir": "",  # Custom plugins directory (empty = use default ~/.speaktype/plugins/)
    "ui_language": "zh",  # UI language: "zh" (Chinese) or "en" (English)
    "setup_completed": False,  # True after first-launch wizard is completed
    "last_seen_version": "",  # Last app version that completed startup
    "whisper_mode_enabled": True,  # Auto-detect whispers and apply real-time gain boost
    "scene_prompts_enabled": True,  # Use per-application prompt templates during polish
    "scene_prompts": {},  # User overrides keyed by scene id (defaults defined in polish.py)
}

CONFIG_DIR = Path.home() / ".speaktype"
CONFIG_FILE = CONFIG_DIR / "config.json"
HISTORY_FILE = CONFIG_DIR / "history.json"
CUSTOM_DICT_FILE = CONFIG_DIR / "custom_dictionary.json"


def _normalize_config(config: dict) -> dict:
    """Clamp legacy config values to the v2.1 product contract."""
    normalized = dict(config)
    normalized["asr_backend"] = "qwen"
    if not normalized.get("asr_model"):
        normalized["asr_model"] = DEFAULT_CONFIG["asr_model"]
    if not normalized.get("whisper_model"):
        normalized["whisper_model"] = DEFAULT_CONFIG["whisper_model"]
    return normalized


def ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def write_json_file(path: Path, data):
    """Write JSON atomically to avoid truncating user data on partial writes."""
    ensure_config_dir()
    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_config() -> dict:
    ensure_config_dir()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                saved = json.load(f)
            config = {**DEFAULT_CONFIG, **saved}
            return _normalize_config(config)
        except (json.JSONDecodeError, IOError):
            pass
    return _normalize_config(DEFAULT_CONFIG)


def save_config(config: dict):
    write_json_file(CONFIG_FILE, _normalize_config(config))


def load_custom_dictionary() -> list:
    if CUSTOM_DICT_FILE.exists():
        try:
            with open(CUSTOM_DICT_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return []


def save_custom_dictionary(words: list):
    write_json_file(CUSTOM_DICT_FILE, words)
