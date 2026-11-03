from __future__ import annotations

import AppKit
import objc
from Foundation import NSIndexSet, NSObject, NSMakeRect, NSMakeSize

from .history import DictationHistory, INSERTION_OUTCOMES
from .i18n import get_language, t
from .design import apply_window, color, material_view, style_button


def history_outcome_text(outcome: str) -> str:
    if outcome not in INSERTION_OUTCOMES:
        raise ValueError(f"Unsupported insertion outcome: {outcome}")
    return t(f"history_outcome_{outcome}")


def history_window_rows(entries: list[dict], query: str = "") -> list[dict]:
    needle = str(query or "").strip().casefold()
    rows = []
    for entry in reversed(entries):
        row = dict(entry)
        row["time_label"] = str(entry.get("timestamp") or "")[:19].replace("T", " ")
        row["app_label"] = str(entry.get("app") or t("diag_unknown_app"))
        row["outcome_label"] = history_outcome_text(entry.get("outcome", "inserted"))
        row["preview"] = " ".join(str(entry.get("polished") or entry.get("raw") or "").splitlines())
        searchable = " ".join(
            str(row.get(key) or "")
            for key in ("raw", "polished", "app_label", "time_label", "outcome", "outcome_label")
        ).casefold()
        if not needle or needle in searchable:
            rows.append(row)
    return rows


class _HistoryDelegate(NSObject):
    def initWithController_(self, controller):
        self = objc.super(_HistoryDelegate, self).init()
        if self is not None:
            self._controller = controller
        return self

    def numberOfRowsInTableView_(self, table):
        return len(self._controller._rows)

    def tableView_objectValueForTableColumn_row_(self, table, column, row):
        return self._controller._rows[row].get(str(column.identifier()), "")

    def tableViewSelectionDidChange_(self, notification):
        self._controller._update_selection()

    def controlTextDidChange_(self, notification):
        self._controller._filter_rows()

    def onRefresh_(self, sender):
        self._controller.refresh()

    def onCopyFinal_(self, sender):
        self._controller.copy_selected("polished")

    def onCopyRaw_(self, sender):
        self._controller.copy_selected("raw")

    def onExport_(self, sender):
        self._controller.export_history()

    def onClose_(self, sender):
        self._controller.close()

    def onOpen_(self, sender):
        self._controller.open_selected()

    def onVocabulary_(self, sender):
        self._controller.show_vocabulary_details()


class HistoryWindowController:
    WIDTH = 900
    HEIGHT = 640

    def __init__(self, history: DictationHistory, *, on_open=None):
        self.history = history
        self._on_open = on_open
        self.window = None
        self._delegate = None
        self._entries = []
        self._rows = []
        self._table = None
        self._search = None
        self._summary = None
        self._feedback = None
        self._final_view = None
        self._raw_view = None
        self._copy_final_button = None
        self._copy_raw_button = None

    def show(self):
        if self.window is None:
            self._build_window()
        self.refresh()
        self.window.makeKeyAndOrderFront_(None)
        AppKit.NSApp.activateIgnoringOtherApps_(True)

    def close(self):
        if self.window is not None:
            self.window.close()

    def _build_window(self):
        style = (
            AppKit.NSTitledWindowMask
            | AppKit.NSClosableWindowMask
            | AppKit.NSMiniaturizableWindowMask
            | AppKit.NSResizableWindowMask
        )
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, self.WIDTH, self.HEIGHT), style, AppKit.NSBackingStoreBuffered, False
        )
        self.window.setTitle_(t("history_title"))
        self.window.setMinSize_(NSMakeSize(self.WIDTH, self.HEIGHT))
        self.window.setReleasedWhenClosed_(False)
        self.window.setTabbingMode_(AppKit.NSWindowTabbingModeDisallowed)
        apply_window(self.window)
        self.window.center()
        self._delegate = _HistoryDelegate.alloc().initWithController_(self)
        content = self.window.contentView()
        top_mask = AppKit.NSViewWidthSizable | AppKit.NSViewMinYMargin

        toolbar = material_view(NSMakeRect(0, 582, 900, 58), "content")
        toolbar.setAutoresizingMask_(top_mask)
        content.addSubview_(toolbar)
        self._search = AppKit.NSSearchField.alloc().initWithFrame_(NSMakeRect(20, 596, 722, 28))
        self._search.setPlaceholderString_(t("history_search_placeholder"))
        self._search.setDelegate_(self._delegate)
        self._search.setAutoresizingMask_(top_mask)
        self._search.cell().setSendsSearchStringImmediately_(True)
        content.addSubview_(self._search)
        refresh = self._button(content, t("history_refresh"), b"onRefresh:", 758, 593, 122)
        refresh.setAutoresizingMask_(AppKit.NSViewMinXMargin | AppKit.NSViewMinYMargin)

        scroll = AppKit.NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 330, 900, 252))
        scroll.setHasVerticalScroller_(True)
        scroll.setHasHorizontalScroller_(False)
        scroll.setBorderType_(AppKit.NSNoBorder)
        scroll.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
        content.addSubview_(scroll)
        self._table = AppKit.NSTableView.alloc().initWithFrame_(scroll.bounds())
        self._table.setUsesAlternatingRowBackgroundColors_(True)
        self._table.setAllowsMultipleSelection_(False)
        self._table.setAllowsEmptySelection_(True)
        self._table.setRowHeight_(30)
        self._table.setStyle_(AppKit.NSTableViewStyleFullWidth)
        self._table.setColumnAutoresizingStyle_(AppKit.NSTableViewLastColumnOnlyAutoresizingStyle)
        for identifier, label, width in (
            ("time_label", "history_column_time", 164),
            ("app_label", "history_column_app", 124),
            ("outcome_label", "history_column_outcome", 122),
            ("preview", "history_column_text", 420),
        ):
            column = AppKit.NSTableColumn.alloc().initWithIdentifier_(identifier)
            column.headerCell().setStringValue_(t(label))
            column.setWidth_(width)
            column.setMinWidth_(80)
            column.setEditable_(False)
            column.dataCell().setLineBreakMode_(AppKit.NSLineBreakByTruncatingTail)
            self._table.addTableColumn_(column)
        self._table.setDataSource_(self._delegate)
        self._table.setDelegate_(self._delegate)
        scroll.setDocumentView_(self._table)

        self._summary = self._label(content, "", 20, 301, 650, 20)
        self._summary.setTextColor_(AppKit.NSColor.secondaryLabelColor())
        self._summary.setAutoresizingMask_(AppKit.NSViewWidthSizable)
        self._vocabulary_button = self._button(content, "热词详情" if get_language() == "zh" else "Vocabulary details",
                                               b"onVocabulary:", 700, 295, 180)
        self._vocabulary_button.setAutoresizingMask_(AppKit.NSViewMinXMargin)
        comparison = AppKit.NSSplitView.alloc().initWithFrame_(NSMakeRect(20, 64, 860, 228))
        comparison.setVertical_(True)
        comparison.setDividerStyle_(AppKit.NSSplitViewDividerStyleThin)
        comparison.setAutoresizingMask_(AppKit.NSViewWidthSizable)
        content.addSubview_(comparison)
        final_panel = AppKit.NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 420, 228))
        raw_panel = AppKit.NSView.alloc().initWithFrame_(NSMakeRect(421, 0, 439, 228))
        comparison.addArrangedSubview_(final_panel)
        comparison.addArrangedSubview_(raw_panel)
        self._label(final_panel, t("history_final_text"), 0, 202, 240, 22, bold=True)
        self._copy_final_button = self._button(final_panel, t("history_copy_final"), b"onCopyFinal:", 272, 196, 138)
        self._copy_final_button.setAutoresizingMask_(AppKit.NSViewMinXMargin)
        self._final_view = self._text_view(final_panel, 0, 0, 410, 194)
        self._label(raw_panel, t("history_raw_text"), 10, 202, 240, 22, bold=True)
        self._copy_raw_button = self._button(raw_panel, t("history_copy_raw"), b"onCopyRaw:", 301, 196, 138)
        self._copy_raw_button.setAutoresizingMask_(AppKit.NSViewMinXMargin)
        self._raw_view = self._text_view(raw_panel, 10, 0, 429, 194)
        comparison.adjustSubviews()
        self._feedback = self._label(content, "", 20, 21, 370, 22)
        self._feedback.setTextColor_(AppKit.NSColor.secondaryLabelColor())
        self._feedback.setAutoresizingMask_(AppKit.NSViewWidthSizable)
        self._open_button = self._button(content, "打开并编辑" if get_language() == "zh" else "Open in editor",
                                         b"onOpen:", 420, 15, 160)
        style_button(self._open_button, primary=True)
        self._open_button.setAutoresizingMask_(AppKit.NSViewMinXMargin)
        export = self._button(content, t("stats_btn_export"), b"onExport:", 594, 15, 150)
        export.setAutoresizingMask_(AppKit.NSViewMinXMargin)
        close = self._button(content, t("stats_btn_close"), b"onClose:", 758, 15, 122)
        close.setAutoresizingMask_(AppKit.NSViewMinXMargin)
        close.setKeyEquivalent_("\x1b")

    def _label(self, parent, text, x, y, width, height, *, bold=False):
        label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, width, height))
        label.setStringValue_(text)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(True)
        label.setFont_(AppKit.NSFont.boldSystemFontOfSize_(14) if bold else AppKit.NSFont.systemFontOfSize_(13))
        label.setTextColor_(color("text"))
        label.cell().setLineBreakMode_(AppKit.NSLineBreakByTruncatingTail)
        parent.addSubview_(label)
        return label

    def _button(self, parent, title, action, x, y, width):
        button = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(x, y, width, 32))
        button.setTitle_(title)
        button.setBezelStyle_(AppKit.NSBezelStyleRounded)
        button.setTarget_(self._delegate)
        button.setAction_(action)
        style_button(button)
        parent.addSubview_(button)
        return button

    def _text_view(self, parent, x, y, width, height):
        scroll = AppKit.NSScrollView.alloc().initWithFrame_(NSMakeRect(x, y, width, height))
        scroll.setHasVerticalScroller_(True)
        scroll.setHasHorizontalScroller_(False)
        scroll.setBorderType_(AppKit.NSNoBorder)
        scroll.setAutoresizingMask_(AppKit.NSViewWidthSizable)
        parent.addSubview_(scroll)
        view = AppKit.NSTextView.alloc().initWithFrame_(scroll.contentView().bounds())
        view.setEditable_(False)
        view.setSelectable_(True)
        view.setRichText_(False)
        view.setFont_(AppKit.NSFont.systemFontOfSize_(15))
        view.setTextColor_(color("text"))
        view.setBackgroundColor_(color("surface"))
        view.setTextContainerInset_(NSMakeSize(8, 7))
        view.setVerticallyResizable_(True)
        view.setHorizontallyResizable_(False)
        view.setAutoresizingMask_(AppKit.NSViewWidthSizable)
        view.textContainer().setWidthTracksTextView_(True)
        scroll.setDocumentView_(view)
        return view

    def refresh(self):
        self._entries = self.history.snapshot()
        if self._table is not None:
            self._filter_rows()

    def _selected_entry(self):
        index = self._table.selectedRow() if self._table is not None else -1
        return self._rows[index] if 0 <= index < len(self._rows) else None

    def _filter_rows(self):
        selected = self._selected_entry()
        selected_id = selected.get("id") if selected else None
        query = self._search.stringValue() if self._search is not None else ""
        self._rows = history_window_rows(self._entries, query)
        self._table.reloadData()
        if self._rows:
            index = next((idx for idx, row in enumerate(self._rows) if row.get("id") == selected_id), 0)
            self._table.selectRowIndexes_byExtendingSelection_(NSIndexSet.indexSetWithIndex_(index), False)
        else:
            self._table.deselectAll_(None)
        if not self._entries:
            message = t("history_empty")
        elif not self._rows:
            message = t("history_no_matches")
        else:
            message = t("history_count", shown=len(self._rows), total=len(self._entries))
        self._feedback.setStringValue_(message)
        self._update_selection()

    def _update_selection(self):
        entry = self._selected_entry()
        final_text = str((entry or {}).get("polished") or (entry or {}).get("raw") or "")
        raw_text = str((entry or {}).get("raw") or "")
        self._final_view.setString_(final_text)
        self._raw_view.setString_(raw_text)
        self._copy_final_button.setEnabled_(bool(final_text))
        self._copy_raw_button.setEnabled_(bool(raw_text))
        self._open_button.setEnabled_(entry is not None and self._on_open is not None)
        self._vocabulary_button.setEnabled_(bool(entry and (entry.get("hotword_terms") or entry.get("hotword_changes"))))
        self._summary.setStringValue_(
            t("history_selection", time=entry["time_label"], app=entry["app_label"], outcome=entry["outcome_label"])
            if entry else t("history_select_record")
        )

    def open_selected(self):
        entry = self._selected_entry()
        if entry is None or self._on_open is None:
            return False
        opened = self._on_open(entry["id"])
        if opened:
            self.close()
        return bool(opened)

    def show_vocabulary_details(self):
        entry = self._selected_entry()
        if entry is None:
            return
        chinese = get_language() == "zh"
        terms = entry.get("hotword_terms") or []
        changes = entry.get("hotword_changes") or []
        lines = ["识别提示" if chinese else "Recognition hints", ", ".join(terms) or ("没有记录" if chinese else "No recorded hints"), "",
                 "实际纠错" if chinese else "Applied corrections"]
        lines.extend(f"{change['original']} → {change['replacement']}" for change in changes)
        if not changes:
            lines.append("没有文字替换记录" if chinese else "No recorded replacements")
        alert = AppKit.NSAlert.alloc().init()
        alert.setMessageText_("这次听写的热词" if chinese else "Vocabulary for this dictation")
        alert.setInformativeText_(entry["time_label"])
        scroll = AppKit.NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 0, 500, 230))
        scroll.setHasVerticalScroller_(True)
        view = AppKit.NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, 480, 230))
        view.setEditable_(False)
        view.setSelectable_(True)
        view.setFont_(AppKit.NSFont.systemFontOfSize_(14))
        view.setString_("\n".join(lines))
        view.setVerticallyResizable_(True)
        view.setHorizontallyResizable_(False)
        view.textContainer().setWidthTracksTextView_(True)
        scroll.setDocumentView_(view)
        alert.setAccessoryView_(scroll)
        alert.addButtonWithTitle_("关闭" if chinese else "Close")
        alert.runModal()

    def copy_selected(self, field="polished") -> bool:
        entry = self._selected_entry()
        text = str((entry or {}).get(field) or "")
        if field == "polished" and not text:
            text = str((entry or {}).get("raw") or "")
        if not text:
            self._feedback.setStringValue_(t("history_nothing_to_copy"))
            return False
        pasteboard = AppKit.NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        copied = bool(pasteboard.setString_forType_(text, AppKit.NSPasteboardTypeString))
        self._feedback.setStringValue_(t("history_copied") if copied else t("history_copy_failed"))
        return copied

    def export_history(self):
        panel = AppKit.NSSavePanel.savePanel()
        panel.setTitle_(t("stats_btn_export"))
        panel.setAllowedFileTypes_(["txt", "md", "csv", "json"])
        panel.setNameFieldStringValue_("speaktype-history.md")
        if panel.runModal() != AppKit.NSModalResponseOK or panel.URL() is None:
            return
        saved_path = self.history.export(panel.URL().path())
        self._feedback.setStringValue_(t("stats_export_done_body", path=str(saved_path)))
