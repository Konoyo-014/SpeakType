"""Dictation statistics panel — native macOS window showing usage analytics."""

import logging
from datetime import datetime, timedelta
from collections import Counter
import AppKit
import objc
from Foundation import NSObject, NSMakeRect

logger = logging.getLogger("speaktype.stats_window")


class StatsWindowController:
    """Displays a statistics dashboard with dictation analytics."""

    def __init__(self, history):
        self.history = history
        self.window = None

    def show(self):
        if self.window and self.window.isVisible():
            self.window.makeKeyAndOrderFront_(None)
            AppKit.NSApp.activateIgnoringOtherApps_(True)
            return
        self._build_window()
        self.window.makeKeyAndOrderFront_(None)
        AppKit.NSApp.activateIgnoringOtherApps_(True)

    def _build_window(self):
        frame = NSMakeRect(0, 0, 520, 560)
        style = (
            AppKit.NSTitledWindowMask
            | AppKit.NSClosableWindowMask
            | AppKit.NSMiniaturizableWindowMask
        )
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, AppKit.NSBackingStoreBuffered, False
        )
        self.window.setTitle_("SpeakType — 听写统计")
        self.window.center()
        self.window.setLevel_(AppKit.NSFloatingWindowLevel)
        self.window.setTabbingMode_(AppKit.NSWindowTabbingModeDisallowed)

        content = self.window.contentView()
        entries = self.history.get_recent(self.history.max_entries)
        stats = self.history.get_stats()
        y = 530

        # --- Overview Section ---
        y = self._section(content, "概览", y)
        y = self._stat_row(content, "总听写次数", str(stats["total_entries"]), y)
        y = self._stat_row(content, "总字数", f"{stats['total_words']:,}", y)
        y = self._stat_row(content, "总时长", f"{stats['total_duration_min']:.1f} min", y)

        avg_words = round(stats["total_words"] / max(stats["total_entries"], 1), 1)
        avg_dur = round(stats["total_duration_min"] * 60 / max(stats["total_entries"], 1), 1)
        y = self._stat_row(content, "平均字数/次", str(avg_words), y)
        y = self._stat_row(content, "平均时长/次", f"{avg_dur:.1f}s", y)

        # --- Activity Section ---
        y -= 10
        y = self._section(content, "活动（最近 7 天）", y)
        day_counts = self._count_by_day(entries, 7)
        for day_str, count in day_counts:
            bar = self._bar_str(count, max(c for _, c in day_counts) if day_counts else 1)
            y = self._stat_row(content, day_str, f"{bar}  {count}", y)

        # --- Top Apps Section ---
        y -= 10
        y = self._section(content, "常用应用", y)
        app_counts = Counter(e.get("app", "Unknown") for e in entries if e.get("app"))
        for app_name, count in app_counts.most_common(5):
            y = self._stat_row(content, app_name, str(count), y)

        # --- Recent Dictations ---
        y -= 10
        y = self._section(content, "最近听写", y)
        for entry in reversed(entries[-8:]):
            text = entry.get("polished", entry.get("raw", ""))[:60]
            ts = entry.get("timestamp", "")[:16].replace("T", " ")
            y = self._stat_row(content, ts, text, y, value_width=340)

    def _section(self, view, title, y):
        y -= 8
        label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(20, y - 20, 480, 18))
        label.setStringValue_(title)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setFont_(AppKit.NSFont.boldSystemFontOfSize_(13))
        view.addSubview_(label)

        sep = AppKit.NSBox.alloc().initWithFrame_(NSMakeRect(20, y - 24, 480, 1))
        sep.setBoxType_(AppKit.NSBoxSeparator)
        view.addSubview_(sep)
        return y - 32

    def _stat_row(self, view, label_text, value_text, y, value_width=280):
        label = AppKit.NSTextField.alloc().initWithFrame_(
            NSMakeRect(30, y - 20, 480 - value_width, 18)
        )
        label.setStringValue_(label_text)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setFont_(AppKit.NSFont.systemFontOfSize_(12))
        label.setTextColor_(AppKit.NSColor.secondaryLabelColor())
        view.addSubview_(label)

        value = AppKit.NSTextField.alloc().initWithFrame_(
            NSMakeRect(500 - value_width, y - 20, value_width - 20, 18)
        )
        value.setStringValue_(str(value_text))
        value.setBezeled_(False)
        value.setDrawsBackground_(False)
        value.setEditable_(False)
        value.setSelectable_(True)
        value.setFont_(AppKit.NSFont.monospacedSystemFontOfSize_weight_(12, AppKit.NSFontWeightMedium))
        view.addSubview_(value)

        return y - 22

    def _count_by_day(self, entries, days):
        """Count dictations per day for the last N days."""
        now = datetime.now()
        counts = {}
        for i in range(days):
            d = now - timedelta(days=i)
            counts[d.strftime("%m/%d %a")] = 0

        for e in entries:
            try:
                ts = datetime.fromisoformat(e["timestamp"])
                key = ts.strftime("%m/%d %a")
                if key in counts:
                    counts[key] += 1
            except (KeyError, ValueError):
                continue

        return list(reversed(list(counts.items())))

    @staticmethod
    def _bar_str(count, max_count, width=15):
        """Generate a text-based bar chart segment."""
        if max_count == 0:
            return " " * width
        filled = round(count / max_count * width)
        return "\u2588" * filled + "\u2591" * (width - filled)
