"""Native local diagnostics window."""

import threading
import AppKit
import objc
from Foundation import NSObject, NSMakeRect

from .i18n import t
from .diagnostics import run_readiness_checks, render_diagnostics_text


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
        return self

    def applyText_(self, _):
        self._controller._set_report_text(self._text)


class DiagnosticsWindowController:
    """Shows local readiness checks without sending user data anywhere."""

    def __init__(self, config: dict, asr_engine=None):
        self.config = config
        self.asr_engine = asr_engine
        self.window = None
        self._delegate = None
        self._updater = None
        self._text_view = None
        self._last_report = ""

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

    def copy_report(self):
        pb = AppKit.NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(self._last_report, AppKit.NSPasteboardTypeString)

    def refresh(self):
        self._set_report_text(t("diag_running"))

        def worker():
            try:
                items = run_readiness_checks(self.config, asr_engine=self.asr_engine)
                text = render_diagnostics_text(items)
            except Exception as e:
                text = t("diag_failed", error=str(e))
            self._updater._text = text
            self._updater.performSelectorOnMainThread_withObject_waitUntilDone_(
                b"applyText:", None, False
            )

        threading.Thread(target=worker, daemon=True, name="SpeakTypeDiagnostics").start()

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
        self.window.setTitle_(t("diag_window_title"))
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

        scroll = AppKit.NSScrollView.alloc().initWithFrame_(NSMakeRect(24, 70, 592, 398))
        scroll.setHasVerticalScroller_(True)
        scroll.setHasHorizontalScroller_(False)
        scroll.setBorderType_(AppKit.NSBezelBorder)
        content.addSubview_(scroll)

        self._text_view = AppKit.NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, 592, 398))
        self._text_view.setEditable_(False)
        self._text_view.setSelectable_(True)
        self._text_view.setFont_(AppKit.NSFont.monospacedSystemFontOfSize_weight_(12, AppKit.NSFontWeightRegular))
        self._text_view.setString_("")
        scroll.setDocumentView_(self._text_view)

        self._add_button(content, t("diag_refresh"), b"onRefresh:", 314, 22, 92)
        self._add_button(content, t("diag_copy"), b"onCopy:", 414, 22, 92)
        self._add_button(content, t("diag_close"), b"onClose:", 514, 22, 92)

    def _add_button(self, view, title, action, x, y, width):
        button = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(x, y, width, 32))
        button.setTitle_(title)
        button.setBezelStyle_(AppKit.NSBezelStyleRounded)
        button.setTarget_(self._delegate)
        button.setAction_(action)
        view.addSubview_(button)

    def _set_report_text(self, text: str):
        self._last_report = text
        if self._text_view is not None:
            self._text_view.setString_(text)
