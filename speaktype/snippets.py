"""Snippet library for frequently used phrases."""

import json
import logging
from .config import CONFIG_DIR, ensure_config_dir, write_json_file

logger = logging.getLogger("speaktype.snippets")

SNIPPETS_FILE = CONFIG_DIR / "snippets.json"

DEFAULT_SNIPPETS = [
    {"trigger": "my email", "text": "", "description": "Insert your email address"},
    {"trigger": "my phone", "text": "", "description": "Insert your phone number"},
    {"trigger": "best regards", "text": "Best regards,\n", "description": "Email sign-off"},
    {"trigger": "kind regards", "text": "Kind regards,\n", "description": "Email sign-off"},
    {"trigger": "thanks and regards", "text": "Thanks and regards,\n", "description": "Email sign-off"},
]


class SnippetLibrary:
    def __init__(self):
        self._snippets = []
        self._load()

    def _load(self):
        ensure_config_dir()
        if SNIPPETS_FILE.exists():
            try:
                with open(SNIPPETS_FILE) as f:
                    self._snippets = json.load(f)
                return
            except (json.JSONDecodeError, IOError):
                pass
        self._snippets = list(DEFAULT_SNIPPETS)
        self._save()

    def _save(self):
        try:
            write_json_file(SNIPPETS_FILE, self._snippets)
        except IOError as e:
            logger.error(f"Failed to save snippets: {e}")

    def match(self, text: str) -> str | None:
        """Check if text matches a snippet trigger. Returns snippet text or None."""
        text_lower = text.strip().lower()
        for snippet in self._snippets:
            if snippet["trigger"].lower() == text_lower and snippet["text"]:
                return snippet["text"]
        return None

    def get_all(self) -> list:
        return list(self._snippets)

    def add(self, trigger: str, text: str, description: str = ""):
        self._snippets.append({
            "trigger": trigger,
            "text": text,
            "description": description,
        })
        self._save()

    def remove(self, index: int):
        if 0 <= index < len(self._snippets):
            self._snippets.pop(index)
            self._save()

    def update(self, index: int, trigger: str, text: str, description: str = ""):
        if 0 <= index < len(self._snippets):
            self._snippets[index] = {
                "trigger": trigger,
                "text": text,
                "description": description,
            }
            self._save()
