"""Configuration management for SpeakType."""

import json
import os
import tempfile
import math
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
    "last_seen_bundle_fingerprint": "",  # Last bundled app build that completed startup
    "permission_restart_pending_after_refresh": False,
    "whisper_mode_enabled": True,  # Auto-detect whispers and apply real-time gain boost
    "scene_prompts_enabled": True,  # Use per-application prompt templates during polish
    "scene_prompts": {},  # User overrides keyed by scene id (defaults defined in polish.py)
    "hotword_learning_enabled": True,  # Learn terminology from immediate edits to SpeakType insertions
    "hotword_context_enabled": True,  # Feed learned active hotwords into ASR/polish context
    "hotword_auto_corrections_enabled": True,  # Promote high-confidence learned wrong->right pairs
    "hotword_observation_seconds": 18,  # Short post-insert edit observation window
    "hotword_observation_stable_seconds": 1.2,  # Debounce before learning from an edit
    "hotword_max_context_terms": 30,  # Max active hotwords passed to one recognition turn
}

CONFIG_DIR = Path(os.environ.get("SPEAKTYPE_CONFIG_DIR", Path.home() / ".speaktype")).expanduser().resolve()
CONFIG_FILE = CONFIG_DIR / "config.json"
HISTORY_FILE = CONFIG_DIR / "history.json"
CUSTOM_DICT_FILE = CONFIG_DIR / "custom_dictionary.json"


def _normalize_config(config: dict) -> dict:
    """Clamp legacy config values to the v2.1 product contract."""
    if not isinstance(config, dict):
        raise ValueError("SpeakType configuration must be a JSON object")
    normalized = dict(config)
    for key, default in DEFAULT_CONFIG.items():
        value = normalized.get(key, default)
        if isinstance(default, bool) and not isinstance(value, bool):
            raise ValueError(f"Configuration '{key}' must be true or false")
        if isinstance(default, str) and not isinstance(value, str):
            raise ValueError(f"Configuration '{key}' must be a string")
        if isinstance(default, dict) and not isinstance(value, dict):
            raise ValueError(f"Configuration '{key}' must be an object")
    for key in ("sample_rate", "history_max_entries", "hotword_max_context_terms"):
        value = normalized.get(key, DEFAULT_CONFIG[key])
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"Configuration '{key}' must be a positive integer")
    for key in ("hotword_observation_seconds", "hotword_observation_stable_seconds", "max_recording_seconds"):
        value = normalized.get(key, DEFAULT_CONFIG[key])
        if key == "max_recording_seconds" and value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"Configuration '{key}' must be a finite nonnegative number")
    device = normalized.get("audio_device")
    if device is not None and (isinstance(device, bool) or not isinstance(device, (int, str))
                               or isinstance(device, int) and device < 0):
        raise ValueError("Configuration 'audio_device' must be a device name, index, or null")
    for key, allowed in (("dictation_mode", ("push_to_talk", "toggle")),
                         ("insert_method", ("paste", "type")), ("ui_language", ("zh", "en"))):
        if normalized.get(key, DEFAULT_CONFIG[key]) not in allowed:
            raise ValueError(f"Unsupported configuration '{key}'")
    prompts = normalized.get("scene_prompts", {})
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in prompts.items()):
        raise ValueError("Configuration 'scene_prompts' must map scene names to strings")
    normalized["asr_backend"] = "qwen"
    if not normalized.get("asr_model"):
        normalized["asr_model"] = DEFAULT_CONFIG["asr_model"]
    if not normalized.get("whisper_model"):
        normalized["whisper_model"] = DEFAULT_CONFIG["whisper_model"]
    return normalized


def ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def get_temp_dir() -> Path:
    directory = CONFIG_DIR / "temp"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return directory


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
        with open(CONFIG_FILE, encoding="utf-8") as f:
            saved = json.load(f)
        if not isinstance(saved, dict):
            raise ValueError(f"Configuration must be a JSON object: {CONFIG_FILE}")
        config = {**DEFAULT_CONFIG, **saved}
        return _normalize_config(config)
    return _normalize_config(DEFAULT_CONFIG)


def save_config(config: dict):
    write_json_file(CONFIG_FILE, _normalize_config(config))


def load_custom_dictionary() -> list:
    if CUSTOM_DICT_FILE.exists():
        with open(CUSTOM_DICT_FILE, encoding="utf-8") as f:
            words = json.load(f)
        if not isinstance(words, list) or any(not isinstance(word, str) for word in words):
            raise ValueError(f"Custom dictionary must be a list of strings: {CUSTOM_DICT_FILE}")
        return words
    return []


def save_custom_dictionary(words: list):
    if not isinstance(words, list) or any(not isinstance(word, str) for word in words):
        raise ValueError("Custom dictionary must be a list of strings")
    write_json_file(CUSTOM_DICT_FILE, words)
