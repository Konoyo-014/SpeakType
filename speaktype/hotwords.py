from __future__ import annotations

from dataclasses import dataclass, field
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
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
CONTEXT_PREFIX = "Vocabulary: "
CONTEXT_SUFFIX = "."

_SPACE_RE = re.compile(r"\s+")
_TECH_SIGNAL_RE = re.compile(r"[A-Z]{2,}|[a-z][A-Z]|[A-Za-z]+[0-9]|[0-9][A-Za-z]|[-_./+#]")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_SENTENCE_PUNCT_RE = re.compile(r"[，。！？；：、,!?;:]")
_ASCII_ACRONYM_RE = re.compile(r"^[A-Za-z]{2,12}$")
_IGNORECASE_EQUIVALENTS = str.maketrans({"İ": "i", "ı": "i", "ſ": "s", "K": "k"})
_MISSING = object()


@dataclass(frozen=True)
class ActiveHotwordContext:
    """Selected hotwords for one recognition turn."""

    terms: list[str]
    context: str
    entries: list[dict] = field(default_factory=list)
    eligible_count: int = 0
    omitted_terms: list[str] = field(default_factory=list)
    selection_reasons: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class HotwordChange:
    original: str
    replacement: str
    term: str


@dataclass(frozen=True)
class HotwordApplication:
    text: str
    changes: list[HotwordChange] = field(default_factory=list)


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


def _candidate_match_key(text: str) -> str:
    return _match_key(text.translate(_IGNORECASE_EQUIVALENTS))


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
    if re.fullmatch(r"[A-Z][a-z]+(?: [A-Z][a-z]+)*", term):
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


def _entry_applies(entry: dict, app_info: dict, scene: str) -> bool:
    app_scope = str(entry.get("scope_app") or "").casefold()
    app_keys = {str(app_info.get(key) or "").casefold() for key in ("name", "bundle_id")}
    scene_scope = str(entry.get("scope_scene") or "")
    return (not app_scope or app_scope in app_keys) and (not scene_scope or scene_scope == scene)


def _replacement_pattern(value: str, *, canonical: bool) -> str:
    parts = [part for part in re.split(r"(\s+|[-_./+#])", value) if part]
    expression = "".join(
        r"\s+" if part.isspace() else
        (r"[ \t]*" if index else "") + re.escape(part) + (r"[ \t]*" if index < len(parts) - 1 else "")
        if canonical and len(part) == 1 and part in "-_./+#" else
        re.escape(part)
        for index, part in enumerate(parts)
    )
    if re.search(r"[A-Za-z0-9]", value):
        expression = (r"(?<![A-Za-z0-9_])" + expression + r"(?![A-Za-z0-9_])"
                      r"(?!['’](?:t|re|ve|ll|d|m)(?![A-Za-z0-9_]))")
    return expression


@lru_cache(maxsize=32)
def _compiled_replacements(values: tuple[tuple[str, str, bool], ...]):
    pattern = re.compile("|".join(
        f"(?P<h{index}>{_replacement_pattern(value, canonical=canonical)})"
        for index, (value, _, canonical) in enumerate(values)
    ), re.IGNORECASE)
    return pattern, {f"h{index}": term for index, (_, term, _) in enumerate(values)}


def _validate_usage_metadata(entry: dict) -> dict:
    usage_count = entry.get("usage_count", 0)
    if isinstance(usage_count, bool) or not isinstance(usage_count, int) or usage_count < 0:
        raise ValueError("Hotword usage_count must be a nonnegative integer")
    last_used_at = entry.get("last_used_at", "")
    if not isinstance(last_used_at, str):
        raise ValueError("Hotword last_used_at must be a string")
    if last_used_at:
        timestamp = datetime.fromisoformat(last_used_at.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("Hotword last_used_at must include a timezone")
        last_used_at = timestamp.astimezone(timezone.utc).isoformat()
    usage_apps = entry.get("usage_apps", {})
    if not isinstance(usage_apps, dict) or any(
        not isinstance(key, str) or isinstance(count, bool)
        or not isinstance(count, int) or count < 0 for key, count in usage_apps.items()
    ):
        raise ValueError("Hotword usage_apps must contain nonnegative integer counts")
    return {"usage_count": usage_count, "last_used_at": last_used_at, "usage_apps": dict(usage_apps)}


def _alias_metadata(aliases: list[str], *, confidence: float, source: str,
                    user_confirmed: bool, approved_aliases=_MISSING,
                    alias_confidences=_MISSING) -> tuple[list[str], dict[str, float]]:
    known = {_term_key(alias): alias for alias in aliases}
    if approved_aliases is _MISSING:
        approved_aliases = aliases if source in ("manual", "dictionary") or user_confirmed else []
    if not isinstance(approved_aliases, list) or any(not isinstance(alias, str) for alias in approved_aliases):
        raise ValueError("Approved hotword aliases must be a list of strings")
    approved_keys = {_term_key(alias) for alias in approved_aliases}
    if not approved_keys.issubset(known):
        raise ValueError("Approved hotword aliases must exist in aliases")
    if alias_confidences is _MISSING:
        alias_confidences = {}
    if not isinstance(alias_confidences, dict):
        raise ValueError("Hotword alias confidences must be an object")
    scores = {}
    for alias, score in alias_confidences.items():
        if not isinstance(alias, str) or _term_key(alias) not in known:
            raise ValueError("Hotword alias confidence keys must exist in aliases")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError("Hotword alias confidence must be a finite number from zero to one")
        canonical = known[_term_key(alias)]
        if canonical in scores:
            raise ValueError("Duplicate hotword alias confidence")
        scores[canonical] = float(score)
    return ([alias for alias in aliases if _term_key(alias) in approved_keys],
            {alias: scores.get(alias, confidence) for alias in aliases})


def validate_manual_hotword(term: str, aliases: Iterable[str] = (), *, enabled: bool = True,
                            scope_app: str = "", scope_scene: str = "", pinned: bool = False) -> dict:
    if not isinstance(term, str) or not 2 <= len(term.strip()) <= MAX_TERM_CHARS:
        raise ValueError(f"Hotword term must contain 2 to {MAX_TERM_CHARS} characters")
    if _CONTROL_RE.search(term) or "\n" in term or "\r" in term or _is_sentence_like_term(term):
        raise ValueError("Hotword term must be a word or short name")
    if not isinstance(enabled, bool):
        raise TypeError("Hotword enabled must be true or false")
    if not isinstance(pinned, bool):
        raise TypeError("Hotword pinned must be true or false")
    if isinstance(aliases, str):
        raise TypeError("Hotword aliases must be a collection of strings")
    aliases = list(aliases)
    if len(aliases) > MAX_ALIASES_PER_TERM or any(
        not isinstance(alias, str) or len(alias.strip()) > MAX_ALIAS_CHARS
        or "\n" in alias or "\r" in alias or _CONTROL_RE.search(alias)
        for alias in aliases
    ):
        raise ValueError("Hotword aliases contain invalid values")
    if not isinstance(scope_app, str) or not isinstance(scope_scene, str):
        raise TypeError("Hotword scopes must be strings")
    if len(scope_app.strip()) > 200 or len(scope_scene.strip()) > 80:
        raise ValueError("Hotword application or scene scope is too long")
    if _CONTROL_RE.search(scope_app + scope_scene) or any(ch in scope_app + scope_scene for ch in "\r\n"):
        raise ValueError("Hotword scopes must occupy a single line")
    term = _clean_text(term, MAX_TERM_CHARS)
    cleaned_aliases = _clean_aliases(aliases, term)
    return {"term": term, "key": _term_key(term), "aliases": cleaned_aliases,
            "active": enabled, "user_disabled": not enabled,
            "user_confirmed": True, "user_deleted": False,
            "approved_aliases": list(cleaned_aliases),
            "alias_confidences": {alias: 1.0 for alias in cleaned_aliases},
            "scope_app": scope_app.strip(), "scope_scene": scope_scene.strip(),
            "confidence": 1.0, "source": "manual", "pinned": pinned}


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

    def _save(self, entries):
        write_json_file(self._path, entries)
        self._entries = entries

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
        if not isinstance(entry.get("user_disabled", False), bool):
            raise ValueError("Hotword user_disabled must be true or false")
        if not isinstance(entry.get("user_confirmed", False), bool):
            raise ValueError("Hotword user_confirmed must be true or false")
        if not isinstance(entry.get("user_deleted", False), bool):
            raise ValueError("Hotword user_deleted must be true or false")
        if not isinstance(entry.get("pinned", False), bool):
            raise ValueError("Hotword pinned must be true or false")
        usage = _validate_usage_metadata(entry)
        for scope_field in ("scope_app", "scope_scene"):
            if not isinstance(entry.get(scope_field, ""), str):
                raise ValueError(f"Hotword {scope_field} must be a string")
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
        source = str(entry.get("source") or "post_edit")
        approved_aliases, alias_confidences = _alias_metadata(
            aliases, confidence=confidence, source=source, user_confirmed=entry.get("user_confirmed", False),
            approved_aliases=entry.get("approved_aliases", _MISSING),
            alias_confidences=entry.get("alias_confidences", _MISSING),
        )
        deleted = entry.get("user_deleted", False)
        active = bool(entry.get("active", False)) and not entry.get("user_disabled", False) and not deleted
        return {
            "term": term,
            "key": _term_key(term),
            "aliases": aliases,
            "confidence": confidence,
            "active": active,
            "user_disabled": entry.get("user_disabled", False) or deleted,
            "user_confirmed": entry.get("user_confirmed", False),
            "user_deleted": deleted,
            "pinned": entry.get("pinned", False),
            **usage,
            "approved_aliases": approved_aliases,
            "alias_confidences": alias_confidences,
            "scope_app": _clean_text(entry.get("scope_app", ""), 200),
            "scope_scene": _clean_text(entry.get("scope_scene", ""), 80),
            "observations": observations,
            "created_at": str(entry.get("created_at") or _now_iso()),
            "updated_at": str(entry.get("updated_at") or _now_iso()),
            "last_seen_at": str(entry.get("last_seen_at") or _now_iso()),
            "source": source,
            "apps": dict(entry.get("apps") or {}),
            "scenes": dict(entry.get("scenes") or {}),
            "languages": dict(entry.get("languages") or {}),
            "evidence": list(entry.get("evidence") or [])[-MAX_EVIDENCE_ITEMS:],
        }

    def _dictionary_entries(self, dictionary, stored_keys):
        entries = []
        seen = set(stored_keys)
        for word in dictionary:
            if not isinstance(word, str):
                raise TypeError("Dictionary words must be strings")
            term = _clean_text(word, MAX_TERM_CHARS)
            key = _term_key(term)
            if not term or key in seen:
                continue
            seen.add(key)
            entry = self._normalize_entry({"term": term, "source": "dictionary", "active": True,
                                           "confidence": 1.0, "user_confirmed": True})
            entry.update(created_at="", updated_at="", last_seen_at="")
            entries.append(entry)
        return entries

    def _find_entry(self, entries, key, dictionary=()):
        entry = next((item for item in entries if item["key"] == key), None)
        if entry is None:
            legacy = next((item for item in self._dictionary_entries(dictionary, {item["key"] for item in entries})
                           if item["key"] == key), None)
            if legacy is not None:
                entry = self._normalize_entry(legacy)
                entries.append(entry)
        return entry

    def _deleted_entry(self, term, timestamp):
        return self._normalize_entry({"term": term, "source": "manual", "confidence": 0.0,
                                      "active": False, "user_disabled": True, "user_deleted": True,
                                      "created_at": timestamp, "updated_at": timestamp, "last_seen_at": timestamp})

    def get_all(self, *, dictionary: Iterable[str] = (), include_deleted: bool = False) -> list[dict]:
        if not isinstance(include_deleted, bool):
            raise TypeError("include_deleted must be true or false")
        with self._lock:
            entries = deepcopy(self._entries)
        visible = [entry for entry in entries if include_deleted or not entry.get("user_deleted")]
        return visible + self._dictionary_entries(dictionary, {entry["key"] for entry in entries})

    def __len__(self) -> int:
        with self._lock:
            return sum(1 for entry in self._entries if not entry.get("user_deleted"))

    def upsert_manual(self, term: str, aliases: Iterable[str] = (), *,
                      original_term: str | None = None, enabled: bool = True,
                      scope_app: str = "", scope_scene: str = "", dictionary: Iterable[str] = (),
                      pinned: bool | None = None) -> dict:
        values = validate_manual_hotword(term, aliases, enabled=enabled,
                                         scope_app=scope_app, scope_scene=scope_scene,
                                         pinned=False if pinned is None else pinned)
        if pinned is None:
            values.pop("pinned")
        term, key = values["term"], values["key"]
        original_key = _term_key(original_term) if original_term is not None else key
        now = _now_iso()
        with self._lock:
            entries = deepcopy(self._entries)
            entry = self._find_entry(entries, original_key, dictionary)
            if original_term is not None and entry is None:
                raise KeyError(f"Hotword does not exist: {original_term}")
            duplicate = next((item for item in entries if item["key"] == key and item is not entry), None)
            if duplicate is not None and not duplicate.get("user_deleted"):
                raise ValueError(f"Hotword already exists: {term}")
            if duplicate is not None:
                entries.remove(duplicate)
            if entry is not None and entry.get("user_deleted"):
                index = entries.index(entry)
                entry = self._normalize_entry({"term": entry["term"], "source": "manual"})
                entries[index] = entry
            if entry is None:
                entry = self._normalize_entry({"term": term, "source": "manual"})
                entries.append(entry)
            elif original_key != key:
                previous = self._deleted_entry(entry["term"], now)
                entries.remove(entry)
                entries.append(previous)
                entry = deepcopy(entry)
                entries.append(entry)
            entry.update(**values, updated_at=now)
            self._save(entries)
            return deepcopy(entry)

    def import_manual(self, entries: list[dict]) -> int:
        if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
            raise TypeError("Hotword import must be a list of objects")
        validated = []
        seen = set()
        for entry in entries:
            state = entry.get("state")
            if "state" in entry and state not in ("pending", "active", "disabled"):
                raise ValueError("Hotword state must be pending, active or disabled")
            for enabled_field in ("enabled", "active"):
                if enabled_field in entry and not isinstance(entry[enabled_field], bool):
                    raise TypeError("Hotword enabled must be true or false")
            if "enabled" in entry and "active" in entry and entry["enabled"] != entry["active"]:
                raise ValueError("Hotword enabled and active fields disagree")
            explicit_enabled = entry.get("enabled", entry.get("active"))
            if explicit_enabled is not None and not isinstance(explicit_enabled, bool):
                raise TypeError("Hotword enabled must be true or false")
            if state is not None and explicit_enabled is not None and explicit_enabled != (state == "active"):
                raise ValueError("Hotword state and enabled fields disagree")
            values = validate_manual_hotword(
                entry.get("term"), entry.get("aliases", []),
                enabled=(state == "active") if state is not None else entry.get("enabled", entry.get("active", True)),
                scope_app=entry.get("scope_app", ""), scope_scene=entry.get("scope_scene", ""),
                pinned=entry.get("pinned", False),
            )
            if "pinned" not in entry:
                values.pop("pinned")
            if state == "pending":
                values["user_disabled"] = False
                values["user_confirmed"] = False
                values["source"] = "imported"
                values["confidence"] = 0.5
                values["approved_aliases"] = []
                values["alias_confidences"] = {alias: 0.5 for alias in values["aliases"]}
            metadata = {}
            usage = _validate_usage_metadata(entry)
            metadata.update({key: value for key, value in usage.items() if key in entry})
            if "user_confirmed" in entry:
                if not isinstance(entry["user_confirmed"], bool):
                    raise TypeError("Hotword user_confirmed must be true or false")
                if state == "pending" and entry["user_confirmed"]:
                    raise ValueError("Pending hotwords cannot already be user confirmed")
                metadata["user_confirmed"] = entry["user_confirmed"]
            if "confidence" in entry:
                confidence = entry["confidence"]
                if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
                    raise ValueError("Hotword confidence must be a finite number from zero to one")
                metadata["confidence"] = confidence
            if "observations" in entry:
                observations = entry["observations"]
                if isinstance(observations, bool) or not isinstance(observations, int) or observations < 0:
                    raise ValueError("Hotword observations must be a nonnegative integer")
                metadata["observations"] = observations
            if "source" in entry:
                if entry["source"] not in ("manual", "post_edit", "imported"):
                    raise ValueError("Hotword source must be manual, post_edit or imported")
                if state == "pending" and entry["source"] == "manual":
                    raise ValueError("Pending hotwords must retain a learning source")
                metadata["source"] = entry["source"]
            for alias_field in ("approved_aliases", "alias_confidences"):
                if alias_field in entry:
                    metadata[alias_field] = deepcopy(entry[alias_field])
            if values["key"] in seen:
                raise ValueError(f"Duplicate imported hotword: {values['term']}")
            seen.add(values["key"])
            validated.append((values, state == "pending", metadata))
        with self._lock:
            merged = deepcopy(self._entries)
            for values, pending, metadata in validated:
                entry = next((item for item in merged if item["key"] == values["key"]), None)
                previous = entry if entry is not None and not entry.get("user_deleted") else None
                if pending and previous is not None:
                    values["confidence"] = previous["confidence"]
                    values["source"] = previous["source"] if previous["source"] not in ("manual", "dictionary") else "imported"
                values.update(metadata)
                if "user_confirmed" not in metadata and values["source"] != "manual":
                    values["user_confirmed"] = bool(not pending and previous and previous.get("user_confirmed"))
                approved = metadata.get("approved_aliases", _MISSING)
                if approved is _MISSING and values["source"] != "manual":
                    if pending:
                        approved = []
                    elif metadata.get("user_confirmed"):
                        approved = list(values["aliases"])
                    else:
                        approved_keys = {_term_key(alias) for alias in (previous or {}).get("approved_aliases", [])}
                        approved = [alias for alias in values["aliases"] if _term_key(alias) in approved_keys]
                scores = metadata.get("alias_confidences", _MISSING)
                if scores is _MISSING and "confidence" in metadata:
                    scores = {alias: values["confidence"] for alias in values["aliases"]}
                elif scores is _MISSING and values["source"] != "manual" and previous is not None:
                    previous_scores = {_term_key(alias): score for alias, score in previous.get("alias_confidences", {}).items()}
                    scores = {alias: previous_scores.get(_term_key(alias), values["confidence"]) for alias in values["aliases"]}
                values["approved_aliases"], values["alias_confidences"] = _alias_metadata(
                    values["aliases"], confidence=values["confidence"], source=values["source"],
                    user_confirmed=values["user_confirmed"], approved_aliases=approved,
                    alias_confidences=scores,
                )
                if pending and values["approved_aliases"]:
                    raise ValueError("Pending hotwords cannot contain approved aliases")
                values["user_deleted"] = False
                if entry is None:
                    entry = self._normalize_entry(values)
                    merged.append(entry)
                elif entry.get("user_deleted"):
                    index = merged.index(entry)
                    entry = self._normalize_entry(values)
                    merged[index] = entry
                entry.update(**values, updated_at=_now_iso())
            self._save(merged)
        return len(validated)

    def set_active(self, term: str, enabled: bool, *, dictionary: Iterable[str] = ()) -> bool:
        if not isinstance(enabled, bool):
            raise TypeError("Hotword enabled must be true or false")
        with self._lock:
            entries = deepcopy(self._entries)
            entry = self._find_entry(entries, _term_key(term), dictionary)
            if entry is None or entry.get("user_deleted"):
                return False
            entry.update(active=enabled, user_disabled=not enabled, updated_at=_now_iso())
            if enabled:
                entry["user_confirmed"] = True
                entry["approved_aliases"] = list(entry["aliases"])
            self._save(entries)
            return True

    def remove(self, term: str, *, dictionary: Iterable[str] = ()) -> bool:
        key = _term_key(term)
        with self._lock:
            entries = deepcopy(self._entries)
            entry = self._find_entry(entries, key, dictionary)
            if entry is None or entry.get("user_deleted"):
                return False
            entries[entries.index(entry)] = self._deleted_entry(entry["term"], _now_iso())
            self._save(entries)
            return True

    def apply(self, text: str, *, app_info: Optional[dict] = None, scene: str = "",
              dictionary: Iterable[str] = (), learned_corrections_enabled: bool = True) -> HotwordApplication:
        if not isinstance(learned_corrections_enabled, bool):
            raise TypeError("Learned corrections enabled must be true or false")
        if not text:
            return HotwordApplication(text=text)
        entries = self._applicable_entries(app_info or {}, scene, dictionary)
        candidates: dict[str, list[tuple[str, str, bool]]] = {}
        canonical_keys = {_match_key(entry["term"]): entry["term"] for entry in entries}
        text_key = _candidate_match_key(text)
        for entry in entries:
            term = entry["term"]
            approved_keys = {_term_key(alias) for alias in entry.get("approved_aliases", [])}
            values = [(term, True)] + [
                (alias, False) for alias in entry.get("aliases", [])
                if _term_key(alias) in approved_keys or (
                    learned_corrections_enabled and entry.get("alias_confidences", {}).get(alias, 0.0) >= 0.86
                )
            ]
            for value, canonical in values:
                if _candidate_match_key(value) not in text_key:
                    continue
                key = _match_key(value)
                if key in canonical_keys and canonical_keys[key] != term:
                    continue
                candidates.setdefault(key, []).append((value, term, canonical))
        unique = []
        for alternatives in candidates.values():
            if len({term for _, term, _ in alternatives}) != 1:
                continue
            seen_patterns = set()
            for value, term, canonical in alternatives:
                pattern_key = _replacement_pattern(value, canonical=canonical).casefold()
                if pattern_key not in seen_patterns:
                    seen_patterns.add(pattern_key)
                    unique.append((value, term, canonical))
        unique.sort(key=lambda item: len(item[0]), reverse=True)
        if not unique:
            return HotwordApplication(text=text)
        pattern, replacements = _compiled_replacements(tuple(unique))
        changes: list[HotwordChange] = []

        def replace(match):
            original = match.group(0)
            term = replacements[match.lastgroup]
            if original != term:
                changes.append(HotwordChange(original=original, replacement=term, term=term))
            return term

        return HotwordApplication(text=pattern.sub(replace, text), changes=changes)

    def record_usage(self, text: str, *, app_info: Optional[dict] = None, scene: str = "",
                     language: str = "", dictionary: Iterable[str] = ()) -> list[str]:
        if not isinstance(text, str):
            raise TypeError("Hotword usage text must be a string")
        if not text:
            return []
        app_info = app_info or {}
        dictionary = tuple(dictionary)
        now = _now_iso()
        app_key = str(app_info.get("bundle_id") or app_info.get("name") or "").casefold()
        with self._lock:
            entries = deepcopy(self._entries)
            candidates = [entry for entry in entries if entry.get("active")
                          and not entry.get("user_deleted") and _entry_applies(entry, app_info, scene)]
            candidates.extend(self._dictionary_entries(dictionary, {entry["key"] for entry in entries}))
            text_key = _candidate_match_key(text)
            candidates = [entry for entry in candidates if _candidate_match_key(entry["term"]) in text_key]
            if not candidates:
                return []
            values = tuple((entry["term"], entry["term"], True)
                           for entry in sorted(candidates, key=lambda item: len(item["term"]), reverse=True))
            pattern, replacements = _compiled_replacements(values)
            matched = {replacements[match.lastgroup] for match in pattern.finditer(text)}
            if not matched:
                return []
            stored_keys = {entry["key"] for entry in entries}
            used = []
            for entry in candidates:
                if entry["term"] not in matched:
                    continue
                if entry["key"] not in stored_keys:
                    entry = self._normalize_entry(entry)
                    entries.append(entry)
                    stored_keys.add(entry["key"])
                entry["usage_count"] = entry.get("usage_count", 0) + 1
                entry["last_used_at"] = now
                _increment_counter(entry.setdefault("usage_apps", {}), app_key)
                _increment_counter(entry.setdefault("scenes", {}), scene)
                _increment_counter(entry.setdefault("languages", {}), language)
                used.append(entry["term"])
            self._save(entries)
            return used

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
            entries = deepcopy(self._entries)
            entry = next((e for e in entries if e.get("key") == key), None)
            if entry is not None and entry.get("user_deleted"):
                return None
            if entry is None:
                entry = {
                    "term": term,
                    "key": key,
                    "aliases": aliases,
                    "confidence": confidence,
                    "active": False,
                    "user_disabled": False,
                    "user_confirmed": False,
                    "user_deleted": False,
                    "pinned": False,
                    "usage_count": 0,
                    "last_used_at": "",
                    "usage_apps": {},
                    "approved_aliases": [],
                    "alias_confidences": {alias: confidence for alias in aliases},
                    "scope_app": "",
                    "scope_scene": "",
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
                entries.append(entry)
            else:
                existing_aliases = _clean_aliases(entry.get("aliases", []), term)
                merged_aliases = existing_aliases + [
                    alias for alias in aliases if _term_key(alias) not in {_term_key(a) for a in existing_aliases}
                ]
                entry["aliases"] = merged_aliases[:MAX_ALIASES_PER_TERM]
                observed_keys = {_term_key(alias) for alias in aliases}
                previous_scores = {_term_key(alias): score for alias, score in entry.get("alias_confidences", {}).items()}
                entry["alias_confidences"] = {
                    alias: max(previous_scores.get(_term_key(alias), 0.0), confidence)
                    if _term_key(alias) in observed_keys else previous_scores.get(_term_key(alias), 0.0)
                    for alias in entry["aliases"]
                }
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
            if not entry.get("user_disabled") and (
                confidence >= active_confidence or entry["observations"] >= repeat_promotion_count
            ):
                entry["active"] = True
            stored = deepcopy(entry)
            self._save(entries)
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
        dictionary: Iterable[str] = (),
    ) -> ActiveHotwordContext:
        """Build a compact context string for the next ASR request."""
        app_info = app_info or {}
        app_keys = {str(app_info.get(key) or "").casefold() for key in ("bundle_id", "name")}
        app_keys.discard("")
        scene = str(scene or "")
        language = str(language or "")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("Hotword context limit must be a nonnegative integer")
        if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars < 0:
            raise ValueError("Hotword context budget must be a nonnegative integer")
        entries = self._applicable_entries(app_info, scene, dictionary)
        now = datetime.now(timezone.utc)

        def app_usage(entry):
            return sum(count for key, count in entry.get("usage_apps", {}).items() if key.casefold() in app_keys)

        def recent_usage(entry):
            if not entry.get("last_used_at"):
                return 0.0
            age_days = max(0.0, (now - datetime.fromisoformat(entry["last_used_at"])).total_seconds() / 86400)
            return max(0.0, 1.0 - age_days / 30.0)

        def score(entry: dict) -> float:
            value = _bounded_confidence(entry.get("confidence"), default=0.5)
            if entry.get("source") in ("manual", "dictionary"):
                value += 2.0
            if entry.get("scope_app") or entry.get("scope_scene"):
                value += 0.5
            value += min(int(entry.get("observations", 0) or 0), 5) * 0.04
            apps = entry.get("apps") or {}
            scenes = entry.get("scenes") or {}
            languages = entry.get("languages") or {}
            if any(count for key, count in apps.items() if key.casefold() in app_keys):
                value += 0.25
            if scene and scenes.get(scene):
                value += 0.18
            if language and language != "auto" and languages.get(language):
                value += 0.08
            value += min(math.log2(1 + entry.get("usage_count", 0)), 4.0) * 0.3
            value += min(math.log2(1 + app_usage(entry)), 3.0) * 0.5
            value += recent_usage(entry) * 2.0
            return value

        def reason(entry):
            if entry.get("pinned"):
                return "pinned"
            if entry.get("scope_app") or entry.get("scope_scene"):
                return "scoped"
            if app_usage(entry):
                return "app_usage"
            if recent_usage(entry):
                return "recent_usage"
            return "manual" if entry.get("source") in ("manual", "dictionary") else "learned"

        terms: list[str] = []
        selected: list[dict] = []
        total_chars = len(CONTEXT_PREFIX) + len(CONTEXT_SUFFIX)
        ranked = sorted(entries, key=lambda entry: (bool(entry.get("pinned")), score(entry),
                                                     entry.get("updated_at", "")), reverse=True)
        for entry in ranked:
            term = str(entry.get("term") or "").strip()
            if not term:
                continue
            extra = len(term) + (2 if terms else 0)
            if len(terms) >= limit:
                break
            if total_chars + extra > max_chars:
                continue
            terms.append(term)
            selected.append(entry)
            total_chars += extra
        context = CONTEXT_PREFIX + ", ".join(terms) + CONTEXT_SUFFIX if terms else ""
        selected_keys = {entry["key"] for entry in selected}
        return ActiveHotwordContext(
            terms=terms, context=context, entries=selected, eligible_count=len(entries),
            omitted_terms=[entry["term"] for entry in ranked if entry["key"] not in selected_keys],
            selection_reasons={entry["term"]: reason(entry) for entry in selected},
        )

    def _applicable_entries(self, app_info: dict, scene: str, dictionary: Iterable[str]) -> list[dict]:
        with self._lock:
            all_entries = deepcopy(self._entries)
        entries = [entry for entry in all_entries if entry.get("active") and entry.get("term")
                   and not entry.get("user_deleted") and _entry_applies(entry, app_info, scene)]
        entries.extend(self._dictionary_entries(dictionary, {entry["key"] for entry in all_entries}))
        return entries


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
