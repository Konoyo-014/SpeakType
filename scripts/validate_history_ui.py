import json
from pathlib import Path
from tempfile import TemporaryDirectory

import AppKit
from Foundation import NSDate, NSMakeSize, NSRunLoop

from speaktype.history import DictationHistory
from speaktype.history_window import HistoryWindowController, history_window_rows
from speaktype.i18n import set_language, t


def advance_ui():
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.08))


AppKit.NSApplication.sharedApplication()
work_dir = Path(__file__).resolve().parents[1] / "work"
work_dir.mkdir(parents=True, exist_ok=True)
set_language("zh")
pasteboard = AppKit.NSPasteboard.generalPasteboard()
original_data = {
    kind: pasteboard.dataForType_(kind)
    for kind in pasteboard.types() or []
    if pasteboard.dataForType_(kind) is not None
}

try:
    with TemporaryDirectory(prefix="history-window-", dir=work_dir) as directory:
        history = DictationHistory(path=Path(directory) / "history.json")
        failed_id = history.add(
            "今天检查 Qwen ASR 的识别结果",
            "今天检查 Qwen3-ASR 的识别结果。\n支持多行内容。",
            "TextEdit",
            3.2,
            outcome="pending",
        )
        assert history.set_outcome(failed_id, "failed")
        sent_id = history.add("hello", "Hello, world.", "Safari", 1.3, outcome="sent")
        assert json.loads(history.path.read_text(encoding="utf-8"))[0]["outcome"] == "failed"
        controller = HistoryWindowController(history)
        controller.show()
        advance_ui()
        assert controller._table.numberOfRows() == 2
        assert controller._selected_entry()["id"] == sent_id
        assert controller._final_view.string() == "Hello, world."

        controller._search.setStringValue_("Qwen3-ASR")
        controller._filter_rows()
        advance_ui()
        assert controller._table.numberOfRows() == 1
        assert controller._selected_entry()["id"] == failed_id
        assert controller._final_view.string() == "今天检查 Qwen3-ASR 的识别结果。\n支持多行内容。"
        assert controller._raw_view.string() == "今天检查 Qwen ASR 的识别结果"
        controller._copy_final_button.performClick_(None)
        assert pasteboard.stringForType_(AppKit.NSPasteboardTypeString) == controller._final_view.string()
        controller._copy_raw_button.performClick_(None)
        assert pasteboard.stringForType_(AppKit.NSPasteboardTypeString) == controller._raw_view.string()
        assert not controller._final_view.isEditable()
        assert controller._final_view.isSelectable()
        initial_text_width = controller._final_view.frame().size.width
        controller.window.setContentSize_(NSMakeSize(1100, 800))
        advance_ui()
        assert controller._final_view.frame().size.width > initial_text_width
        assert controller._final_view.string() == "今天检查 Qwen3-ASR 的识别结果。\n支持多行内容。"

        controller._search.setStringValue_("没有符合的文本")
        controller._filter_rows()
        advance_ui()
        assert controller._table.numberOfRows() == 0
        assert controller._feedback.stringValue() == t("history_no_matches")
        assert not controller._copy_final_button.isEnabled()
        clipboard_before = pasteboard.stringForType_(AppKit.NSPasteboardTypeString)
        assert not controller.copy_selected()
        assert pasteboard.stringForType_(AppKit.NSPasteboardTypeString) == clipboard_before

        controller._search.setStringValue_("Safari")
        controller._filter_rows()
        assert len(controller._rows) == 1
        assert controller._rows[0]["outcome_label"] == t("history_outcome_sent")
        controller.close()
        controller.show()
        advance_ui()
        assert controller.window.isVisible()
        assert controller._selected_entry()["id"] == sent_id
        history.clear()
        controller.refresh()
        advance_ui()
        assert controller._table.numberOfRows() == 0
        assert controller._feedback.stringValue() == t("history_empty")
        assert controller._final_view.string() == ""
        assert controller._raw_view.string() == ""
        assert not controller._copy_raw_button.isEnabled()
        controller.close()

        set_language("en")
        rows = history_window_rows([
            {"timestamp": "2026-11-01T01:40:00", "raw": "原始文本", "polished": "Final Text", "app": "Mail", "outcome": "sent"}
        ], "UNVERIFIED")
        assert len(rows) == 1
        assert rows[0]["outcome_label"] == "Sent, unverified"
        english_controller = HistoryWindowController(history)
        english_controller.show()
        advance_ui()
        assert english_controller.window.title() == "SpeakType — Dictation History"
        assert english_controller._table.tableColumns()[0].headerCell().stringValue() == "Time"
        assert english_controller._feedback.stringValue() == t("history_empty")
        english_controller.close()
        set_language("zh")
        print("Native history window verified: search, selection, original/final text, real copy-button actions, clipboard, sent/failed outcomes, empty state, refresh, resizing, close/reopen, Chinese/English controls.")
finally:
    pasteboard.clearContents()
    for kind, data in original_data.items():
        pasteboard.setData_forType_(data, kind)
