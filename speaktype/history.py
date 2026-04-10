"""Local dictation history management."""

import csv
import io
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from .config import HISTORY_FILE, ensure_config_dir, write_json_file

logger = logging.getLogger("speaktype.history")

EXPORT_FORMATS = ("txt", "md", "csv", "json")


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

        rendered = self.render(self._entries, fmt)
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
