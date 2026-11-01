"""Local dictation history management."""

import csv
import io
import json
import math
import threading
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from numbers import Real
from typing import Iterable, Optional
from uuid import uuid4

from .config import HISTORY_FILE, write_json_file

EXPORT_FORMATS = ("txt", "md", "csv", "json")
INSERTION_OUTCOMES = ("pending", "inserted", "sent", "failed")


def _validate_duration(value) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("History duration must be a finite nonnegative number")
    duration = float(value)
    if not math.isfinite(duration) or duration < 0:
        raise ValueError("History duration must be a finite nonnegative number")
    return duration


def _validate_entry(entry: dict, index: int) -> dict:
    if not isinstance(entry, dict):
        raise ValueError(f"History record {index} must be an object")
    result = dict(entry)
    for key in ("timestamp", "raw", "polished", "app"):
        if key not in result or not isinstance(result[key], str):
            raise ValueError(f"History record {index} field {key} must be a string")
    result["duration"] = _validate_duration(result.get("duration", 0))
    if "id" not in result:
        result["id"] = uuid4().hex
    if not isinstance(result["id"], str) or not result["id"]:
        raise ValueError(f"History record {index} must have a nonempty string id")
    result.setdefault("outcome", "sent")
    if result["outcome"] not in INSERTION_OUTCOMES:
        raise ValueError(f"History record {index} has an unsupported insertion outcome")
    return result


class DictationHistory:
    def __init__(self, max_entries=1000, path: str | Path | None = None):
        if isinstance(max_entries, bool) or not isinstance(max_entries, int) or max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self.max_entries = max_entries
        self.path = Path(path).expanduser() if path is not None else HISTORY_FILE
        self._entries = []
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            with open(self.path, encoding="utf-8") as f:
                entries = json.load(f)
            if not isinstance(entries, list):
                raise ValueError("History file must contain a list of records")
            self._entries = [_validate_entry(entry, index) for index, entry in enumerate(entries)]
            identifiers = [entry["id"] for entry in self._entries]
            if len(identifiers) != len(set(identifiers)):
                raise ValueError("History record ids must be unique")
            self._entries = self._entries[-self.max_entries:]

    def _save(self):
        write_json_file(self.path, self._entries[-self.max_entries:])

    def add(
        self,
        raw_text: str,
        polished_text: str,
        app_name: str = "",
        duration_sec: float = 0,
        outcome: str = "inserted",
    ) -> str:
        if outcome not in INSERTION_OUTCOMES:
            raise ValueError(f"Unsupported insertion outcome: {outcome}")
        if not all(isinstance(value, str) for value in (raw_text, polished_text, app_name)):
            raise ValueError("History text and app name must be strings")
        duration = _validate_duration(duration_sec)
        entry = {
            "id": uuid4().hex,
            "timestamp": datetime.now().isoformat(),
            "raw": raw_text,
            "polished": polished_text,
            "app": app_name,
            "duration": round(duration, 1),
            "outcome": outcome,
        }
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self.max_entries:
                self._entries = self._entries[-self.max_entries:]
            self._save()
        return entry["id"]

    def set_outcome(self, entry_id: str, outcome: str) -> bool:
        if outcome not in INSERTION_OUTCOMES:
            raise ValueError(f"Unsupported insertion outcome: {outcome}")
        with self._lock:
            for entry in self._entries:
                if entry.get("id") == entry_id:
                    entry["outcome"] = outcome
                    self._save()
                    return True
        return False

    def update_text(self, entry_id: str, polished_text: str) -> bool:
        if not isinstance(polished_text, str):
            raise ValueError("History final text must be a string")
        with self._lock:
            for entry in self._entries:
                if entry.get("id") == entry_id:
                    entry["polished"] = polished_text
                    self._save()
                    return True
        return False

    def add_async(self, raw_text: str, polished_text: str, app_name: str = "", duration_sec: float = 0, outcome: str = "inserted"):
        worker = threading.Thread(
            target=self.add,
            kwargs={
                "raw_text": raw_text,
                "polished_text": polished_text,
                "app_name": app_name,
                "duration_sec": duration_sec,
                "outcome": outcome,
            },
            daemon=True,
            name="SpeakTypeHistorySave",
        )
        worker.start()
        return worker

    def snapshot(self) -> list[dict]:
        with self._lock:
            return deepcopy(self._entries)

    def get_recent(self, count=20) -> list:
        with self._lock:
            return deepcopy(self._entries[-count:]) if count > 0 else []

    def get_stats(self) -> dict:
        with self._lock:
            entries = deepcopy(self._entries)
        total_words = sum(len(e.get("polished", "").split()) for e in entries)
        total_duration = sum(e.get("duration", 0) for e in entries)
        return {
            "total_entries": len(entries),
            "total_words": total_words,
            "total_duration_min": round(total_duration / 60, 1),
        }

    def clear(self):
        with self._lock:
            self._entries = []
            self._save()

    # ------------------------------------------------------------------ #
    # Export                                                              #
    # ------------------------------------------------------------------ #

    def export(self, path: str | Path, fmt: Optional[str] = None) -> Path:
        """Write the dictation history to a file in the requested format.

        Args:
            path: Destination filename. The format is inferred from the
                file extension when ``fmt`` is omitted.
            fmt: Optional explicit format ('txt', 'md', 'csv', 'json').

        Returns the resolved destination path.
        """
        target = Path(path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        if fmt is None:
            fmt = target.suffix.lstrip(".").lower() or "txt"
        fmt = fmt.lower()
        if fmt not in EXPORT_FORMATS:
            raise ValueError(f"Unsupported export format: {fmt}")

        rendered = self.render(self.snapshot(), fmt)
        target.write_text(rendered, encoding="utf-8")
        return target

    @staticmethod
    def render(entries: Iterable[dict], fmt: str) -> str:
        """Render history entries to a string in the requested format."""
        entries_list = list(entries)
        fmt = fmt.lower()

        if fmt == "json":
            return json.dumps(entries_list, indent=2, ensure_ascii=False)

        if fmt == "csv":
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(["timestamp", "app", "duration", "raw", "polished"])
            for entry in entries_list:
                writer.writerow([
                    entry.get("timestamp", ""),
                    entry.get("app", ""),
                    entry.get("duration", 0),
                    entry.get("raw", ""),
                    entry.get("polished", ""),
                ])
            return buffer.getvalue()

        if fmt == "md":
            lines: list[str] = ["# SpeakType Dictation History", ""]
            for entry in entries_list:
                ts = entry.get("timestamp", "")
                app = entry.get("app", "Unknown")
                duration = entry.get("duration", 0)
                lines.append(f"## {ts} — {app} ({duration}s)")
                raw = entry.get("raw", "")
                polished = entry.get("polished", "")
                if polished and polished != raw:
                    lines.append("")
                    lines.append(f"**Polished:** {polished}")
                    lines.append("")
                    lines.append(f"**Raw:** {raw}")
                else:
                    lines.append("")
                    lines.append(polished or raw)
                lines.append("")
            return "\n".join(lines).strip() + "\n"

        # default: plain text
        lines = []
        for entry in entries_list:
            ts = entry.get("timestamp", "")
            app = entry.get("app", "Unknown")
            duration = entry.get("duration", 0)
            polished = entry.get("polished") or entry.get("raw", "")
            lines.append(f"[{ts}] ({app}, {duration}s) {polished}")
        return "\n".join(lines) + ("\n" if lines else "")
