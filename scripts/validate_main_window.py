import json
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
bundle = os.environ.get("SPEAKTYPE_TEST_BUNDLE")
if not bundle:
    sys.path.insert(0, str(root))

import AppKit
from Foundation import NSDate, NSIndexSet, NSMakeSize, NSRunLoop

from speaktype.app import SpeakTypeApp
from speaktype.config import CONFIG_DIR, DEFAULT_CONFIG, load_config, save_config
from speaktype.i18n import set_language
from speaktype.main_window import LABELS, MainWindowController, PHASES, TRANSLATION_LANGUAGES


assert CONFIG_DIR.is_relative_to(root / "work"), "Use SPEAKTYPE_CONFIG_DIR under the repository work directory"
if bundle:
    assert Path(sys.prefix).resolve().is_relative_to(Path(bundle).resolve())
    assert Path(sys.modules["speaktype.main_window"].__file__).resolve().is_relative_to(Path(bundle).resolve())


def advance():
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.05))


save_config({**DEFAULT_CONFIG, "setup_completed": True, "polish_enabled": False,
             "translate_enabled": False, "sound_feedback": False,
             "hotword_learning_enabled": False, "hotword_context_enabled": False})
AppKit.NSApplication.sharedApplication()
application = SpeakTypeApp()
application.history.clear()
first_id = application.history.add("手动输入的原始文本：Unicode 🙂 café。", "待编辑的最终文本。", "TextEdit", 1.5, outcome="saved")
second_id = application.history.add("第二条手动输入。\n包含原始换行。", "第二条最终文本。\n保留换行。", "Notes", 2.3, outcome="cancelled")
report = {"runtime": bundle or "source", "scope": "Native controls with explicit state inputs and real application callbacks, files and clipboard", "phases": [], "checks": []}
pasteboard = AppKit.NSPasteboard.generalPasteboard()
original_clipboard = {kind: pasteboard.dataForType_(kind) for kind in pasteboard.types() or [] if pasteboard.dataForType_(kind) is not None}


def build_controller(language):
    return MainWindowController(
        on_record=application._main_record, on_cancel=application._main_cancel,
        on_copy=application._main_copy, on_insert=application._main_insert,
        on_polish=lambda text: application._main_transform(text, False),
        on_translate=lambda text: application._main_transform(text, True),
        on_history=lambda: application._show_history(None),
        on_settings=lambda: application._open_settings(None),
        on_setup=application._show_setup_center,
        on_dictionary=lambda: application._open_dict(None),
        on_recent=application._main_select_recent,
        on_target=application._main_select_target,
        on_translate_language=application._main_set_translate_language,
        on_edit=application._main_edit,
        language=language,
    )


targets = [{"name": str(item.localizedName()), "bundle_id": str(item.bundleIdentifier() or ""),
            "pid": int(item.processIdentifier())}
           for item in AppKit.NSWorkspace.sharedWorkspace().runningApplications()
           if item.activationPolicy() == AppKit.NSApplicationActivationPolicyRegular
           and item.processIdentifier() != os.getpid() and item.localizedName() != "SpeakType"]
assert targets, "The native target picker needs an actual running external application"
readiness = [{"key": key, "status": "ready", "detail": f"UI state input: {key}",
              "action": key, "action_label": "查看设置"}
             for key in ("microphone", "asr", "llm", "accessibility", "hotkey")]
state = {"phase": "idle", "ready": True, "busy": False, "raw": "", "final": "", "partial": "",
         "elapsed": 0, "level": 0, "hotkey": "Right Command", "readiness": readiness,
         "target_name": "", "target_apps": targets, "translate_target": "en",
         "recent": application.history.get_recent(8)}
controller = build_controller("zh")
application._main_controller = controller
application._main_state.update(state)

try:
    controller.update_state(state)
    controller.show()
    advance()
    assert controller.window.isVisible()
    assert controller.window.contentView().frame().size == NSMakeSize(1000, 720)
    assert controller._record_button.isEnabled()
    assert not controller._cancel_button.isEnabled()
    assert not controller._copy_button.isEnabled()
    assert not controller._insert_button.isEnabled()
    assert not controller._raw_view.isEditable() and controller._raw_view.isSelectable()
    assert controller._final_view.isEditable()
    assert controller._final_view.allowsUndo()
    assert not controller._raw_placeholder.isHidden() and not controller._final_placeholder.isHidden()
    assert controller._target_picker.numberOfItems() == len(targets) + 1
    assert controller._translation_picker.numberOfItems() == len(TRANSLATION_LANGUAGES)
    assert all(card["status"].stringValue() for card in controller._readiness_cards.values())
    report["checks"].append("Native window, empty text, five readiness items, actual running target applications")

    controller._recent_table.selectRowIndexes_byExtendingSelection_(NSIndexSet.indexSetWithIndex_(0), False)
    advance()
    selected_id = controller._recent[0]["id"]
    selected = next(item for item in application.history.snapshot() if item["id"] == selected_id)
    assert application._latest_dictation["id"] == selected_id
    assert controller._raw_view.string() == selected["raw"]
    assert controller.get_final_text() == selected["polished"]
    rendered = controller._delegate.tableView_objectValueForTableColumn_row_(controller._recent_table, None, 0)
    assert "已取消" in rendered
    rendered = controller._delegate.tableView_objectValueForTableColumn_row_(controller._recent_table, None, 1)
    assert "已保存，待插入" in rendered
    edited = "用户通过编辑区输入：🙂 café 한국어 日本語。\n第二行保留。"
    controller._final_view.setSelectedRange_((0, len(controller.get_final_text().encode("utf-16-le")) // 2))
    controller._final_view.insertText_replacementRange_(edited, controller._final_view.selectedRange())
    advance()
    assert controller.get_final_text() == edited
    controller._final_view.breakUndoCoalescing()
    controller._final_view.insertText_replacementRange_("可以撤销的输入。", controller._final_view.selectedRange())
    assert controller._final_view.undoManager().canUndo()
    controller._final_view.undoManager().undo()
    assert controller.get_final_text() == edited
    controller._final_view.undoManager().redo()
    assert controller.get_final_text() == edited + "可以撤销的输入。"
    controller._final_view.undoManager().undo()
    assert controller.get_final_text() == edited
    advance()
    assert controller._pending_edit == edited
    assert next(item for item in application.history.snapshot() if item["id"] == selected_id)["polished"] == selected["polished"]
    controller.update_state({**controller._snapshot, "level": 0.63, "elapsed": 65.5})
    assert controller.get_final_text() == edited
    assert controller._level.doubleValue() == 63
    assert "01:05" in controller._elapsed_label.stringValue()
    assert controller._copy_button.isEnabled()
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.5))
    assert controller._pending_edit is None and controller._edit_timer is None
    assert next(item for item in application.history.snapshot() if item["id"] == selected_id)["polished"] == edited
    assert next(item for item in application.history.snapshot() if item["id"] == selected_id)["outcome"] == "saved"
    controller._final_view.undoManager().undo()
    assert controller.get_final_text() == selected["polished"]
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.5))
    assert next(item for item in application.history.snapshot() if item["id"] == selected_id)["polished"] == selected["polished"]
    controller._final_view.undoManager().redo()
    assert controller.get_final_text() == edited
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.5))
    assert next(item for item in application.history.snapshot() if item["id"] == selected_id)["polished"] == edited
    controller._final_view.insertText_replacementRange_("\n立即复制的编辑。", controller._final_view.selectedRange())
    edited = controller.get_final_text()
    assert controller._pending_edit == edited
    controller._copy_button.performClick_(None)
    assert controller._pending_edit is None
    assert pasteboard.stringForType_(AppKit.NSPasteboardTypeString) == edited
    persisted = next(item for item in application.history.snapshot() if item["id"] == selected_id)
    assert persisted["polished"] == edited and persisted["raw"] == selected["raw"]
    assert next(item for item in json.loads(application.history.path.read_text(encoding="utf-8")) if item["id"] == selected_id)["polished"] == edited
    controller._final_view.insertText_replacementRange_("\n切换记录之前的编辑。", controller._final_view.selectedRange())
    edited = controller.get_final_text()
    controller._recent_table.selectRowIndexes_byExtendingSelection_(NSIndexSet.indexSetWithIndex_(1), False)
    advance()
    assert controller._pending_edit is None
    assert next(item for item in application.history.snapshot() if item["id"] == selected_id)["polished"] == edited
    assert application._latest_dictation["id"] == first_id
    assert controller._recent_table.selectedRow() == 1
    controller._recent_table.selectRowIndexes_byExtendingSelection_(NSIndexSet.indexSetWithIndex_(0), False)
    advance()
    assert controller.get_final_text() == edited
    report["checks"].append("Real history selection, saved/cancelled labels, Unicode editing, native undo/redo with persisted results, 0.4-second native debounce, edit preservation, clipboard and same-record persistence, flush before recent selection")

    frontmost_pid = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication().processIdentifier()
    controller._target_picker.selectItemAtIndex_(1)
    controller._target_picker.sendAction_to_(controller._target_picker.action(), controller._target_picker.target())
    advance()
    assert application._last_external_app["pid"] == targets[0]["pid"]
    assert AppKit.NSWorkspace.sharedWorkspace().frontmostApplication().processIdentifier() == frontmost_pid
    assert controller._insert_button.isEnabled()
    assert targets[0]["name"] in controller._insert_button.title()
    duplicate = next((item for item in targets if sum(other["name"] == item["name"] for other in targets) > 1), None)
    if duplicate is not None:
        duplicate_index = max(index for index, item in enumerate(targets) if item["name"] == duplicate["name"])
        controller._target_picker.selectItemAtIndex_(duplicate_index + 1)
        controller._target_picker.sendAction_to_(controller._target_picker.action(), controller._target_picker.target())
        advance()
        assert application._last_external_app["pid"] == targets[duplicate_index]["pid"]
        assert controller._target_picker.indexOfSelectedItem() == duplicate_index + 1
        report["checks"].append("Actual same-name running applications remain selected by PID")
    controller._final_view.insertText_replacementRange_("\n切换翻译语言之前的编辑。", controller._final_view.selectedRange())
    edited = controller.get_final_text()
    controller._translation_picker.selectItemAtIndex_(3)
    controller._translation_picker.sendAction_to_(controller._translation_picker.action(), controller._translation_picker.target())
    advance()
    assert application.config["translate_target"] == "ko" and load_config()["translate_target"] == "ko"
    assert controller._translation_picker.indexOfSelectedItem() == 3
    assert controller._pending_edit is None
    assert next(item for item in application.history.snapshot() if item["id"] == selected_id)["polished"] == edited
    report["checks"].append("Target selection keeps frontmost application and does not insert; translation language persists to isolated config")

    baseline = {**controller._snapshot, "raw": selected["raw"], "final": edited, "ready": True, "busy": False,
                "target_name": targets[0]["name"], "target_pid": targets[0]["pid"], "target_apps": targets, "readiness": readiness}
    for phase in sorted(PHASES):
        busy = phase in {"loading", "transcribing", "polishing", "translating", "delivering"}
        controller.update_state({**baseline, "phase": phase, "busy": busy,
                                 "partial": "真正显示在原生控件中的状态验证文本" if phase == "recording" else ""})
        blocked = busy or phase == "recording"
        assert bool(controller._record_button.isEnabled()) == (phase == "recording" or not busy), phase
        assert bool(controller._cancel_button.isEnabled()) == (blocked and phase != "delivering"), phase
        assert bool(controller._copy_button.isEnabled()) == (not blocked), phase
        assert bool(controller._insert_button.isEnabled()) == (not blocked), phase
        assert bool(controller._polish_button.isEnabled()) == (not blocked), phase
        assert bool(controller._translate_button.isEnabled()) == (not blocked), phase
        assert bool(controller._final_view.isEditable()) == (not blocked), phase
        assert bool(controller._recent_table.isEnabled()) == (not blocked), phase
        assert bool(controller._target_picker.isEnabled()) == (not blocked), phase
        assert bool(controller._translation_picker.isEnabled()) == (not blocked), phase
        assert controller._raw_view.string() == ("真正显示在原生控件中的状态验证文本" if phase == "recording" else selected["raw"]), phase
        assert controller.get_final_text() == edited, phase
        assert controller._phase_label.stringValue() == LABELS["zh"][phase]
        report["phases"].append(phase)
    controller.update_state({**baseline, "phase": "idle", "ready": False})
    assert controller._phase_label.stringValue() == "请先完成准备"
    assert not controller._record_button.isEnabled()
    controller.update_state({**baseline, "phase": "recording", "ready": False})
    assert controller._record_button.isEnabled() and controller._record_button.title() == "停止录音"
    unavailable = [{**item, "status": "optional" if item["key"] == "llm" else item["status"]} for item in readiness]
    controller.update_state({**baseline, "phase": "done", "readiness": unavailable, "target_name": ""})
    assert controller._record_button.isEnabled() and controller._copy_button.isEnabled()
    assert not controller._polish_button.isEnabled() and not controller._translate_button.isEnabled()
    assert not controller._insert_button.isEnabled()
    controller.update_state({**baseline, "phase": "delivering"})
    assert not controller._cancel_button.isEnabled()
    report["checks"].append("All phases, recording stop, busy editing/action exclusion, delivering cancellation exclusion, optional LLM, missing target")

    long_text = "\n".join(f"第 {index} 行：真实 NSTextView 中的 Unicode 🙂 文本。" for index in range(1, 81))
    controller.update_state({**baseline, "phase": "done", "raw": long_text, "final": long_text})
    advance()
    controller._raw_view.layoutManager().ensureLayoutForTextContainer_(controller._raw_view.textContainer())
    controller._final_view.layoutManager().ensureLayoutForTextContainer_(controller._final_view.textContainer())
    assert controller._raw_view.layoutManager().usedRectForTextContainer_(controller._raw_view.textContainer()).size.height > controller._raw_scroll.contentSize().height
    assert controller._final_view.layoutManager().usedRectForTextContainer_(controller._final_view.textContainer()).size.height > controller._final_scroll.contentSize().height
    original_width = controller._final_view.frame().size.width
    original_height = controller._final_scroll.frame().size.height
    original_content_height = controller.window.contentView().frame().size.height
    controller.window.setContentSize_(NSMakeSize(1240, 900))
    advance()
    assert controller._final_view.frame().size.width > original_width
    actual_size = controller.window.contentView().frame().size
    assert controller._final_scroll.frame().size.height == original_height + actual_size.height - original_content_height
    report["resize"] = {"requested": [1240, 900], "actual": [actual_size.width, actual_size.height],
                        "screen_visible_height": controller.window.screen().visibleFrame().size.height}
    assert controller.get_final_text() == long_text
    controller.window.setContentSize_(NSMakeSize(1000, 720))
    controller.update_state({**baseline, "phase": "done"})
    advance()
    identity = controller.window.windowNumber()
    controller._final_view.insertText_replacementRange_("\n关闭之前的编辑。", controller._final_view.selectedRange())
    closed_text = controller.get_final_text()
    assert controller._pending_edit == closed_text
    controller.window.performClose_(None)
    assert controller._pending_edit is None
    assert next(item for item in application.history.snapshot() if item["id"] == selected_id)["polished"] == closed_text
    controller.show()
    advance()
    assert controller.window.windowNumber() == identity and controller.window.isVisible()
    assert controller._record_button.keyEquivalent() == "r"
    assert controller._insert_button.keyEquivalent() == "\r"
    assert controller._copy_button.keyEquivalentModifierMask() == AppKit.NSEventModifierFlagCommand | AppKit.NSEventModifierFlagShift
    assert controller._final_view.accessibilityLabel() == "最终文本"
    report["checks"].append("Long raw/final scrolling, window resizing, close/reopen reuse, keyboard equivalents and accessibility labels")

    controller._history_button.performClick_(None)
    advance()
    assert application._history_controller.window.isVisible()
    application._history_controller.close()
    controller._settings_button.performClick_(None)
    advance()
    assert application._settings_controller.window.isVisible()
    application._settings_controller._do_cancel()
    controller._dictionary_button.performClick_(None)
    advance()
    assert application._dict_controller.window.isVisible()
    application._dict_controller.window.close()
    report["checks"].append("Real history, preferences and dictionary windows opened through main-window buttons")

    controller.close()
    set_language("en")
    application.history.add("保留取消状态的输入。", "Cancelled dictation retained for the native UI check.", outcome="cancelled")
    english = build_controller("en")
    application._main_controller = english
    english.update_state({**baseline, "phase": "done", "translate_target": "ko", "recent": application.history.get_recent(8)})
    english.show()
    advance()
    assert english._record_button.title() == "Start dictation"
    assert english._phase_label.stringValue() == "Text is ready"
    assert english._translation_picker.titleOfSelectedItem() == "한국어"
    assert english._target_picker.accessibilityLabel() == "Target app"
    english.update_state({**english._snapshot, "phase": "idle", "ready": False})
    assert english._phase_label.stringValue() == "Set up dictation"
    english.update_state({**english._snapshot, "phase": "done", "ready": True})
    recent_text = english._delegate.tableView_objectValueForTableColumn_row_(english._recent_table, None, 0)
    assert "Cancelled" in recent_text
    recent_text = english._delegate.tableView_objectValueForTableColumn_row_(english._recent_table, None, 1)
    assert "Saved; ready to insert" in recent_text
    if "--hold" in sys.argv:
        english.window.setTitle_("SpeakType — Main window validation")
        print("READY_MAIN_WINDOW_EN", flush=True)
        assert input().strip() == "continue"
        english.close()
        controller.window.setTitle_("SpeakType — 主窗口验证")
        controller.show()
        print("READY_MAIN_WINDOW_ZH", flush=True)
        assert input().strip() == "continue"
        controller.close()
    english.close()
    report["checks"].append("English controls and cancelled/saved state labels")
    destination = root / "work" / ("bundle-main-window-report.json" if bundle else "main-window-report.json")
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"REPORT {destination}")
finally:
    controller.close()
    if application._main_controller is not None:
        application._main_controller.close()
    application._status_overlay.hide()
    pasteboard.clearContents()
    for kind, data in original_clipboard.items():
        pasteboard.setData_forType_(data, kind)
