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
        self._compiled: re.Pattern | None = None
        self._replacements: dict[str, str] = {}
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
        with open(self._path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError(f"Corrections must be a JSON list: {self._path}")
        if any(not isinstance(e, dict) or not isinstance(e.get("wrong"), str)
               or not isinstance(e.get("right"), str) for e in data):
            raise ValueError(f"Invalid correction entries in {self._path}")
        self._entries = [{"wrong": e["wrong"], "right": e["right"]} for e in data if e["wrong"]]
        self._rebuild_compiled()

    def _commit_entries(self, entries):
        write_json_file(self._path, entries)
        self._entries = entries
        self._rebuild_compiled()

    # ------------------------------------------------------------------ #
    # Mutations                                                          #
    # ------------------------------------------------------------------ #

    def add(self, wrong: str, right: str):
        wrong = (wrong or "").strip()
        right = (right or "").strip()
        if not wrong:
            return
        with self._lock:
            entries = [dict(entry) for entry in self._entries]
            for entry in entries:
                if entry.get("wrong", "").lower() == wrong.lower():
                    entry["right"] = right
                    break
            else:
                entries.append({"wrong": wrong, "right": right})
            self._commit_entries(entries)

    def remove(self, wrong: str):
        wrong = (wrong or "").strip().lower()
        with self._lock:
            entries = [
                e for e in self._entries if e.get("wrong", "").lower() != wrong
            ]
            self._commit_entries(entries)

    def clear(self):
        with self._lock:
            self._commit_entries([])

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
            self._commit_entries(cleaned)

    # ------------------------------------------------------------------ #
    # Lookup                                                              #
    # ------------------------------------------------------------------ #

    def get_all(self) -> list[dict]:
        with self._lock:
            return [dict(e) for e in self._entries]

    def __len__(self) -> int:
        return len(self._entries)

    def apply(self, text: str) -> str:
        return self.apply_with_changes(text)[0]

    def apply_with_changes(self, text: str) -> tuple[str, list[dict]]:
        if not text:
            return text, []
        with self._lock:
            compiled = self._compiled
            replacements = dict(self._replacements)
        if compiled is None:
            return text, []
        changes = []

        def replace(match):
            original = match.group(0)
            replacement = replacements[match.lastgroup]
            if original != replacement:
                changes.append({"original": original, "replacement": replacement})
            return replacement

        return compiled.sub(replace, text), changes

    def _rebuild_compiled(self):
        expressions: list[str] = []
        replacements: dict[str, str] = {}
        seen = set()
        for entry in sorted(self._entries, key=lambda item: len(item.get("wrong", "")), reverse=True):
            wrong = entry.get("wrong", "")
            right = entry.get("right", "")
            if not wrong or wrong.casefold() in seen:
                continue
            seen.add(wrong.casefold())
            pattern = re.escape(wrong)
            if re.search(r"[A-Za-z0-9]", wrong):
                pattern = (r"(?<![A-Za-z0-9_])" + pattern + r"(?![A-Za-z0-9_])"
                           r"(?!['’](?:t|re|ve|ll|d|m)(?![A-Za-z0-9_]))")
            group = f"c{len(expressions)}"
            expressions.append(f"(?P<{group}>{pattern})")
            replacements[group] = right
        self._compiled = re.compile("|".join(expressions), re.IGNORECASE) if expressions else None
        self._replacements = replacements
