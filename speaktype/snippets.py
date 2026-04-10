"""Snippet library for frequently used phrases.

Snippets map a short trigger phrase the user speaks (e.g. "我的邮箱") to
a longer block of text that should be inserted in its place. v2.1 adds
two improvements over the v2.0 exact-match implementation:

* **Fuzzy matching** — small punctuation / whitespace / case differences
  are tolerated, and one-token edit distance is allowed for short
  triggers so "我邮箱" still matches "我的邮箱".
* **Dynamic variables** — snippet text may include placeholders like
  ``{date}``, ``{time}``, ``{datetime}``, ``{clipboard}``, and any
  ``{env:NAME}`` lookup. Placeholders are expanded at insertion time.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Optional

from .config import CONFIG_DIR, ensure_config_dir, write_json_file

logger = logging.getLogger("speaktype.snippets")

SNIPPETS_FILE = CONFIG_DIR / "snippets.json"

DEFAULT_SNIPPETS = [
    {"trigger": "my email", "text": "", "description": "Insert your email address"},
    {"trigger": "my phone", "text": "", "description": "Insert your phone number"},
    {"trigger": "best regards", "text": "Best regards,\n", "description": "Email sign-off"},
    {"trigger": "kind regards", "text": "Kind regards,\n", "description": "Email sign-off"},
    {"trigger": "thanks and regards", "text": "Thanks and regards,\n", "description": "Email sign-off"},
    {"trigger": "today's date", "text": "{date}", "description": "Insert today's date"},
    {"trigger": "current time", "text": "{time}", "description": "Insert the current time"},
]


_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_:./-]*)\}")
_NORMALIZE_RE = re.compile(r"[\s,.!?;:'\"，。！？；：、]+")


def _normalize_trigger(text: str) -> str:
    """Lower-case the text and squash punctuation/whitespace differences."""
    if not text:
        return ""
    return _NORMALIZE_RE.sub("", text.lower()).strip()


def _is_close_match(needle: str, haystack: str, max_edits: int = 1) -> bool:
    """Tiny edit-distance check used as a last-resort fuzzy match.

    Only meaningful for short strings — we cap iterations to avoid
    runaway behavior on pathological inputs.
    """
    if not needle or not haystack:
        return False
    if abs(len(needle) - len(haystack)) > max_edits:
        return False
    if needle == haystack:
        return True
    # Levenshtein with two rolling rows. Hard cap on size for safety.
    if max(len(needle), len(haystack)) > 24:
        return False
    prev = list(range(len(haystack) + 1))
    for i, c1 in enumerate(needle, 1):
        curr = [i] + [0] * len(haystack)
        for j, c2 in enumerate(haystack, 1):
            cost = 0 if c1 == c2 else 1
            curr[j] = min(
                curr[j - 1] + 1,         # insertion
                prev[j] + 1,             # deletion
                prev[j - 1] + cost,      # substitution
            )
        prev = curr
    return prev[-1] <= max_edits


def _expand_variables(text: str, *, now: Optional[datetime] = None, clipboard: Optional[str] = None) -> str:
    """Replace ``{var}`` placeholders inside snippet text.

    Supported variables:
        {date}        2026-04-06
        {time}        14:30
        {datetime}    2026-04-06 14:30
        {clipboard}   current pasteboard string contents (lazy)
        {env:NAME}    process environment variable NAME (empty if missing)
    """
    if not text or "{" not in text:
        return text or ""
    now_dt = now or datetime.now()
    cached_clipboard: Optional[str] = clipboard
    clipboard_lookup_done = clipboard is not None

    def _resolve(match: re.Match) -> str:
        nonlocal cached_clipboard, clipboard_lookup_done
        key = match.group(1)
        if key == "date":
            return now_dt.strftime("%Y-%m-%d")
        if key == "time":
            return now_dt.strftime("%H:%M")
        if key == "datetime":
            return now_dt.strftime("%Y-%m-%d %H:%M")
        if key == "clipboard":
            if not clipboard_lookup_done:
                cached_clipboard = _read_clipboard()
                clipboard_lookup_done = True
            return cached_clipboard or ""
        if key.startswith("env:"):
            return os.environ.get(key[4:], "")
        # Unknown placeholder — leave it intact so the user can debug it.
        return match.group(0)

    return _PLACEHOLDER_RE.sub(_resolve, text)


def _contains_sensitive_placeholder(text: str) -> bool:
    """Sensitive placeholders should not be reachable through fuzzy matches."""
    if not text or "{" not in text:
        return False
    for match in _PLACEHOLDER_RE.finditer(text):
        key = match.group(1)
        if key == "clipboard" or key.startswith("env:"):
            return True
    return False


def _read_clipboard() -> str:
    """Best-effort read of the macOS pasteboard. Returns '' on failure."""
    try:
        import AppKit  # type: ignore

        pb = AppKit.NSPasteboard.generalPasteboard()
        return pb.stringForType_(AppKit.NSPasteboardTypeString) or ""
    except Exception as e:
        logger.debug(f"Clipboard read failed during snippet expansion: {e}")
        return ""


class SnippetLibrary:
    def __init__(self):
        self._snippets: list[dict] = []
        self._load()

    # ------------------------------------------------------------------ #
    # Persistence                                                         #
    # ------------------------------------------------------------------ #

    def _load(self):
        ensure_config_dir()
        if SNIPPETS_FILE.exists():
            try:
                with open(SNIPPETS_FILE, encoding="utf-8") as f:
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

    # ------------------------------------------------------------------ #
    # Matching                                                            #
    # ------------------------------------------------------------------ #

    def match(self, text: str, *, fuzzy: bool = True) -> Optional[str]:
        """Find a snippet for ``text`` and return its expanded body.

        Tries exact match (case-insensitive) first, then a normalized
        comparison that strips punctuation/whitespace, then a tiny
        edit-distance fallback for short triggers.
        """
        if not text:
            return None
        spoken = text.strip()
        spoken_lower = spoken.lower()
        spoken_normalized = _normalize_trigger(spoken)

        for snippet in self._snippets:
            trigger = (snippet.get("trigger") or "").strip()
            body = snippet.get("text") or ""
            if not trigger or not body:
                continue
            if trigger.lower() == spoken_lower:
                return _expand_variables(body)

        if not fuzzy:
            return None

        for snippet in self._snippets:
            trigger = (snippet.get("trigger") or "").strip()
            body = snippet.get("text") or ""
            if not trigger or not body:
                continue
            if _contains_sensitive_placeholder(body):
                continue
            trigger_normalized = _normalize_trigger(trigger)
            if not trigger_normalized:
                continue
            if trigger_normalized == spoken_normalized:
                return _expand_variables(body)

        # Last-resort: short triggers, allow 1 edit. Only fire when both
        # sides are short to avoid false positives on long sentences.
        for snippet in self._snippets:
            trigger = (snippet.get("trigger") or "").strip()
            body = snippet.get("text") or ""
            if not trigger or not body:
                continue
            if _contains_sensitive_placeholder(body):
                continue
            trigger_normalized = _normalize_trigger(trigger)
            if not trigger_normalized or len(trigger_normalized) > 12:
                continue
            if _is_close_match(spoken_normalized, trigger_normalized, max_edits=1):
                return _expand_variables(body)

        return None

    # ------------------------------------------------------------------ #
    # CRUD                                                                #
    # ------------------------------------------------------------------ #

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
