from __future__ import annotations

import math

import AppKit
import objc
from Foundation import (
    NSIndexSet, NSNotificationCenter, NSObject, NSMakeRect, NSMakeSize, NSTimer,
    NSUndoManagerDidRedoChangeNotification, NSUndoManagerDidUndoChangeNotification,
)


LABELS = {
    "zh": {
        "window": "SpeakType", "idle": "可以开始听写", "setup_needed": "请先完成准备", "loading": "正在准备",
        "recording": "正在录音", "transcribing": "正在识别语音", "polishing": "正在润色",
        "translating": "正在翻译", "delivering": "正在插入文本", "done": "文本已准备好", "error": "需要处理问题",
        "cancelled": "已取消", "start": "开始听写", "stop": "停止录音", "cancel": "取消",
        "raw": "原始转写", "partial": "实时转写", "final": "最终文本", "editable": "可以直接编辑",
        "raw_empty": "开始说话后，识别内容会显示在这里。",
        "final_empty": "最终文本会显示在这里。你可以编辑后再复制或插入。",
        "copy": "复制", "insert": "插入到 {target}", "insert_empty": "插入文本",
        "polish": "重新润色", "translate": "翻译", "recent": "最近听写",
        "recent_empty": "还没有听写记录", "recent_count": "{count} 条记录 · 点击查看完整内容",
        "history": "全部历史", "settings": "偏好设置", "dictionary": "词典与短语",
        "setup": "准备设置", "help": "使用帮助", "microphone": "麦克风", "asr": "语音识别",
        "llm": "润色与翻译", "accessibility": "插入权限", "hotkey_ready": "全局快捷键", "ready": "已就绪", "missing": "需要设置", "working": "正在检查",
        "optional": "可选", "unknown": "尚未检查", "fix": "处理", "record_level": "麦克风音量",
        "duration": "录音时长 {time}", "hotkey": "全局快捷键：{hotkey}", "hotkey_empty": "在偏好设置中选择全局快捷键",
        "target": "插入目标：{target}", "target_empty": "先点击其他应用的输入框，再返回 SpeakType 选择插入。",
        "target_picker": "插入目标", "choose_target": "选择其他应用", "translate_language": "翻译目标语言",
        "shortcuts": "⌘R 开始或停止 · ⌘↩ 插入 · ⇧⌘C 复制 · Esc 取消",
        "copy_tip": "复制当前最终文本（⇧⌘C）", "insert_tip": "把当前最终文本插入到此前选择的目标应用（⌘↩）",
        "polish_tip": "使用本地模型重新润色当前最终文本（⇧⌘P）",
        "translate_tip": "使用设置中的目标语言翻译当前最终文本（⇧⌘T）",
        "llm_missing": "请在准备设置中启用可用的本地语言模型。", "recent_accessibility": "最近听写记录",
        "outcome_pending": "正在处理", "outcome_inserted": "已验证插入", "outcome_sent": "已发送，未验证",
        "outcome_failed": "插入失败", "outcome_saved": "已保存，待插入", "outcome_cancelled": "已取消",
    },
    "en": {
        "window": "SpeakType", "idle": "Ready to dictate", "setup_needed": "Set up dictation", "loading": "Preparing",
        "recording": "Recording", "transcribing": "Transcribing", "polishing": "Polishing",
        "translating": "Translating", "delivering": "Inserting text", "done": "Text is ready", "error": "Action needed",
        "cancelled": "Cancelled", "start": "Start dictation", "stop": "Stop recording", "cancel": "Cancel",
        "raw": "Original transcription", "partial": "Live transcription", "final": "Final text", "editable": "Editable",
        "raw_empty": "Start speaking to see the transcription here.",
        "final_empty": "Your final text appears here. Edit it before copying or inserting.",
        "copy": "Copy", "insert": "Insert into {target}", "insert_empty": "Insert text",
        "polish": "Polish again", "translate": "Translate", "recent": "Recent dictations",
        "recent_empty": "No dictations yet", "recent_count": "{count} records · Select one to read it",
        "history": "All history", "settings": "Preferences", "dictionary": "Dictionary",
        "setup": "Setup", "help": "Help", "microphone": "Microphone", "asr": "Speech recognition",
        "llm": "Polishing & translation", "accessibility": "Text insertion", "hotkey_ready": "Global hotkey", "ready": "Ready", "missing": "Setup needed", "working": "Checking",
        "optional": "Optional", "unknown": "Not checked", "fix": "Resolve", "record_level": "Microphone level",
        "duration": "Recording time {time}", "hotkey": "Global hotkey: {hotkey}", "hotkey_empty": "Choose a global hotkey in Preferences",
        "target": "Insertion target: {target}", "target_empty": "Click an input field in another app, then return here to insert.",
        "target_picker": "Target app", "choose_target": "Choose another app", "translate_language": "Translation language",
        "shortcuts": "⌘R start or stop · ⌘↩ insert · ⇧⌘C copy · Esc cancel",
        "copy_tip": "Copy the current final text (⇧⌘C)", "insert_tip": "Insert the current final text into the previously selected app (⌘↩)",
        "polish_tip": "Polish the current final text with the local model (⇧⌘P)",
        "translate_tip": "Translate the current final text into the configured language (⇧⌘T)",
        "llm_missing": "Enable an available local language model in Setup.", "recent_accessibility": "Recent dictation records",
        "outcome_pending": "Processing", "outcome_inserted": "Verified insertion", "outcome_sent": "Sent, unverified",
        "outcome_failed": "Insertion failed", "outcome_saved": "Saved; ready to insert", "outcome_cancelled": "Cancelled",
    },
}

PHASES = frozenset(("idle", "loading", "cancelled", "recording", "transcribing", "polishing", "translating", "delivering", "done", "error"))
_BUSY_PHASES = frozenset(("loading", "transcribing", "polishing", "translating", "delivering"))
_TOP_RESIZE = AppKit.NSViewWidthSizable | AppKit.NSViewMinYMargin
_FILL_RESIZE = AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable
_COMMAND = AppKit.NSEventModifierFlagCommand
_SHIFT_COMMAND = _COMMAND | AppKit.NSEventModifierFlagShift
TRANSLATION_LANGUAGES = (("en", "English", "英语"), ("zh", "中文", "中文"), ("ja", "日本語", "日语"),
                         ("ko", "한국어", "韩语"), ("es", "Español", "西班牙语"),
                         ("fr", "Français", "法语"), ("de", "Deutsch", "德语"))


class _MainWindowDelegate(NSObject):
    def initWithController_(self, controller):
        self = objc.super(_MainWindowDelegate, self).init()
        if self is not None:
            self._controller = controller
        return self

    def onRecord_(self, sender):
        self._controller._on_record()

    def onCancel_(self, sender):
        self._controller.flush_edits()
        self._controller._callbacks["cancel"]()

    def onCopy_(self, sender):
        self._controller.flush_edits()
        self._controller._callbacks["copy"](self._controller.get_final_text())

    def onInsert_(self, sender):
        self._controller.flush_edits()
        self._controller._callbacks["insert"](self._controller.get_final_text())

    def onPolish_(self, sender):
        self._controller.flush_edits()
        self._controller._callbacks["polish"](self._controller.get_final_text())

    def onTranslate_(self, sender):
        self._controller.flush_edits()
        self._controller._callbacks["translate"](self._controller.get_final_text())

    def onTarget_(self, sender):
        index = sender.indexOfSelectedItem() - 1
        if self._controller._on_target is not None and 0 <= index < len(self._controller._target_apps):
            target = dict(self._controller._target_apps[index])
            self._controller._selected_target_pid = target.get("pid")
            self._controller.flush_edits()
            self._controller._on_target(target)

    def onTranslateLanguage_(self, sender):
        if self._controller._on_translate_language is not None:
            code = TRANSLATION_LANGUAGES[sender.indexOfSelectedItem()][0]
            self._controller.flush_edits()
            self._controller._on_translate_language(code)

    def onHistory_(self, sender):
        self._controller.flush_edits()
        self._controller._callbacks["history"]()

    def onSettings_(self, sender):
        self._controller.flush_edits()
        self._controller._callbacks["settings"]()

    def onDictionary_(self, sender):
        self._controller.flush_edits()
        self._controller._callbacks["dictionary"]()

    def onSetup_(self, sender):
        self._controller.flush_edits()
        self._controller._callbacks["setup"](None)

    def onReadinessAction_(self, sender):
        action = self._controller._readiness_actions.get(sender.tag())
        self._controller.flush_edits()
        self._controller._callbacks["setup"](action)

    def onHelp_(self, sender):
        self._controller.flush_edits()
        self._controller._callbacks["setup"]("help")

    def onEditTimer_(self, timer):
        self._controller.flush_edits()

    def windowShouldClose_(self, sender):
        self._controller.flush_edits()
        return True

    def numberOfRowsInTableView_(self, table):
        return len(self._controller._recent)

    def tableView_objectValueForTableColumn_row_(self, table, column, row):
        entry = self._controller._recent[row]
        time = str(entry.get("timestamp") or "").replace("T", " ")[:16]
        app = str(entry.get("app") or "")
        outcome = self._controller.labels.get(f"outcome_{entry.get('outcome')}", "")
        preview = " ".join(str(entry.get("polished") or entry.get("raw") or "").split())
        return f"{time}  {app}\n{outcome}\n{preview}"

    def tableViewSelectionDidChange_(self, notification):
        self._controller._select_recent()

    def textDidChange_(self, notification):
        if notification.object() == self._controller._final_view:
            self._controller._refresh_actions()
            self._controller._final_placeholder.setHidden_(bool(self._controller.get_final_text()))
            self._controller._schedule_edit()

    def onUndoRedo_(self, notification):
        self._controller._refresh_actions()
        self._controller._final_placeholder.setHidden_(bool(self._controller.get_final_text()))
        self._controller._schedule_edit()


class MainWindowController:
    WIDTH = 1000
    HEIGHT = 720

    def __init__(self, on_record, on_cancel, on_copy, on_insert, on_polish, on_translate,
                 on_history, on_settings, on_setup, on_dictionary, *, on_recent=None,
                 on_target=None, on_translate_language=None, on_edit=None, language="zh", labels=None):
        self._callbacks = {
            "record": on_record, "cancel": on_cancel, "copy": on_copy, "insert": on_insert,
            "polish": on_polish, "translate": on_translate, "history": on_history,
            "settings": on_settings, "setup": on_setup, "dictionary": on_dictionary,
        }
        for name, callback in self._callbacks.items():
            if not callable(callback):
                raise TypeError(f"Main window callback must be callable: {name}")
        for name, callback in (("on_recent", on_recent), ("on_target", on_target), ("on_translate_language", on_translate_language), ("on_edit", on_edit)):
            if callback is not None and not callable(callback):
                raise TypeError(f"{name} must be callable")
        self._on_recent = on_recent
        self._on_target = on_target
        self._on_translate_language = on_translate_language
        self._on_edit = on_edit
        self._language = "en" if language == "en" else "zh"
        self.labels = {**LABELS["en" if language == "en" else "zh"], **(labels or {})}
        self.window = None
        self._delegate = None
        self._snapshot = {}
        self._recent = []
        self._selected_recent_id = None
        self._suppress_selection = False
        self._last_final = None
        self._last_raw = None
        self._last_partial = None
        self._last_phase = None
        self._readiness_cards = {}
        self._readiness_actions = {}
        self._llm_ready = False
        self._target_apps = []
        self._selected_target_pid = None
        self._pending_edit = None
        self._edit_timer = None
        self._suppress_edit = False
        self._undo_manager = None
        self._disposed = False

    def _label(self, parent, text, frame, *, size=13, bold=False, color=None, resize=0):
        label = AppKit.NSTextField.labelWithString_(text)
        label.setFrame_(NSMakeRect(*frame))
        label.setFont_(AppKit.NSFont.boldSystemFontOfSize_(size) if bold else AppKit.NSFont.systemFontOfSize_(size))
        label.setLineBreakMode_(AppKit.NSLineBreakByTruncatingTail)
        label.setAutoresizingMask_(resize)
        label.setAccessibilityLabel_(text)
        if color is not None:
            label.setTextColor_(color)
        parent.addSubview_(label)
        return label

    def _button(self, parent, text, action, frame, *, key=None, modifiers=_COMMAND, resize=0):
        button = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(*frame))
        button.setTitle_(text)
        button.setBezelStyle_(AppKit.NSBezelStyleRounded)
        button.setTarget_(self._delegate)
        button.setAction_(action)
        button.setAutoresizingMask_(resize)
        button.setAccessibilityLabel_(text)
        if key is not None:
            button.setKeyEquivalent_(key)
            button.setKeyEquivalentModifierMask_(modifiers)
        parent.addSubview_(button)
        return button

    def _text_view(self, parent, frame, *, editable, placeholder):
        scroll = AppKit.NSScrollView.alloc().initWithFrame_(NSMakeRect(*frame))
        scroll.setBorderType_(AppKit.NSBezelBorder)
        scroll.setHasVerticalScroller_(True)
        scroll.setHasHorizontalScroller_(False)
        scroll.setAutoresizingMask_(_FILL_RESIZE if editable else _TOP_RESIZE)
        parent.addSubview_(scroll)
        view = AppKit.NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, frame[2] - 18, frame[3]))
        view.setEditable_(editable)
        view.setSelectable_(True)
        view.setRichText_(False)
        view.setAllowsUndo_(editable)
        view.setFont_(AppKit.NSFont.systemFontOfSize_(15))
        view.setTextContainerInset_(NSMakeSize(10, 9))
        view.setVerticallyResizable_(True)
        view.setHorizontallyResizable_(False)
        view.setAutoresizingMask_(AppKit.NSViewWidthSizable)
        view.textContainer().setWidthTracksTextView_(True)
        view.setAccessibilityLabel_(self.labels["final" if editable else "raw"])
        if editable:
            view.setDelegate_(self._delegate)
        scroll.setDocumentView_(view)
        hint = self._label(scroll, placeholder, (12, frame[3] - 32, frame[2] - 38, 20),
                           size=13, color=AppKit.NSColor.placeholderTextColor(), resize=_TOP_RESIZE)
        return view, hint, scroll

    def _popup(self, parent, action, frame, label, resize=0):
        popup = AppKit.NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(*frame), False)
        popup.setTarget_(self._delegate)
        popup.setAction_(action)
        popup.setAutoresizingMask_(resize)
        popup.setAccessibilityLabel_(label)
        popup.setToolTip_(label)
        parent.addSubview_(popup)
        return popup

    def _readiness_card(self, key):
        box = AppKit.NSBox.alloc().initWithFrame_(NSMakeRect(0, 0, 312, 80))
        box.setBoxType_(AppKit.NSBoxCustom)
        box.setBorderType_(AppKit.NSLineBorder)
        box.setBorderColor_(AppKit.NSColor.separatorColor())
        box.setFillColor_(AppKit.NSColor.controlBackgroundColor())
        box.setCornerRadius_(9)
        box.setContentViewMargins_(NSMakeSize(0, 0))
        box.heightAnchor().constraintEqualToConstant_(80).setActive_(True)
        content = box.contentView()
        title = self._label(content, self.labels[key], (12, 53, 286, 18), bold=True, resize=AppKit.NSViewWidthSizable)
        status = self._label(content, self.labels["unknown"], (12, 31, 145, 18), resize=AppKit.NSViewWidthSizable)
        detail = self._label(content, "", (12, 10, 286, 17), size=11,
                             color=AppKit.NSColor.secondaryLabelColor(), resize=AppKit.NSViewWidthSizable)
        action = self._button(content, self.labels["fix"], b"onReadinessAction:", (169, 27, 130, 28),
                              resize=AppKit.NSViewMinXMargin)
        action.setHidden_(True)
        self._readiness_cards[key] = {"box": box, "title": title, "status": status, "detail": detail, "action": action}
        return box

    def _build_window(self):
        AppKit.NSApplication.sharedApplication()
        self._delegate = _MainWindowDelegate.alloc().initWithController_(self)
        style = AppKit.NSTitledWindowMask | AppKit.NSClosableWindowMask | AppKit.NSMiniaturizableWindowMask | AppKit.NSResizableWindowMask
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, self.WIDTH, self.HEIGHT), style, AppKit.NSBackingStoreBuffered, False)
        self.window.setTitle_(self.labels["window"])
        self.window.setContentMinSize_(NSMakeSize(self.WIDTH, self.HEIGHT))
        self.window.setReleasedWhenClosed_(False)
        self.window.setTabbingMode_(AppKit.NSWindowTabbingModeDisallowed)
        self.window.setDelegate_(self._delegate)
        self.window.center()
        content = self.window.contentView()

        header = AppKit.NSView.alloc().initWithFrame_(NSMakeRect(20, 654, 960, 46))
        header.setAutoresizingMask_(_TOP_RESIZE)
        content.addSubview_(header)
        self._label(header, "SpeakType", (0, 11, 150, 32), size=24, bold=True)
        self._phase_label = self._label(header, "", (184, 25, 560, 21), size=16, bold=True, resize=AppKit.NSViewWidthSizable)
        self._status_label = self._label(header, "", (184, 3, 560, 19), size=12,
                                         color=AppKit.NSColor.secondaryLabelColor(), resize=AppKit.NSViewWidthSizable)
        self._spinner = AppKit.NSProgressIndicator.alloc().initWithFrame_(NSMakeRect(157, 20, 18, 18))
        self._spinner.setStyle_(AppKit.NSProgressIndicatorStyleSpinning)
        self._spinner.setDisplayedWhenStopped_(False)
        header.addSubview_(self._spinner)
        self._setup_button = self._button(header, self.labels["setup"], b"onSetup:", (756, 8, 98, 34), resize=AppKit.NSViewMinXMargin)
        self._settings_button = self._button(header, self.labels["settings"], b"onSettings:", (860, 8, 100, 34), key=",", resize=AppKit.NSViewMinXMargin)

        readiness = AppKit.NSStackView.alloc().initWithFrame_(NSMakeRect(20, 564, 960, 80))
        readiness.setOrientation_(AppKit.NSUserInterfaceLayoutOrientationHorizontal)
        readiness.setAlignment_(AppKit.NSLayoutAttributeCenterY)
        readiness.setDistribution_(AppKit.NSStackViewDistributionFillEqually)
        readiness.setSpacing_(12)
        readiness.setAutoresizingMask_(_TOP_RESIZE)
        for key in ("microphone", "asr", "llm"):
            readiness.addArrangedSubview_(self._readiness_card(key))
        content.addSubview_(readiness)

        controls = AppKit.NSView.alloc().initWithFrame_(NSMakeRect(20, 464, 960, 90))
        controls.setAutoresizingMask_(_TOP_RESIZE)
        content.addSubview_(controls)
        self._record_button = self._button(controls, self.labels["start"], b"onRecord:", (0, 31, 194, 48), key="r")
        self._record_button.setFont_(AppKit.NSFont.boldSystemFontOfSize_(17))
        self._cancel_button = self._button(controls, self.labels["cancel"], b"onCancel:", (202, 37, 86, 35), key="\x1b", modifiers=0)
        self._level = AppKit.NSProgressIndicator.alloc().initWithFrame_(NSMakeRect(310, 53, 178, 14))
        self._level.setStyle_(AppKit.NSProgressIndicatorStyleBar)
        self._level.setIndeterminate_(False)
        self._level.setMinValue_(0)
        self._level.setMaxValue_(100)
        self._level.setAccessibilityLabel_(self.labels["record_level"])
        controls.addSubview_(self._level)
        self._elapsed_label = self._label(controls, "", (310, 26, 178, 20), size=12, color=AppKit.NSColor.secondaryLabelColor())
        self._hotkey_label = self._label(controls, "", (510, 68, 450, 21), size=13, resize=AppKit.NSViewWidthSizable)
        self._label(controls, self.labels["target_picker"], (510, 42, 76, 20), size=12,
                    color=AppKit.NSColor.secondaryLabelColor())
        self._target_picker = self._popup(controls, b"onTarget:", (586, 38, 374, 28),
                                          self.labels["target_picker"], resize=AppKit.NSViewWidthSizable)
        for index, key in enumerate(("accessibility", "hotkey")):
            x = 310 + index * 330
            label = self._label(controls, "", (x, 8, 208, 20), size=11,
                                color=AppKit.NSColor.secondaryLabelColor())
            action = self._button(controls, self.labels["fix"], b"onReadinessAction:", (x + 210, 2, 110, 32))
            action.setHidden_(True)
            self._readiness_cards[key] = {"status": label, "action": action}

        body = AppKit.NSView.alloc().initWithFrame_(NSMakeRect(20, 58, 960, 404))
        body.setAutoresizingMask_(_FILL_RESIZE)
        content.addSubview_(body)
        editor = AppKit.NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 692, 404))
        editor.setAutoresizingMask_(_FILL_RESIZE)
        body.addSubview_(editor)
        self._raw_heading = self._label(editor, self.labels["raw"], (0, 382, 692, 22), bold=True, resize=_TOP_RESIZE)
        self._raw_view, self._raw_placeholder, self._raw_scroll = self._text_view(
            editor, (0, 276, 692, 98), editable=False, placeholder=self.labels["raw_empty"])
        self._label(editor, self.labels["final"], (0, 246, 380, 22), bold=True, resize=_TOP_RESIZE)
        self._label(editor, self.labels["editable"], (480, 246, 212, 20), size=12,
                    color=AppKit.NSColor.secondaryLabelColor(), resize=AppKit.NSViewMinXMargin | AppKit.NSViewMinYMargin)
        self._final_view, self._final_placeholder, self._final_scroll = self._text_view(
            editor, (0, 76, 692, 164), editable=True, placeholder=self.labels["final_empty"])
        self._copy_button = self._button(editor, self.labels["copy"], b"onCopy:", (0, 36, 94, 34), key="c", modifiers=_SHIFT_COMMAND)
        self._insert_button = self._button(editor, self.labels["insert_empty"], b"onInsert:", (102, 36, 248, 34), key="\r")
        self._polish_button = self._button(editor, self.labels["polish"], b"onPolish:", (358, 36, 132, 34), key="p", modifiers=_SHIFT_COMMAND)
        self._translate_button = self._button(editor, self.labels["translate"], b"onTranslate:", (498, 36, 86, 34), key="t", modifiers=_SHIFT_COMMAND)
        self._translation_picker = self._popup(editor, b"onTranslateLanguage:", (590, 39, 102, 28),
                                               self.labels["translate_language"], resize=AppKit.NSViewMinXMargin)
        self._translation_picker.addItemsWithTitles_([entry[2 if self._language == "zh" else 1] for entry in TRANSLATION_LANGUAGES])
        self._copy_button.setToolTip_(self.labels["copy_tip"])
        self._insert_button.setToolTip_(self.labels["insert_tip"])
        self._polish_button.setToolTip_(self.labels["polish_tip"])
        self._translate_button.setToolTip_(self.labels["translate_tip"])
        self._target_label = self._label(editor, "", (0, 7, 692, 22), size=12,
                                         color=AppKit.NSColor.secondaryLabelColor(), resize=AppKit.NSViewWidthSizable)

        recent_panel = AppKit.NSView.alloc().initWithFrame_(NSMakeRect(708, 0, 252, 404))
        recent_panel.setAutoresizingMask_(AppKit.NSViewMinXMargin | AppKit.NSViewHeightSizable)
        body.addSubview_(recent_panel)
        self._label(recent_panel, self.labels["recent"], (0, 382, 252, 22), bold=True, resize=_TOP_RESIZE)
        recent_scroll = AppKit.NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 74, 252, 300))
        recent_scroll.setBorderType_(AppKit.NSBezelBorder)
        recent_scroll.setHasVerticalScroller_(True)
        recent_scroll.setHasHorizontalScroller_(False)
        recent_scroll.setAutoresizingMask_(_FILL_RESIZE)
        recent_panel.addSubview_(recent_scroll)
        self._recent_table = AppKit.NSTableView.alloc().initWithFrame_(recent_scroll.bounds())
        self._recent_table.setHeaderView_(None)
        self._recent_table.setRowHeight_(64)
        self._recent_table.setUsesAlternatingRowBackgroundColors_(True)
        self._recent_table.setAllowsMultipleSelection_(False)
        self._recent_table.setAllowsEmptySelection_(True)
        self._recent_table.setColumnAutoresizingStyle_(AppKit.NSTableViewLastColumnOnlyAutoresizingStyle)
        self._recent_table.setAccessibilityLabel_(self.labels["recent_accessibility"])
        column = AppKit.NSTableColumn.alloc().initWithIdentifier_("record")
        column.setWidth_(235)
        column.setEditable_(False)
        column.dataCell().setFont_(AppKit.NSFont.systemFontOfSize_(12))
        column.dataCell().setWraps_(True)
        column.dataCell().setUsesSingleLineMode_(False)
        column.dataCell().setLineBreakMode_(AppKit.NSLineBreakByTruncatingTail)
        self._recent_table.addTableColumn_(column)
        self._recent_table.setDelegate_(self._delegate)
        self._recent_table.setDataSource_(self._delegate)
        recent_scroll.setDocumentView_(self._recent_table)
        self._recent_hint = self._label(recent_panel, "", (0, 45, 252, 20), size=11,
                                        color=AppKit.NSColor.secondaryLabelColor())
        self._history_button = self._button(recent_panel, self.labels["history"], b"onHistory:", (0, 4, 122, 34), key="y")
        self._dictionary_button = self._button(recent_panel, self.labels["dictionary"], b"onDictionary:", (130, 4, 122, 34), key="d", modifiers=_SHIFT_COMMAND)
        self._label(content, self.labels["shortcuts"], (20, 16, 824, 22), size=11,
                    color=AppKit.NSColor.secondaryLabelColor(), resize=AppKit.NSViewWidthSizable)
        self._help_button = self._button(content, self.labels["help"], b"onHelp:", (860, 11, 120, 32), resize=AppKit.NSViewMinXMargin)
        self.window.setInitialFirstResponder_(self._record_button)
        self._undo_manager = self._final_view.undoManager()
        for notification in (NSUndoManagerDidUndoChangeNotification, NSUndoManagerDidRedoChangeNotification):
            NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(self._delegate, b"onUndoRedo:", notification, self._undo_manager)

    def show(self):
        if self._disposed:
            raise RuntimeError("A disposed main window controller cannot be shown again")
        if self.window is None:
            self._build_window()
            self.update_state(self._snapshot)
        self.window.makeKeyAndOrderFront_(None)
        AppKit.NSApp.activateIgnoringOtherApps_(True)

    def close(self):
        self.flush_edits()
        if self.window is not None:
            self.window.close()

    def dispose(self):
        if self._disposed:
            return
        self.flush_edits()
        if self._undo_manager is not None:
            center = NSNotificationCenter.defaultCenter()
            for notification in (NSUndoManagerDidUndoChangeNotification, NSUndoManagerDidRedoChangeNotification):
                center.removeObserver_name_object_(self._delegate, notification, self._undo_manager)
            self._undo_manager = None
        if self.window is not None:
            self._final_view.setDelegate_(None)
            self._recent_table.setDelegate_(None)
            self._recent_table.setDataSource_(None)
            self.window.setDelegate_(None)
            self.window.close()
        if self._delegate is not None:
            self._delegate._controller = None
        self._on_edit = None
        self._disposed = True

    def get_final_text(self) -> str:
        return str(self._final_view.string()) if self.window is not None else str(self._snapshot.get("final") or "")

    def _schedule_edit(self):
        if self._suppress_edit or self._on_edit is None:
            return
        self._pending_edit = self.get_final_text()
        if self._edit_timer is not None:
            self._edit_timer.invalidate()
        self._edit_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.4, self._delegate, b"onEditTimer:", None, False)

    def flush_edits(self):
        if self._edit_timer is not None:
            self._edit_timer.invalidate()
            self._edit_timer = None
        if self._pending_edit is not None:
            text = self._pending_edit
            self._pending_edit = None
            self._on_edit(text)

    def _set_final_text(self, text):
        self._suppress_edit = True
        try:
            if self._final_view.string() != text:
                self._final_view.setString_(text)
                undo = self._final_view.undoManager()
                if undo is not None:
                    undo.removeAllActions()
        finally:
            self._suppress_edit = False
        self._final_placeholder.setHidden_(bool(text))

    def _on_record(self):
        self.flush_edits()
        self._selected_recent_id = None
        self._suppress_selection = True
        self._recent_table.deselectAll_(None)
        self._suppress_selection = False
        self._callbacks["record"]()

    def _render_readiness(self, items):
        self._readiness_actions = {}
        mapped = {}
        aliases = {"mic": "microphone", "speech": "asr", "ollama": "llm", "ollama_model": "llm",
                   "insertion": "accessibility", "input_monitoring": "hotkey"}
        for item in items:
            key = str(item.get("key") or item.get("id") or "")
            mapped[aliases.get(key, key)] = item
        self._llm_ready = False
        colors = {"ready": AppKit.NSColor.systemGreenColor(), "missing": AppKit.NSColor.systemOrangeColor(),
                  "error": AppKit.NSColor.systemRedColor(), "working": AppKit.NSColor.secondaryLabelColor()}
        for index, key in enumerate(("microphone", "asr", "llm", "accessibility", "hotkey")):
            item = mapped.get(key, {})
            status = str(item.get("status") or ("ready" if item.get("ready") is True else "unknown"))
            status = {"ok": "ready", "available": "ready", "checking": "working", "loading": "working", "fail": "error", "warn": "missing"}.get(status, status)
            card = self._readiness_cards[key]
            title = str(item.get("label") or item.get("title") or self.labels["hotkey_ready" if key == "hotkey" else key])
            status_label = str(item.get("status_label") or self.labels.get(status, self.labels["unknown"]))
            if "title" in card:
                card["title"].setStringValue_(title)
            else:
                status_label = f"{title}：{status_label}" if self.labels["start"] == LABELS["zh"]["start"] else f"{title}: {status_label}"
            card["status"].setStringValue_(status_label)
            card["status"].setAccessibilityLabel_(f"{title} {status_label}")
            card["status"].setTextColor_(colors.get(status, AppKit.NSColor.secondaryLabelColor()))
            detail = str(item.get("detail") or "")
            if "detail" in card:
                card["detail"].setStringValue_(detail)
                card["detail"].setToolTip_(detail)
            card["status"].setToolTip_(detail)
            action = item.get("action")
            card["action"].setHidden_(not bool(action))
            card["action"].setEnabled_(bool(action) and status != "working")
            card["action"].setTitle_(str(item.get("action_label") or self.labels["fix"]))
            card["action"].setAccessibilityLabel_(f"{title} {card['action'].title()}")
            card["action"].setTag_(index)
            self._readiness_actions[index] = action
            if key == "llm":
                self._llm_ready = status == "ready"

    def _refresh_actions(self):
        phase = self._snapshot.get("phase", "idle")
        recording = phase == "recording"
        busy = bool(self._snapshot.get("busy")) or phase in _BUSY_PHASES
        text = bool(self.get_final_text().strip())
        target = str(self._snapshot.get("target_name") or "")
        self._record_button.setEnabled_(recording or (bool(self._snapshot.get("ready")) and not busy))
        self._record_button.setTitle_(self.labels["stop" if recording else "start"])
        self._record_button.setAccessibilityLabel_(self.labels["stop" if recording else "start"])
        self._cancel_button.setEnabled_((busy or recording) and phase != "delivering")
        self._copy_button.setEnabled_(text and not busy and not recording)
        self._insert_button.setEnabled_(text and bool(target) and target != "SpeakType" and not busy and not recording)
        self._insert_button.setTitle_(self.labels["insert"].format(target=target) if target else self.labels["insert_empty"])
        self._insert_button.setAccessibilityLabel_(self._insert_button.title())
        self._polish_button.setEnabled_(text and self._llm_ready and not busy and not recording)
        self._translate_button.setEnabled_(text and self._llm_ready and not busy and not recording)
        self._final_view.setEditable_(not busy and not recording)
        self._recent_table.setEnabled_(not busy and not recording)
        self._target_picker.setEnabled_(not busy and not recording and self._on_target is not None)
        self._translation_picker.setEnabled_(not busy and not recording and self._on_translate_language is not None)
        self._polish_button.setToolTip_(self.labels["polish_tip"] if self._llm_ready else self.labels["llm_missing"])
        self._translate_button.setToolTip_(self.labels["translate_tip"] if self._llm_ready else self.labels["llm_missing"])

    def _select_recent(self):
        if self._suppress_selection or self._snapshot.get("phase") in _BUSY_PHASES | {"recording"} or self._snapshot.get("busy"):
            return
        index = self._recent_table.selectedRow()
        if not 0 <= index < len(self._recent):
            return
        entry = self._recent[index]
        self._selected_recent_id = entry.get("id")
        self.flush_edits()
        raw = str(entry.get("raw") or "")
        final = str(entry.get("polished") or raw)
        self._raw_view.setString_(raw)
        self._set_final_text(final)
        self._raw_heading.setStringValue_(self.labels["raw"])
        self._raw_placeholder.setHidden_(bool(raw))
        self._final_placeholder.setHidden_(bool(final))
        self._refresh_actions()
        if self._on_recent is not None and self._selected_recent_id:
            self._on_recent(self._selected_recent_id)

    def update_state(self, snapshot: dict):
        if not isinstance(snapshot, dict):
            raise TypeError("Main window state must be a dictionary")
        phase = snapshot.get("phase", "idle")
        if phase not in PHASES:
            raise ValueError(f"Unsupported main window phase: {phase}")
        self._snapshot = dict(snapshot)
        if self.window is None:
            return
        heading = self.labels["setup_needed"] if phase == "idle" and not snapshot.get("ready") else self.labels[phase]
        self._phase_label.setStringValue_(heading)
        self._phase_label.setAccessibilityLabel_(heading)
        self._phase_label.setTextColor_(AppKit.NSColor.systemRedColor() if phase == "error" else AppKit.NSColor.labelColor())
        status = str(snapshot.get("status") or "")
        self._status_label.setStringValue_(status)
        self._status_label.setToolTip_(status)
        if phase in _BUSY_PHASES:
            self._spinner.startAnimation_(None)
        else:
            self._spinner.stopAnimation_(None)
        raw, final, partial = (str(snapshot.get(key) or "") for key in ("raw", "final", "partial"))
        if raw != self._last_raw or partial != self._last_partial or phase != self._last_phase:
            displayed = partial if phase == "recording" and partial else (raw or partial)
            self._raw_view.setString_(displayed)
            self._raw_placeholder.setHidden_(bool(displayed))
            self._raw_heading.setStringValue_(self.labels["partial"] if phase == "recording" and partial else self.labels["raw"])
        if final != self._last_final:
            self._set_final_text(final)
        self._last_raw, self._last_final, self._last_partial = raw, final, partial
        self._last_phase = phase
        elapsed = float(snapshot.get("elapsed") or 0)
        level = float(snapshot.get("level") or 0)
        if not math.isfinite(elapsed) or not math.isfinite(level):
            raise ValueError("Recording time and level must be finite")
        seconds = max(0, int(elapsed))
        self._elapsed_label.setStringValue_(self.labels["duration"].format(time=f"{seconds // 60:02d}:{seconds % 60:02d}"))
        self._level.setDoubleValue_(max(0, min(level, 1)) * 100)
        hotkey = str(snapshot.get("hotkey") or "")
        self._hotkey_label.setStringValue_(self.labels["hotkey"].format(hotkey=hotkey) if hotkey else self.labels["hotkey_empty"])
        target = str(snapshot.get("target_name") or "")
        target_text = self.labels["target"].format(target=target) if target else self.labels["target_empty"]
        self._target_label.setStringValue_(target_text)
        self._target_label.setToolTip_(target_text)
        targets = snapshot.get("target_apps") or []
        if any(not isinstance(item, dict) or not isinstance(item.get("name"), str) for item in targets):
            raise ValueError("Target applications must contain names")
        self._target_apps = [dict(item) for item in targets if item["name"] != "SpeakType"]
        names = [item["name"] for item in self._target_apps]
        titles = [self.labels["choose_target"]] + [
            f"{item['name']} ({item['pid']})" if names.count(item["name"]) > 1 else item["name"] for item in self._target_apps]
        if list(self._target_picker.itemTitles()) != titles:
            self._target_picker.removeAllItems()
            self._target_picker.addItemsWithTitles_(titles)
        target_pid = snapshot.get("target_pid", self._selected_target_pid)
        selected = next((index + 1 for index, item in enumerate(self._target_apps)
                         if item["name"] == target and (target_pid is None or item.get("pid") == target_pid)), 0)
        self._target_picker.selectItemAtIndex_(selected)
        language = str(snapshot.get("translate_target") or "en")
        language_index = next((index for index, item in enumerate(TRANSLATION_LANGUAGES) if item[0] == language), None)
        if language_index is None:
            raise ValueError(f"Unsupported translation language: {language}")
        self._translation_picker.selectItemAtIndex_(language_index)
        self._render_readiness(snapshot.get("readiness") or [])
        entries = snapshot.get("recent") or []
        if any(not isinstance(entry, dict) for entry in entries):
            raise ValueError("Recent dictations must be dictionaries")
        recent = sorted((dict(entry) for entry in entries), key=lambda item: str(item.get("timestamp") or ""), reverse=True)
        if recent != self._recent:
            self._suppress_selection = True
            self._recent = recent
            self._recent_table.reloadData()
            index = next((i for i, entry in enumerate(recent) if entry.get("id") == self._selected_recent_id), None)
            if index is None:
                self._recent_table.deselectAll_(None)
            else:
                self._recent_table.selectRowIndexes_byExtendingSelection_(NSIndexSet.indexSetWithIndex_(index), False)
            self._suppress_selection = False
        self._recent_hint.setStringValue_(self.labels["recent_count"].format(count=len(recent)) if recent else self.labels["recent_empty"])
        self._refresh_actions()
