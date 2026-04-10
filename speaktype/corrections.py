"""User-defined ASR correction store.

A small JSON-backed dictionary mapping a frequently-misheard ASR phrase
to the user's preferred replacement. The first iteration is intentionally
*manual* — users add corrections through the Dictionary & Snippets editor.
A future iteration will infer corrections by watching the user edit text
right after dictation, but the runtime hook for that lives in app.py and
already calls into this module for the actual lookup/replace logic.

Format on disk (``~/.speaktype/corrections.json``)::

    [
        {"wrong": "PI thon", "right": "Python"},
        {"wrong": "我 sql", "right": "MySQL"}
    ]

Lookup is case-insensitive and applied to whole-word matches so editing a
correction for "PI thon" never accidentally rewrites the substring inside
"PI thoner" or similar.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Iterable, Optional

from .config import CONFIG_DIR, ensure_config_dir, write_json_file

logger = logging.getLogger("speaktype.corrections")

CORRECTIONS_FILE = CONFIG_DIR / "corrections.json"


class CorrectionStore:
    """Persistent collection of (wrong, right) replacements."""

    def __init__(self, path: Optional[Path] = None):
        self._path = path or CORRECTIONS_FILE
        self._entries: list[dict] = []
        self._lock = threading.Lock()
        self._compiled: list[tuple[re.Pattern, str]] = []
        self._load()

    # ------------------------------------------------------------------ #
    # Persistence                                                         #
    # ------------------------------------------------------------------ #

    def _load(self):
        ensure_config_dir()
        if not self._path.exists():
            self._entries = []
            self._rebuild_compiled()
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._entries = [
                    {"wrong": str(e.get("wrong", "")), "right": str(e.get("right", ""))}
                    for e in data
                    if e and e.get("wrong")
                ]
            else:
                self._entries = []
        except (IOError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load corrections from {self._path}: {e}")
            self._entries = []
        self._rebuild_compiled()

    def _save(self):
        try:
            write_json_file(self._path, self._entries)
        except IOError as e:
            logger.error(f"Failed to save corrections: {e}")

    # ------------------------------------------------------------------ #
    # Mutations                                                          #
    # ------------------------------------------------------------------ #

    def add(self, wrong: str, right: str):
        wrong = (wrong or "").strip()
        right = (right or "").strip()
        if not wrong:
            return
        with self._lock:
            # Update if the same wrong already exists
            for entry in self._entries:
                if entry.get("wrong", "").lower() == wrong.lower():
                    entry["right"] = right
                    break
            else:
                self._entries.append({"wrong": wrong, "right": right})
            self._rebuild_compiled()
        self._save()

    def remove(self, wrong: str):
        wrong = (wrong or "").strip().lower()
        with self._lock:
            before = len(self._entries)
            self._entries = [
                e for e in self._entries if e.get("wrong", "").lower() != wrong
            ]
            if len(self._entries) != before:
                self._rebuild_compiled()
        self._save()

    def clear(self):
        with self._lock:
            self._entries = []
            self._compiled = []
        self._save()

    def replace_all(self, entries: Iterable[dict]):
        """Wholesale replacement, used when saving the dict editor."""
        cleaned = []
        for entry in entries:
            wrong = (entry.get("wrong") or "").strip()
            right = (entry.get("right") or "").strip()
            if not wrong:
                continue
            cleaned.append({"wrong": wrong, "right": right})
        with self._lock:
            self._entries = cleaned
            self._rebuild_compiled()
        self._save()

    # ------------------------------------------------------------------ #
    # Lookup                                                              #
    # ------------------------------------------------------------------ #

    def get_all(self) -> list[dict]:
        with self._lock:
            return [dict(e) for e in self._entries]

    def __len__(self) -> int:
        return len(self._entries)

    def apply(self, text: str) -> str:
        """Return ``text`` with every known correction applied."""
        if not text:
            return text
        with self._lock:
            compiled = list(self._compiled)
        result = text
        for pattern, replacement in compiled:
            try:
                result = pattern.sub(replacement, result)
            except Exception as e:
                logger.debug(f"Correction sub failed: {e}")
        return result

    def _rebuild_compiled(self):
        compiled: list[tuple[re.Pattern, str]] = []
        for entry in self._entries:
            wrong = entry.get("wrong", "")
            right = entry.get("right", "")
            if not wrong:
                continue
            try:
                # Whole-word, case-insensitive match. Wrap in lookarounds
                # so we don't eat punctuation around the match.
                pattern = re.compile(
                    r"(?<![\w])" + re.escape(wrong) + r"(?![\w])",
                    re.IGNORECASE,
                )
                compiled.append((pattern, right))
            except re.error as e:
                logger.debug(f"Failed to compile correction {wrong!r}: {e}")
        self._compiled = compiled
