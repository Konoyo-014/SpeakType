"""Native adaptive hotword status window."""

from __future__ import annotations

from datetime import datetime
import math
import subprocess

import AppKit
import objc
from Foundation import NSObject, NSMakeRect

from .config import CONFIG_DIR, ensure_config_dir
from .hotwords import HOTWORDS_FILE, HotwordStore
from .i18n import t


def _confidence_percent(value) -> str:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    return f"{round(confidence * 100):.0f}%"


def _short_date(value: str) -> str:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return ""
    return dt.strftime("%Y-%m-%d")


def _top_counter_keys(mapping: dict, limit: int = 2) -> str:
    if not isinstance(mapping, dict) or not mapping:
        return ""
    pairs = sorted(mapping.items(), key=lambda item: int(item[1] or 0), reverse=True)
    return ", ".join(str(key) for key, _ in pairs[:limit] if key)


def hotword_window_rows(entries: list[dict]) -> list[dict]:
    """Return display rows sorted for the hotword status window."""
    def sort_key(entry: dict):
        return (
            0 if entry.get("active") else 1,
            -int(entry.get("observations", 0) or 0),
            -float(entry.get("confidence", 0.0) or 0.0),
            str(entry.get("updated_at", "")),
        )

    rows: list[dict] = []
    for entry in sorted((e for e in entries if e.get("term")), key=sort_key):
        aliases = ", ".join(str(alias) for alias in entry.get("aliases") or [] if alias)
        apps = _top_counter_keys(entry.get("apps") or {})
        rows.append(
            {
                "term": str(entry.get("term") or ""),
                "active": bool(entry.get("active")),
                "confidence": _confidence_percent(entry.get("confidence")),
                "observations": int(entry.get("observations", 0) or 0),
                "updated": _short_date(str(entry.get("updated_at") or entry.get("last_seen_at") or "")),
                "aliases": aliases,
                "apps": apps,
            }
        )
    return rows


def active_hotword_context_text(entries: list[dict]) -> str:
    rows = hotword_window_rows(entries)
    return " ".join(row["term"] for row in rows if row.get("active"))


def active_hotword_context_copy_state(entries: list[dict]) -> dict:
    active_rows = [row for row in hotword_window_rows(entries) if row.get("active")]
    text = " ".join(row["term"] for row in active_rows)
    count = len(active_rows)
    if not text:
        return {
            "text": "",
            "count": 0,
            "should_copy": False,
            "feedback": t("hotwords_copy_empty"),
        }
    return {
        "text": text,
        "count": count,
        "should_copy": True,
        "feedback": t("hotwords_copy_done", count=count),
    }


def hotword_reveal_feedback(file_exists: bool) -> str:
    return t("hotwords_reveal_done_file" if file_exists else "hotwords_reveal_done_folder")


def _display_len(text: str) -> int:
    total = 0
    for ch in str(text or ""):
        total += 2 if ord(ch) > 127 else 1
    return total


def hotword_row_detail(row_data: dict) -> str:
    parts = []
    if row_data.get("aliases"):
        parts.append(t("hotwords_aliases", aliases=row_data["aliases"]))
    if row_data.get("apps"):
        parts.append(t("hotwords_apps", apps=row_data["apps"]))
    return "  ·  ".join(parts) if parts else t("hotwords_no_extra")


def hotword_row_metrics(row_data: dict, width: int = 612) -> dict:
    """Return deterministic row sizing for the native hotword window."""
    text_width = max(220, width - 62)
    title_chars = max(24, int(text_width / 8.5))
    detail_chars = max(28, int(text_width / 7.0))

    title_lines = min(2, max(1, math.ceil(_display_len(row_data.get("term", "")) / title_chars)))
    detail = hotword_row_detail(row_data)
    detail_lines = min(4, max(1, math.ceil(_display_len(detail) / detail_chars)))

    title_height = 20 if title_lines == 1 else 38
    detail_height = detail_lines * 18
    row_height = 14 + title_height + 22 + 6 + detail_height + 12
    return {
        "text_width": text_width,
        "title_height": title_height,
        "detail_height": detail_height,
        "row_height": max(92, row_height),
        "detail": detail,
    }


def hotword_rows_document_height(rows: list[dict], width: int = 652, min_height: int = 368) -> int:
    if not rows:
        return min_height
    height = 8
    for row_data in rows:
        height += hotword_row_metrics(row_data, width)["row_height"] + 8
    return max(min_height, height + 8)


class _HotwordsFlippedView(AppKit.NSView):
    def isFlipped(self):
        return True


class _HotwordsDelegate(NSObject):
    def initWithController_(self, controller):
        self = objc.super(_HotwordsDelegate, self).init()
        if self is not None:
            self._controller = controller
        return self

    def onRefresh_(self, sender):
        self._controller.refresh()

    def onCopyContext_(self, sender):
        self._controller.copy_context()

    def onReveal_(self, sender):
        self._controller.reveal_store()

    def onClose_(self, sender):
        self._controller.close()


class HotwordsWindowController:
    """Read-only view of locally learned adaptive hotwords."""

    WIDTH = 700
    HEIGHT = 560
    ROW_WIDTH = 652

    def __init__(self, hotwords: HotwordStore | None = None):
        self.hotwords = hotwords if hotwords is not None else HotwordStore()
        self.window = None
        self._delegate = None
        self._rows_view = None
        self._summary_field = None
        self._copy_feedback_field = None
        self._last_entries: list[dict] = []

    def show(self):
        if self.window and self.window.isVisible():
            self.window.makeKeyAndOrderFront_(None)
            AppKit.NSApp.activateIgnoringOtherApps_(True)
            self.refresh()
            return
        self._build_window()
        self.window.makeKeyAndOrderFront_(None)
        AppKit.NSApp.activateIgnoringOtherApps_(True)
        self.refresh()

    def close(self):
        if self.window:
            self.window.close()

    def refresh(self):
        try:
            self._last_entries = self.hotwords.get_all()
        except Exception:
            self._last_entries = []
        self._clear_copy_feedback()
        self._render()

    def copy_context(self):
        state = active_hotword_context_copy_state(self._last_entries)
        if state["should_copy"]:
            pb = AppKit.NSPasteboard.generalPasteboard()
            pb.clearContents()
            pb.setString_forType_(state["text"], AppKit.NSPasteboardTypeString)
        color = (
            AppKit.NSColor.secondaryLabelColor()
            if state["should_copy"]
            else AppKit.NSColor.systemOrangeColor()
        )
        self._set_footer_feedback(state["feedback"], color)

    def _clear_copy_feedback(self):
        self._set_footer_feedback("", AppKit.NSColor.secondaryLabelColor())

    def _set_footer_feedback(self, text, color):
        if self._copy_feedback_field is not None:
            self._copy_feedback_field.setStringValue_(text)
            self._copy_feedback_field.setTextColor_(color)

    def reveal_store(self):
        ensure_config_dir()
        file_exists = HOTWORDS_FILE.exists()
        if file_exists:
            subprocess.run(["open", "-R", str(HOTWORDS_FILE)])
        else:
            subprocess.run(["open", str(CONFIG_DIR)])
        self._set_footer_feedback(
            hotword_reveal_feedback(file_exists),
            AppKit.NSColor.secondaryLabelColor(),
        )

    def _build_window(self):
        frame = NSMakeRect(0, 0, self.WIDTH, self.HEIGHT)
        style = (
            AppKit.NSTitledWindowMask
            | AppKit.NSClosableWindowMask
            | AppKit.NSMiniaturizableWindowMask
        )
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, AppKit.NSBackingStoreBuffered, False
        )
        self.window.setReleasedWhenClosed_(False)
        self.window.setTitle_(t("hotwords_window_title"))
        self.window.center()
        self.window.setLevel_(AppKit.NSFloatingWindowLevel)
        self.window.setTabbingMode_(AppKit.NSWindowTabbingModeDisallowed)

        content = self.window.contentView()
        self._delegate = _HotwordsDelegate.alloc().initWithController_(self)

        title = self._label(t("hotwords_window_heading"), 24, 510, 652, 24, 17, AppKit.NSColor.labelColor(), bold=True)
        content.addSubview_(title)

        subtitle = self._label(t("hotwords_window_subtitle"), 24, 482, 652, 22, 12, AppKit.NSColor.secondaryLabelColor())
        content.addSubview_(subtitle)

        self._summary_field = self._label("", 24, 452, 652, 22, 13, AppKit.NSColor.secondaryLabelColor(), bold=True)
        content.addSubview_(self._summary_field)

        scroll = AppKit.NSScrollView.alloc().initWithFrame_(NSMakeRect(24, 70, 652, 368))
        scroll.setHasVerticalScroller_(True)
        scroll.setHasHorizontalScroller_(False)
        scroll.setBorderType_(AppKit.NSNoBorder)
        scroll.setDrawsBackground_(False)
        content.addSubview_(scroll)

        self._rows_view = _HotwordsFlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, 652, 368))
        scroll.setDocumentView_(self._rows_view)

        self._copy_feedback_field = self._label("", 24, 28, 260, 18, 11, AppKit.NSColor.secondaryLabelColor())
        content.addSubview_(self._copy_feedback_field)

        self._add_button(content, t("hotwords_refresh"), b"onRefresh:", 298, 22, 82)
        self._add_button(content, t("hotwords_copy_context"), b"onCopyContext:", 388, 22, 112)
        self._add_button(content, t("hotwords_reveal_file"), b"onReveal:", 508, 22, 82)
        self._add_button(content, t("hotwords_close"), b"onClose:", 598, 22, 78)

    def _add_button(self, view, title, action, x, y, width):
        button = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(x, y, width, 32))
        button.setTitle_(title)
        button.setBezelStyle_(AppKit.NSBezelStyleRounded)
        button.setTarget_(self._delegate)
        button.setAction_(action)
        view.addSubview_(button)

    def _render(self):
        if self._summary_field is not None:
            active = sum(1 for entry in self._last_entries if entry.get("active"))
            self._summary_field.setStringValue_(
                t("hotwords_summary", active=active, total=len(self._last_entries))
            )
        self._render_rows(hotword_window_rows(self._last_entries))

    def _render_rows(self, rows: list[dict]):
        if self._rows_view is None:
            return
        for subview in list(self._rows_view.subviews()):
            subview.removeFromSuperview()
        if not rows:
            title = self._label(t("hotwords_empty_title"), 16, 16, 620, 22, 13, AppKit.NSColor.labelColor(), bold=True)
            detail = self._label(t("hotwords_empty_detail"), 16, 42, 620, 22, 12, AppKit.NSColor.secondaryLabelColor())
            self._rows_view.addSubview_(title)
            self._rows_view.addSubview_(detail)
            self._rows_view.setFrame_(NSMakeRect(0, 0, self.ROW_WIDTH, hotword_rows_document_height([])))
            return

        y = 8
        for row_data in rows:
            metrics = hotword_row_metrics(row_data, self.ROW_WIDTH)
            row_height = metrics["row_height"]
            text_width = metrics["text_width"]
            row = _HotwordsFlippedView.alloc().initWithFrame_(NSMakeRect(0, y, self.ROW_WIDTH, row_height))
            row.setWantsLayer_(True)
            layer = row.layer()
            if layer is not None:
                layer.setCornerRadius_(8)
                try:
                    layer.setCornerCurve_("continuous")
                except Exception:
                    pass
                layer.setBackgroundColor_(AppKit.NSColor.controlBackgroundColor().colorWithAlphaComponent_(0.72).CGColor())

            marker_color = AppKit.NSColor.systemGreenColor() if row_data["active"] else AppKit.NSColor.systemOrangeColor()
            status = t("hotwords_status_active") if row_data["active"] else t("hotwords_status_candidate")
            marker = self._label("●", 14, 14, 18, 18, 12, marker_color, bold=True)
            title = self._label(
                row_data["term"],
                38,
                10,
                text_width,
                metrics["title_height"],
                13,
                AppKit.NSColor.labelColor(),
                bold=True,
                wraps=True,
                line_break_mode=AppKit.NSLineBreakByCharWrapping,
                tooltip=row_data["term"],
            )
            status_text = t(
                "hotwords_row_status",
                status=status,
                confidence=row_data["confidence"],
            )
            meta = t("hotwords_row_history", observations=row_data["observations"], updated=row_data["updated"] or "-")
            status_label = self._label(
                f"{status_text} · {meta}",
                38,
                16 + metrics["title_height"],
                text_width,
                18,
                11,
                AppKit.NSColor.secondaryLabelColor(),
                tooltip=f"{status_text} · {meta}",
            )
            detail_text = metrics["detail"]
            detail = self._label(
                detail_text,
                38,
                40 + metrics["title_height"],
                text_width,
                metrics["detail_height"],
                12,
                AppKit.NSColor.secondaryLabelColor(),
                wraps=True,
                line_break_mode=AppKit.NSLineBreakByWordWrapping,
                tooltip=detail_text,
            )
            row.addSubview_(marker)
            row.addSubview_(title)
            row.addSubview_(status_label)
            row.addSubview_(detail)
            self._rows_view.addSubview_(row)
            y += row_height + 8
        self._rows_view.setFrame_(NSMakeRect(0, 0, self.ROW_WIDTH, hotword_rows_document_height(rows, self.ROW_WIDTH)))

    def _row_detail(self, row_data: dict) -> str:
        return hotword_row_detail(row_data)

    def _label(
        self,
        text,
        x,
        y,
        width,
        height,
        size,
        color,
        *,
        bold=False,
        wraps=False,
        line_break_mode=None,
        tooltip=None,
    ):
        label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, width, height))
        label.setStringValue_(str(text or ""))
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(True)
        label.setTextColor_(color)
        if tooltip:
            label.setToolTip_(str(tooltip))
        if bold:
            label.setFont_(AppKit.NSFont.boldSystemFontOfSize_(size))
        else:
            label.setFont_(AppKit.NSFont.systemFontOfSize_(size))
        cell = label.cell()
        if cell is not None:
            try:
                if wraps:
                    cell.setWraps_(True)
                    cell.setLineBreakMode_(
                        line_break_mode or AppKit.NSLineBreakByWordWrapping
                    )
                    label.setUsesSingleLineMode_(False)
                else:
                    cell.setLineBreakMode_(AppKit.NSLineBreakByTruncatingTail)
            except Exception:
                pass
        return label
