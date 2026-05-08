"""Dictation statistics panel with a scrollable native macOS layout."""

import logging
from collections import Counter
from datetime import datetime, timedelta
import math
import unicodedata

import AppKit
import objc
from Foundation import NSObject, NSMakePoint, NSMakeRect, NSMakeSize

from .i18n import get_language, t

logger = logging.getLogger("speaktype.stats_window")


def _display_units(text: str) -> int:
    total = 0
    for ch in str(text or ""):
        total += 2 if unicodedata.east_asian_width(ch) in {"W", "F"} else 1
    return total


def wrapped_text_height(text: str, width: int, *, line_height: int = 17) -> int:
    units_per_line = max(18, int(width / 6.5))
    lines = max(1, math.ceil(_display_units(text) / units_per_line))
    return lines * line_height


def stats_minutes_text(minutes: float) -> str:
    return t("stats_duration_minutes_value", minutes=f"{float(minutes or 0):.1f}")


def stats_seconds_text(seconds: float) -> str:
    return t("stats_duration_seconds_value", seconds=f"{float(seconds or 0):.1f}")


def stats_day_label(dt: datetime) -> str:
    if get_language() == "zh":
        weekdays = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
        return f"{dt.strftime('%m/%d')} {weekdays[dt.weekday()]}"
    return dt.strftime("%m/%d %a")


def stats_summary_text(stats: dict) -> str:
    return t(
        "stats_summary",
        count=stats["total_entries"],
        words=f"{stats['total_words']:,}",
        duration=stats_minutes_text(stats["total_duration_min"]),
    )


def stats_metric_values(stats: dict) -> list[tuple[str, str]]:
    avg_words = round(stats["total_words"] / max(stats["total_entries"], 1), 1)
    avg_dur = round(stats["total_duration_min"] * 60 / max(stats["total_entries"], 1), 1)
    return [
        (t("stats_total"), str(stats["total_entries"])),
        (t("stats_words"), f"{stats['total_words']:,}"),
        (t("stats_duration"), stats_minutes_text(stats["total_duration_min"])),
        (t("stats_avg_words"), str(avg_words)),
        (t("stats_avg_dur"), stats_seconds_text(avg_dur)),
    ]


def stats_window_recent_rows(entries: list[dict], *, limit: int = 8) -> list[dict]:
    rows = []
    for entry in reversed(list(entries)[-limit:]):
        timestamp = str(entry.get("timestamp", "") or "")
        rows.append(
            {
                "timestamp": timestamp[:16].replace("T", " "),
                "app": str(entry.get("app", "") or t("diag_unknown_app")),
                "duration": float(entry.get("duration", 0) or 0),
                "text": str(entry.get("polished") or entry.get("raw") or ""),
            }
        )
    return rows


class _StatsFlippedView(AppKit.NSView):
    def isFlipped(self):
        return True


class _StatsDelegate(NSObject):
    """ObjC delegate to dispatch stats-window button actions."""

    def initWithController_(self, controller):
        self = objc.super(_StatsDelegate, self).init()
        if self is not None:
            self._controller = controller
        return self

    def onExport_(self, sender):
        self._controller._do_export()

    def onClose_(self, sender):
        self._controller.close()


class StatsWindowController:
    """Displays a scrollable statistics dashboard with dictation analytics."""

    WIDTH = 660
    HEIGHT = 620
    DOC_WIDTH = 612
    SCROLL_HEIGHT = 446
    BUTTON_BAR_HEIGHT = 56

    def __init__(self, history):
        self.history = history
        self.window = None
        self._delegate = None
        self._doc_view = None

    def show(self):
        if self.window and self.window.isVisible():
            self.window.makeKeyAndOrderFront_(None)
            AppKit.NSApp.activateIgnoringOtherApps_(True)
            return
        self._build_window()
        self.window.makeKeyAndOrderFront_(None)
        AppKit.NSApp.activateIgnoringOtherApps_(True)

    def close(self):
        if self.window:
            self.window.close()

    def _build_window(self):
        frame = NSMakeRect(0, 0, self.WIDTH, self.HEIGHT)
        style = (
            AppKit.NSTitledWindowMask
            | AppKit.NSClosableWindowMask
            | AppKit.NSMiniaturizableWindowMask
            | AppKit.NSResizableWindowMask
        )
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, AppKit.NSBackingStoreBuffered, False
        )
        self.window.setTitle_(t("stats_title"))
        self.window.center()
        self.window.setLevel_(AppKit.NSFloatingWindowLevel)
        self.window.setTabbingMode_(AppKit.NSWindowTabbingModeDisallowed)
        self.window.setMinSize_(NSMakeSize(self.WIDTH, self.HEIGHT))

        self._delegate = _StatsDelegate.alloc().initWithController_(self)

        content = self.window.contentView()
        entries = self.history.get_recent(self.history.max_entries)
        stats = self.history.get_stats()

        self._label(content, t("stats_heading"), 24, 574, 612, 24, 17, AppKit.NSColor.labelColor(), bold=True)
        self._label(content, t("stats_subtitle"), 24, 548, 612, 20, 12, AppKit.NSColor.secondaryLabelColor())
        self._label(
            content,
            stats_summary_text(stats),
            24,
            522,
            612,
            20,
            13,
            AppKit.NSColor.secondaryLabelColor(),
            bold=True,
        )

        scroll = AppKit.NSScrollView.alloc().initWithFrame_(NSMakeRect(24, 70, self.DOC_WIDTH, self.SCROLL_HEIGHT))
        scroll.setHasVerticalScroller_(True)
        scroll.setHasHorizontalScroller_(False)
        scroll.setBorderType_(AppKit.NSNoBorder)
        scroll.setDrawsBackground_(False)
        scroll.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
        content.addSubview_(scroll)

        self._doc_view = _StatsFlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, self.DOC_WIDTH, self.SCROLL_HEIGHT))
        scroll.setDocumentView_(self._doc_view)
        doc_height = self._populate_content(entries, stats)
        self._doc_view.setFrame_(NSMakeRect(0, 0, self.DOC_WIDTH, max(self.SCROLL_HEIGHT, doc_height)))
        scroll.contentView().scrollToPoint_(NSMakePoint(0, 0))
        scroll.reflectScrolledClipView_(scroll.contentView())

        sep = AppKit.NSBox.alloc().initWithFrame_(NSMakeRect(0, self.BUTTON_BAR_HEIGHT - 1, self.WIDTH, 1))
        sep.setBoxType_(AppKit.NSBoxSeparator)
        sep.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewMaxYMargin)
        content.addSubview_(sep)

        self._add_button(content, t("stats_btn_export"), b"onExport:", 420, 22, 116)
        self._add_button(content, t("stats_btn_close"), b"onClose:", 546, 22, 90)

    def _populate_content(self, entries: list[dict], stats: dict) -> int:
        view = self._doc_view
        y = 8
        y = self._add_metrics(view, stats, y)
        y += 8
        y = self._section(view, t("stats_activity"), y)
        y = self._add_activity(view, entries, y)
        y += 10
        y = self._section(view, t("stats_top_apps"), y)
        y = self._add_top_apps(view, entries, y)
        y += 10
        y = self._section(view, t("stats_recent"), y)
        y = self._add_recent(view, entries, y)
        return y + 16

    def _add_metrics(self, view, stats: dict, y: int) -> int:
        metrics = stats_metric_values(stats)
        tile_w = 190
        tile_h = 58
        for idx, (label, value) in enumerate(metrics):
            col = idx % 3
            row = idx // 3
            x = col * 204
            tile_y = y + row * 66
            self._panel(view, x, tile_y, tile_w, tile_h)
            self._label(view, label, x + 12, tile_y + 10, tile_w - 24, 16, 11, AppKit.NSColor.secondaryLabelColor())
            self._label(view, value, x + 12, tile_y + 30, tile_w - 24, 20, 15, AppKit.NSColor.labelColor(), bold=True)
        return y + 132

    def _add_activity(self, view, entries: list[dict], y: int) -> int:
        day_counts = self._count_by_day(entries, 7)
        max_count = max((count for _, count in day_counts), default=1)
        max_count = max(max_count, 1)
        for day_str, count in day_counts:
            self._label(view, day_str, 8, y + 2, 110, 18, 12, AppKit.NSColor.secondaryLabelColor())
            self._bar(view, 132, y + 7, 360, 8, count / max_count)
            self._label(view, str(count), 510, y + 2, 80, 18, 12, AppKit.NSColor.labelColor(), bold=True)
            y += 24
        return y

    def _add_top_apps(self, view, entries: list[dict], y: int) -> int:
        app_counts = Counter(e.get("app", "Unknown") for e in entries if e.get("app"))
        if not app_counts:
            self._label(view, t("stats_no_apps"), 8, y + 4, 580, 20, 12, AppKit.NSColor.secondaryLabelColor())
            return y + 28
        max_count = max(app_counts.values()) or 1
        for app_name, count in app_counts.most_common(6):
            self._label(view, app_name, 8, y + 2, 170, 18, 12, AppKit.NSColor.secondaryLabelColor())
            self._bar(view, 190, y + 7, 302, 8, count / max_count)
            self._label(view, str(count), 510, y + 2, 80, 18, 12, AppKit.NSColor.labelColor(), bold=True)
            y += 24
        return y

    def _add_recent(self, view, entries: list[dict], y: int) -> int:
        rows = stats_window_recent_rows(entries)
        if not rows:
            self._label(view, t("stats_no_recent"), 8, y + 4, 580, 20, 12, AppKit.NSColor.secondaryLabelColor())
            return y + 28
        for row in rows:
            text_height = wrapped_text_height(row["text"], 520)
            row_h = 46 + text_height
            self._panel(view, 0, y, self.DOC_WIDTH, row_h)
            meta = f"{row['timestamp']}  ·  {row['app']}  ·  {stats_seconds_text(row['duration'])}"
            self._label(view, meta, 14, y + 10, 580, 18, 11, AppKit.NSColor.secondaryLabelColor())
            self._label(view, row["text"], 14, y + 32, 580, text_height, 12, AppKit.NSColor.labelColor(), wraps=True)
            y += row_h + 8
        return y

    def _section(self, view, title: str, y: int) -> int:
        self._label(view, title, 0, y, 590, 20, 13, AppKit.NSColor.labelColor(), bold=True)
        sep = AppKit.NSBox.alloc().initWithFrame_(NSMakeRect(0, y + 24, self.DOC_WIDTH, 1))
        sep.setBoxType_(AppKit.NSBoxSeparator)
        view.addSubview_(sep)
        return y + 34

    def _panel(self, view, x: int, y: int, width: int, height: int):
        panel = AppKit.NSView.alloc().initWithFrame_(NSMakeRect(x, y, width, height))
        panel.setWantsLayer_(True)
        layer = panel.layer()
        if layer is not None:
            layer.setCornerRadius_(8)
            try:
                layer.setCornerCurve_("continuous")
            except Exception:
                pass
            layer.setBackgroundColor_(AppKit.NSColor.controlBackgroundColor().colorWithAlphaComponent_(0.72).CGColor())
        view.addSubview_(panel)

    def _bar(self, view, x: int, y: int, width: int, height: int, fraction: float):
        fraction = max(0.0, min(1.0, float(fraction or 0.0)))
        bg = AppKit.NSView.alloc().initWithFrame_(NSMakeRect(x, y, width, height))
        bg.setWantsLayer_(True)
        bg_layer = bg.layer()
        if bg_layer is not None:
            bg_layer.setCornerRadius_(height / 2)
            bg_layer.setBackgroundColor_(AppKit.NSColor.tertiaryLabelColor().colorWithAlphaComponent_(0.22).CGColor())
        view.addSubview_(bg)
        fg = AppKit.NSView.alloc().initWithFrame_(NSMakeRect(x, y, max(4, round(width * fraction)) if fraction > 0 else 0, height))
        fg.setWantsLayer_(True)
        fg_layer = fg.layer()
        if fg_layer is not None:
            fg_layer.setCornerRadius_(height / 2)
            fg_layer.setBackgroundColor_(AppKit.NSColor.controlAccentColor().CGColor())
        view.addSubview_(fg)

    def _label(self, view, text, x, y, width, height, size, color, *, bold=False, wraps=False):
        label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, width, height))
        label.setStringValue_(str(text or ""))
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(True)
        label.setTextColor_(color)
        if bold:
            label.setFont_(AppKit.NSFont.boldSystemFontOfSize_(size))
        else:
            label.setFont_(AppKit.NSFont.systemFontOfSize_(size))
        cell = label.cell()
        if cell is not None:
            try:
                if wraps:
                    cell.setWraps_(True)
                    cell.setLineBreakMode_(AppKit.NSLineBreakByWordWrapping)
                    label.setUsesSingleLineMode_(False)
                else:
                    cell.setLineBreakMode_(AppKit.NSLineBreakByTruncatingTail)
            except Exception:
                pass
        view.addSubview_(label)
        return label

    def _add_button(self, view, title, action, x, y, width):
        button = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(x, y, width, 32))
        button.setTitle_(title)
        button.setBezelStyle_(AppKit.NSBezelStyleRounded)
        button.setTarget_(self._delegate)
        button.setAction_(action)
        view.addSubview_(button)

    def _count_by_day(self, entries, days):
        """Count dictations per day for the last N days."""
        now = datetime.now()
        counts = {}
        for i in range(days):
            d = now - timedelta(days=i)
            counts[stats_day_label(d)] = 0

        for e in entries:
            try:
                ts = datetime.fromisoformat(e["timestamp"])
                key = stats_day_label(ts)
                if key in counts:
                    counts[key] += 1
            except (KeyError, ValueError):
                continue

        return list(reversed(list(counts.items())))

    def _do_export(self):
        """Show an NSSavePanel and export the history to the chosen file."""
        panel = AppKit.NSSavePanel.savePanel()
        panel.setTitle_(t("stats_btn_export"))
        panel.setAllowedFileTypes_(["txt", "md", "csv", "json"])
        panel.setNameFieldStringValue_("speaktype-history.md")

        result = panel.runModal()
        if result != AppKit.NSModalResponseOK:
            return
        url = panel.URL()
        if url is None:
            return
        path = url.path()
        try:
            saved_path = self.history.export(path)
        except Exception as e:
            logger.error(f"History export failed: {e}")
            self._show_alert(
                t("stats_export_failed_title"),
                t("stats_export_failed_body", error=str(e)[:200]),
                AppKit.NSAlertStyleWarning,
            )
            return
        self._show_alert(
            t("stats_export_done_title"),
            t("stats_export_done_body", path=str(saved_path)),
            AppKit.NSAlertStyleInformational,
        )

    def _show_alert(self, title: str, body: str, style):
        alert = AppKit.NSAlert.alloc().init()
        alert.setMessageText_(title)
        alert.setInformativeText_(body)
        alert.setAlertStyle_(style)
        alert.runModal()
