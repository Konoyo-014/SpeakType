"""Local dictation history management."""

import json
import logging
from datetime import datetime
from .config import HISTORY_FILE, ensure_config_dir, write_json_file

logger = logging.getLogger("speaktype.history")


class DictationHistory:
    def __init__(self, max_entries=1000):
        self.max_entries = max_entries
        self._entries = []
        self._load()

    def _load(self):
        ensure_config_dir()
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, encoding="utf-8") as f:
                    self._entries = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._entries = []

    def _save(self):
        try:
            write_json_file(HISTORY_FILE, self._entries[-self.max_entries:])
        except IOError as e:
            logger.error(f"Failed to save history: {e}")

    def add(self, raw_text: str, polished_text: str, app_name: str = "", duration_sec: float = 0):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "raw": raw_text,
            "polished": polished_text,
            "app": app_name,
            "duration": round(duration_sec, 1),
        }
        self._entries.append(entry)
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries:]
        self._save()

    def get_recent(self, count=20) -> list:
        return self._entries[-count:]

    def get_stats(self) -> dict:
        total_words = sum(len(e.get("polished", "").split()) for e in self._entries)
        total_duration = sum(e.get("duration", 0) for e in self._entries)
        return {
            "total_entries": len(self._entries),
            "total_words": total_words,
            "total_duration_min": round(total_duration / 60, 1),
        }

    def clear(self):
        self._entries = []
        self._save()
