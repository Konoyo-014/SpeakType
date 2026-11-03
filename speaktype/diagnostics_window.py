import threading
import unicodedata
import AppKit
import objc
from Foundation import NSObject, NSMakeRect

from .i18n import t
from .diagnostics import run_readiness_checks, render_diagnostics_text
from .design import apply_window, style_button

_diagnostics_workers = set()
_diagnostics_worker_lock = threading.Lock()
_diagnostics_shutdown = threading.Event()


def diagnostics_counts(items: list) -> dict[str, int]:
    return {
        "ok": sum(1 for item in items if item.status == "ok"),
        "warn": sum(1 for item in items if item.status == "warn"),
        "fail": sum(1 for item in items if item.status == "fail"),
    }


def diagnostics_summary_text(items: list, fallback: str) -> str:
    if not items:
        return fallback
    counts = diagnostics_counts(items)
    return t(
        "diag_summary_counts",
        ok=counts["ok"],
        warn=counts["warn"],
        fail=counts["fail"],
    )


class _DiagnosticsFlippedView(AppKit.NSView):
    def isFlipped(self):
        return True


class _DiagnosticsDelegate(NSObject):
    def initWithController_(self, controller):
        self = objc.super(_DiagnosticsDelegate, self).init()
        if self is not None:
            self._controller = controller
        return self

    def onRefresh_(self, sender):
        self._controller.refresh()

    def onCopy_(self, sender):
        self._controller.copy_report()

    def onClose_(self, sender):
        self._controller.close()


class _DiagnosticsUpdater(NSObject):
    def initWithController_(self, controller):
        self = objc.super(_DiagnosticsUpdater, self).init()
        if self is not None:
            self._controller = controller
            self._text = ""
            self._items = []
        return self

    def applyText_(self, _):
        self._controller._apply_report(self._text, self._items)


class DiagnosticsWindowController:
    """Shows local readiness checks without sending user data anywhere."""

    ROW_WIDTH = 592
    ROW_TEXT_WIDTH = 520
    ROW_DETAIL_LINE = 17
    ROW_ACTION_LINE = 17

    def __init__(self, config: dict, asr_engine=None):
        self.config = config
        self.asr_engine = asr_engine
        self.window = None
        self._delegate = None
        self._updater = None
        self._rows_view = None
        self._summary_field = None
        self._refresh_button = None
        self._copy_button = None
        self._last_report = ""
        self._last_items = []
        self._worker_thread = None

    def show(self):
        if _diagnostics_shutdown.is_set():
            raise RuntimeError("A shutting-down diagnostics window cannot be shown")
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

    @property
    def worker_threads(self):
        with _diagnostics_worker_lock:
            return tuple(_diagnostics_workers)

    def shutdown(self):
        _diagnostics_shutdown.set()

    def resume_after_shutdown(self):
        _diagnostics_shutdown.clear()
        if self.window is not None:
            self.refresh()

    def copy_report(self):
        pb = AppKit.NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(self._last_report, AppKit.NSPasteboardTypeString)
        if self._copy_button is not None:
            self._copy_button.setTitle_(t("diag_copy_done"))

    def refresh(self):
        if _diagnostics_shutdown.is_set() or (self._worker_thread is not None and self._worker_thread.is_alive()):
            return
        self._set_running(True)
        self._set_report_text(t("diag_running"))

        def worker():
            try:
                try:
                    items = run_readiness_checks(self.config, asr_engine=self.asr_engine)
                    text = render_diagnostics_text(items)
                except Exception as e:
                    items = []
                    text = t("diag_failed", error=str(e))
                if not _diagnostics_shutdown.is_set():
                    self._updater._text = text
                    self._updater._items = items
                    self._updater.performSelectorOnMainThread_withObject_waitUntilDone_(
                        b"applyText:", None, False
                    )
            finally:
                with _diagnostics_worker_lock:
                    _diagnostics_workers.discard(threading.current_thread())

        self._worker_thread = threading.Thread(target=worker, daemon=True, name="SpeakTypeDiagnostics")
        with _diagnostics_worker_lock:
            _diagnostics_workers.add(self._worker_thread)
        self._worker_thread.start()

    def _build_window(self):
        frame = NSMakeRect(0, 0, 640, 560)
        style = (
            AppKit.NSTitledWindowMask
            | AppKit.NSClosableWindowMask
            | AppKit.NSMiniaturizableWindowMask
        )
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, AppKit.NSBackingStoreBuffered, False
        )
        self.window.setReleasedWhenClosed_(False)
        self.window.setTitle_(t("diag_window_title"))
        apply_window(self.window)
        self.window.center()
        self.window.setLevel_(AppKit.NSFloatingWindowLevel)
        self.window.setTabbingMode_(AppKit.NSWindowTabbingModeDisallowed)

        content = self.window.contentView()
        self._delegate = _DiagnosticsDelegate.alloc().initWithController_(self)
        self._updater = _DiagnosticsUpdater.alloc().initWithController_(self)

        title = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(24, 510, 592, 24))
        title.setStringValue_(t("diag_window_heading"))
        title.setBezeled_(False)
        title.setDrawsBackground_(False)
        title.setEditable_(False)
        title.setSelectable_(False)
        title.setFont_(AppKit.NSFont.boldSystemFontOfSize_(17))
        content.addSubview_(title)

        subtitle = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(24, 482, 592, 22))
        subtitle.setStringValue_(t("diag_window_subtitle"))
        subtitle.setBezeled_(False)
        subtitle.setDrawsBackground_(False)
        subtitle.setEditable_(False)
        subtitle.setSelectable_(False)
        subtitle.setTextColor_(AppKit.NSColor.secondaryLabelColor())
        subtitle.setFont_(AppKit.NSFont.systemFontOfSize_(12))
        content.addSubview_(subtitle)

        self._summary_field = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(24, 452, 592, 22))
        self._summary_field.setBezeled_(False)
        self._summary_field.setDrawsBackground_(False)
        self._summary_field.setEditable_(False)
        self._summary_field.setSelectable_(False)
        self._summary_field.setFont_(AppKit.NSFont.systemFontOfSize_weight_(13, self._font_weight("medium")))
        content.addSubview_(self._summary_field)

        scroll = AppKit.NSScrollView.alloc().initWithFrame_(NSMakeRect(24, 74, 592, 364))
        scroll.setHasVerticalScroller_(True)
        scroll.setHasHorizontalScroller_(False)
        scroll.setBorderType_(AppKit.NSNoBorder)
        scroll.setDrawsBackground_(False)
        content.addSubview_(scroll)

        self._rows_view = _DiagnosticsFlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, 592, 364))
        scroll.setDocumentView_(self._rows_view)

        self._refresh_button = self._add_button(content, t("diag_refresh"), b"onRefresh:", 314, 22, 92)
        self._copy_button = self._add_button(content, t("diag_copy"), b"onCopy:", 414, 22, 92)
        self._add_button(content, t("diag_close"), b"onClose:", 514, 22, 92)

    def _add_button(self, view, title, action, x, y, width):
        button = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(x, y, width, 32))
        button.setTitle_(title)
        button.setBezelStyle_(AppKit.NSBezelStyleRounded)
        button.setTarget_(self._delegate)
        button.setAction_(action)
        style_button(button)
        view.addSubview_(button)
        return button

    def _apply_report(self, text: str, items: list):
        if _diagnostics_shutdown.is_set():
            return
        self._last_report = text
        self._last_items = list(items or [])
        is_running = not self._last_items and text == t("diag_running")
        self._set_running(is_running)
        if self._summary_field is not None:
            self._summary_field.setStringValue_(diagnostics_summary_text(self._last_items, text))
            self._summary_field.setTextColor_(self._summary_color(self._last_items))
        self._render_rows(self._last_items, text)

    def _set_report_text(self, text: str):
        self._apply_report(text, [])

    def _summary_color(self, items: list):
        if not items:
            return AppKit.NSColor.secondaryLabelColor()
        if any(item.status == "fail" for item in items):
            return AppKit.NSColor.systemRedColor()
        if any(item.status == "warn" for item in items):
            return AppKit.NSColor.systemOrangeColor()
        return AppKit.NSColor.systemGreenColor()

    def _set_running(self, running: bool):
        if self._refresh_button is not None:
            self._refresh_button.setEnabled_(not running)
            self._refresh_button.setTitle_(t("diag_refresh_running") if running else t("diag_refresh"))
        if self._copy_button is not None:
            self._copy_button.setEnabled_(not running and bool(str(self._last_report or "").strip()))
            if running:
                self._copy_button.setTitle_(t("diag_copy"))

    def _render_rows(self, items: list, fallback: str):
        if self._rows_view is None:
            return
        for subview in list(self._rows_view.subviews()):
            subview.removeFromSuperview()

        if not items:
            label = self._label(
                fallback,
                12,
                14,
                560,
                42,
                self._font_weight("regular"),
                AppKit.NSColor.secondaryLabelColor(),
                wraps=True,
            )
            self._rows_view.addSubview_(label)
            self._rows_view.setFrame_(NSMakeRect(0, 0, self.ROW_WIDTH, 364))
            return

        y = 8
        for item in items:
            detail_height = self._text_height(item.detail, line_height=self.ROW_DETAIL_LINE)
            action_text = self._action_text(item.action)
            action_height = self._text_height(action_text, line_height=self.ROW_ACTION_LINE) if action_text else 0
            row_height = 44 + detail_height + (8 + action_height if action_text else 0)
            row = _DiagnosticsFlippedView.alloc().initWithFrame_(NSMakeRect(0, y, self.ROW_WIDTH, row_height))
            row.setWantsLayer_(True)
            layer = row.layer()
            if layer is not None:
                layer.setCornerRadius_(8)
                try:
                    layer.setCornerCurve_("continuous")
                except Exception:
                    pass
                color = AppKit.NSColor.controlBackgroundColor().colorWithAlphaComponent_(0.72)
                layer.setBackgroundColor_(color.CGColor())

            marker = self._label("●", 14, 14, 18, 18, self._font_weight("bold"), self._status_color(item.status))
            title = self._label(item.title, 38, 10, self.ROW_TEXT_WIDTH, 20, self._font_weight("semibold"), AppKit.NSColor.labelColor())
            detail = self._label(
                item.detail,
                38,
                31,
                self.ROW_TEXT_WIDTH,
                detail_height,
                self._font_weight("regular"),
                AppKit.NSColor.secondaryLabelColor(),
                wraps=True,
            )
            row.addSubview_(marker)
            row.addSubview_(title)
            row.addSubview_(detail)
            if action_text:
                action = self._label(
                    action_text,
                    38,
                    36 + detail_height,
                    self.ROW_TEXT_WIDTH,
                    action_height,
                    self._font_weight("regular"),
                    self._tertiary_text_color(),
                    wraps=True,
                )
                row.addSubview_(action)
            self._rows_view.addSubview_(row)
            y += row_height + 8
        self._rows_view.setFrame_(NSMakeRect(0, 0, self.ROW_WIDTH, max(364, y + 8)))

    def _status_color(self, status: str):
        if status == "ok":
            return AppKit.NSColor.systemGreenColor()
        if status == "fail":
            return AppKit.NSColor.systemRedColor()
        return AppKit.NSColor.systemOrangeColor()

    def _font_weight(self, name: str):
        weights = {
            "regular": "NSFontWeightRegular",
            "medium": "NSFontWeightMedium",
            "semibold": "NSFontWeightSemibold",
            "bold": "NSFontWeightBold",
        }
        attr = weights.get(name, "NSFontWeightRegular")
        return getattr(AppKit, attr, getattr(AppKit, "NSFontWeightRegular", 0.0))

    def _tertiary_text_color(self):
        color_factory = getattr(AppKit.NSColor, "tertiaryLabelColor", None)
        if color_factory is not None:
            return color_factory()
        return AppKit.NSColor.secondaryLabelColor()

    def _action_text(self, action: str) -> str:
        if not action:
            return ""
        text = f"{t('diag_action_prefix')} {action}"
        return (
            text.replace("。临时测试可运行：", "。\n临时测试可运行：")
            .replace(". For a temporary test, run:", ".\nFor a temporary test, run:")
        )

    def _text_height(self, text: str, *, line_height: int) -> int:
        clean = str(text or "")
        if not clean:
            return line_height
        hard_lines = clean.splitlines() or [clean]
        line_count = 0
        for line in hard_lines:
            line_count += max(1, (self._display_units(line) + 51) // 52)
        return min(line_height * 4, line_height * line_count)

    def _display_units(self, text: str) -> int:
        total = 0
        for char in str(text or ""):
            total += 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
        return total

    def _label(self, text, x, y, width, height, weight, color, *, wraps=False):
        label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, width, height))
        label.setStringValue_(str(text or ""))
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(True)
        label.setFont_(AppKit.NSFont.systemFontOfSize_weight_(12, weight))
        label.setTextColor_(color)
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
        return label
