"""Local adaptive hotword storage and context selection.

Hotwords are learned terminology hints, not unconditional replacements.
They bias future ASR and protect spelling during local LLM polish, while
correction rules remain a separate layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
import math
import re
import threading
from pathlib import Path
from typing import Iterable, Optional

from .config import CONFIG_DIR, ensure_config_dir, write_json_file

logger = logging.getLogger("speaktype.hotwords")

HOTWORDS_FILE = CONFIG_DIR / "hotwords.json"

MAX_TERM_CHARS = 80
MAX_ALIAS_CHARS = 80
MAX_ALIASES_PER_TERM = 8
MAX_EVIDENCE_ITEMS = 4
DEFAULT_ACTIVE_CONFIDENCE = 0.78
DEFAULT_REPEAT_PROMOTION_COUNT = 2

_SPACE_RE = re.compile(r"\s+")
_TECH_SIGNAL_RE = re.compile(r"[A-Z]{2,}|[a-z][A-Z]|[A-Za-z]+[0-9]|[0-9][A-Za-z]|[-_./+#]")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_SENTENCE_PUNCT_RE = re.compile(r"[，。！？；：、,!?;:]")
_ASCII_ACRONYM_RE = re.compile(r"^[A-Za-z]{2,12}$")


@dataclass(frozen=True)
class ActiveHotwordContext:
    """Selected hotwords for one recognition turn."""

    terms: list[str]
    context: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value: str, max_chars: int) -> str:
    value = _CONTROL_RE.sub("", str(value or "")).strip()
    value = _SPACE_RE.sub(" ", value)
    return value[:max_chars].strip()


def _term_key(term: str) -> str:
    return _SPACE_RE.sub(" ", (term or "").strip().casefold())


def _match_key(text: str) -> str:
    text = _CONTROL_RE.sub("", str(text or "")).casefold()
    return _SPACE_RE.sub("", text)


def _text_contains_term(text: str, term: str) -> bool:
    text = _clean_text(text, 4000)
    term = _clean_text(term, MAX_TERM_CHARS)
    if not text or not term:
        return False
    if term.casefold() in text.casefold():
        return True
    return _match_key(term) in _match_key(text)


def _is_sentence_like_term(term: str) -> bool:
    term = _clean_text(term, MAX_TERM_CHARS)
    if not term:
        return True
    if "\n" in term or "\r" in term:
        return True
    if _SENTENCE_PUNCT_RE.search(term):
        return True
    if term.endswith(".") and not re.search(r"\.[A-Za-z0-9]+$", term):
        return True
    return False


def _looks_like_hotword(term: str) -> bool:
    term = (term or "").strip()
    if len(term) < 2 or len(term) > MAX_TERM_CHARS:
        return False
    if _is_sentence_like_term(term):
        return False
    if _TECH_SIGNAL_RE.search(term):
        return True
    # CJK names / project names are often short and carry no ASCII casing signal.
    cjk_count = sum(1 for ch in term if "\u3400" <= ch <= "\u9fff")
    return 2 <= cjk_count <= 12


def _looks_like_reusable_correction(wrong: str, right: str) -> bool:
    wrong = _clean_text(wrong, 100)
    right = _clean_text(right, 100)
    if not wrong or not right:
        return False
    if _looks_like_hotword(right):
        cjk_count = sum(1 for ch in right if "\u3400" <= ch <= "\u9fff")
        if cjk_count and cjk_count < 3 and not _TECH_SIGNAL_RE.search(right):
            return False
        return True
    if _ASCII_ACRONYM_RE.fullmatch(right) and re.search(r"\s", wrong):
        return True
    return False


def _clean_aliases(aliases: Iterable[str] | None, term: str) -> list[str]:
    seen = {_term_key(term)}
    cleaned: list[str] = []
    for alias in aliases or []:
        value = _clean_text(str(alias), MAX_ALIAS_CHARS)
        key = _term_key(value)
        if not value or key in seen:
            continue
        seen.add(key)
        cleaned.append(value)
        if len(cleaned) >= MAX_ALIASES_PER_TERM:
            break
    return cleaned


def _bounded_confidence(value, default: float = 0.5) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = default
    if math.isnan(result) or math.isinf(result):
        result = default
    return max(0.0, min(1.0, result))


def _increment_counter(mapping: dict, key: str):
    key = str(key or "").strip()
    if not key:
        return
    mapping[key] = int(mapping.get(key, 0) or 0) + 1


class HotwordStore:
    """Persistent, local-only collection of learned hotwords."""

    def __init__(self, path: Optional[Path] = None):
        self._path = path or HOTWORDS_FILE
        self._entries: list[dict] = []
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        ensure_config_dir()
        if not self._path.exists():
            self._entries = []
            return
        with open(self._path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list) or any(not isinstance(entry, dict) for entry in data):
            raise ValueError(f"Hotwords must be a list of objects: {self._path}")
        self._entries = [self._normalize_entry(entry) for entry in data]

    def _save(self):
        write_json_file(self._path, self._entries)

    def _normalize_entry(self, entry: dict) -> dict:
        if not isinstance(entry.get("term"), str) or not entry["term"].strip():
            raise ValueError("Hotword term must be a nonempty string")
        observations = entry.get("observations", 0)
        if isinstance(observations, bool) or not isinstance(observations, int) or observations < 0:
            raise ValueError("Hotword observations must be a nonnegative integer")
        aliases = entry.get("aliases", [])
        if not isinstance(aliases, list) or any(not isinstance(alias, str) for alias in aliases):
            raise ValueError("Hotword aliases must be a list of strings")
        if not isinstance(entry.get("active", False), bool):
            raise ValueError("Hotword active must be true or false")
        confidence = entry.get("confidence", 0.5)
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence):
            raise ValueError("Hotword confidence must be a finite number")
        for field in ("apps", "scenes", "languages"):
            counters = entry.get(field, {})
            if not isinstance(counters, dict) or any(
                not isinstance(key, str) or isinstance(count, bool)
                or not isinstance(count, int) or count < 0 for key, count in counters.items()
            ):
                raise ValueError(f"Hotword {field} must contain nonnegative integer counts")
        evidence = entry.get("evidence", [])
        if not isinstance(evidence, list) or any(not isinstance(item, dict) for item in evidence):
            raise ValueError("Hotword evidence must be a list of objects")
        term = _clean_text(entry.get("term", ""), MAX_TERM_CHARS)
        aliases = _clean_aliases(entry.get("aliases") or [], term)
        observations = max(0, int(entry.get("observations", 0) or 0))
        confidence = _bounded_confidence(entry.get("confidence"), default=0.5)
        active = bool(entry.get("active", False))
        return {
            "term": term,
            "key": _term_key(term),
            "aliases": aliases,
            "confidence": confidence,
            "active": active,
            "observations": observations,
            "created_at": str(entry.get("created_at") or _now_iso()),
            "updated_at": str(entry.get("updated_at") or _now_iso()),
            "last_seen_at": str(entry.get("last_seen_at") or _now_iso()),
            "source": str(entry.get("source") or "post_edit"),
            "apps": dict(entry.get("apps") or {}),
            "scenes": dict(entry.get("scenes") or {}),
            "languages": dict(entry.get("languages") or {}),
            "evidence": list(entry.get("evidence") or [])[-MAX_EVIDENCE_ITEMS:],
        }

    def get_all(self) -> list[dict]:
        with self._lock:
            return deepcopy(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def add_or_reinforce(
        self,
        term: str,
        aliases: Iterable[str] | None = None,
        *,
        confidence: float = 0.5,
        app_info: Optional[dict] = None,
        scene: str = "",
        language: str = "",
        source: str = "post_edit",
        raw_fragment: str = "",
        edited_fragment: str = "",
        active_confidence: float = DEFAULT_ACTIVE_CONFIDENCE,
        repeat_promotion_count: int = DEFAULT_REPEAT_PROMOTION_COUNT,
    ) -> dict | None:
        """Add or update a learned hotword and return the stored entry."""
        term = _clean_text(term, MAX_TERM_CHARS)
        if not _looks_like_hotword(term):
            return None
        key = _term_key(term)
        now = _now_iso()
        confidence = _bounded_confidence(confidence)
        aliases = _clean_aliases(aliases, term)
        app_info = app_info or {}
        app_name = str(app_info.get("name", "") or "")
        bundle_id = str(app_info.get("bundle_id", "") or "")

        evidence = {
            "raw": _clean_text(raw_fragment, 120),
            "edited": _clean_text(edited_fragment, 120),
            "app": app_name[:80],
            "scene": str(scene or "")[:40],
            "timestamp": now,
        }

        with self._lock:
            entry = next((e for e in self._entries if e.get("key") == key), None)
            if entry is None:
                entry = {
                    "term": term,
                    "key": key,
                    "aliases": aliases,
                    "confidence": confidence,
                    "active": False,
                    "observations": 0,
                    "created_at": now,
                    "updated_at": now,
                    "last_seen_at": now,
                    "source": source,
                    "apps": {},
                    "scenes": {},
                    "languages": {},
                    "evidence": [],
                }
                self._entries.append(entry)
            else:
                existing_aliases = _clean_aliases(entry.get("aliases", []), term)
                merged_aliases = existing_aliases + [
                    alias for alias in aliases if _term_key(alias) not in {_term_key(a) for a in existing_aliases}
                ]
                entry["aliases"] = merged_aliases[:MAX_ALIASES_PER_TERM]
                previous_confidence = _bounded_confidence(entry.get("confidence"), default=0.5)
                entry["confidence"] = round(max(previous_confidence, confidence), 3)
                entry["updated_at"] = now
                entry["last_seen_at"] = now

            entry["observations"] = int(entry.get("observations", 0) or 0) + 1
            _increment_counter(entry.setdefault("apps", {}), bundle_id or app_name)
            _increment_counter(entry.setdefault("scenes", {}), scene)
            _increment_counter(entry.setdefault("languages", {}), language)
            if evidence["raw"] or evidence["edited"]:
                entry.setdefault("evidence", []).append(evidence)
                entry["evidence"] = entry["evidence"][-MAX_EVIDENCE_ITEMS:]
            if confidence >= active_confidence or entry["observations"] >= repeat_promotion_count:
                entry["active"] = True
            stored = deepcopy(entry)
            self._save()
        return stored

    def learn_from_payload(
        self,
        payload: dict,
        *,
        app_info: Optional[dict] = None,
        scene: str = "",
        language: str = "",
        raw_text: str = "",
        edited_text: str = "",
    ) -> list[dict]:
        """Persist hotwords from a local model learning payload."""
        if not isinstance(payload, dict) or payload.get("learn") is False:
            return []
        edited_text = _clean_text(edited_text, 4000)
        learned: list[dict] = []
        for item in payload.get("hotwords") or []:
            if not isinstance(item, dict):
                continue
            term = _clean_text(item.get("term", ""), MAX_TERM_CHARS)
            if edited_text and not _text_contains_term(edited_text, term):
                logger.debug("Rejected learned hotword not present in edited text: %s", term)
                continue
            entry = self.add_or_reinforce(
                term,
                item.get("aliases") or [],
                confidence=item.get("confidence", 0.5),
                app_info=app_info,
                scene=scene,
                language=language,
                source="post_edit",
                raw_fragment=raw_text,
                edited_fragment=edited_text,
            )
            if entry is not None:
                learned.append(entry)
        return learned

    def active_context(
        self,
        *,
        app_info: Optional[dict] = None,
        scene: str = "",
        language: str = "",
        limit: int = 30,
        max_chars: int = 800,
    ) -> ActiveHotwordContext:
        """Build a compact context string for the next ASR request."""
        app_info = app_info or {}
        app_keys = {
            str(app_info.get("bundle_id", "") or ""),
            str(app_info.get("name", "") or ""),
        }
        app_keys.discard("")
        scene = str(scene or "")
        language = str(language or "")
        with self._lock:
            entries = [dict(e) for e in self._entries if e.get("active") and e.get("term")]

        def score(entry: dict) -> float:
            value = _bounded_confidence(entry.get("confidence"), default=0.5)
            value += min(int(entry.get("observations", 0) or 0), 5) * 0.04
            apps = entry.get("apps") or {}
            scenes = entry.get("scenes") or {}
            languages = entry.get("languages") or {}
            if any(apps.get(k) for k in app_keys):
                value += 0.25
            if scene and scenes.get(scene):
                value += 0.18
            if language and language != "auto" and languages.get(language):
                value += 0.08
            return value

        terms: list[str] = []
        total_chars = 0
        for entry in sorted(entries, key=score, reverse=True):
            term = str(entry.get("term") or "").strip()
            if not term:
                continue
            extra = len(term) + (1 if terms else 0)
            if len(terms) >= limit or total_chars + extra > max_chars:
                break
            terms.append(term)
            total_chars += extra
        return ActiveHotwordContext(terms=terms, context=" ".join(terms))


def extract_confident_corrections(
    payload: dict,
    *,
    min_confidence: float = 0.86,
    raw_text: str = "",
    inserted_text: str = "",
    edited_text: str = "",
) -> list[dict]:
    """Return conservative correction candidates from a learning payload."""
    if not isinstance(payload, dict) or payload.get("learn") is False:
        return []
    corrections: list[dict] = []
    seen: set[tuple[str, str]] = set()
    source_text = f"{raw_text or ''}\n{inserted_text or ''}"
    has_context = bool((source_text or "").strip() or (edited_text or "").strip())
    for item in payload.get("corrections") or []:
        if not isinstance(item, dict):
            continue
        wrong = _clean_text(item.get("wrong", ""), 100)
        right = _clean_text(item.get("right", ""), 100)
        confidence = _bounded_confidence(item.get("confidence"), default=0.0)
        key = (_term_key(wrong), _term_key(right))
        if not wrong or not right or key in seen:
            continue
        if confidence < min_confidence:
            continue
        if len(wrong) < 3 or len(right) < 2:
            continue
        if wrong.casefold() == right.casefold():
            continue
        if has_context:
            if not _text_contains_term(source_text, wrong):
                continue
            if not _text_contains_term(edited_text, right):
                continue
        if not _looks_like_reusable_correction(wrong, right):
            continue
        seen.add(key)
        corrections.append({"wrong": wrong, "right": right, "confidence": confidence})
    return corrections
