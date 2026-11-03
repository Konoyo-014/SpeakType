from __future__ import annotations

import math

import AppKit
import objc
from Foundation import (
    NSIndexSet, NSNotificationCenter, NSObject, NSMakeRect, NSMakeSize, NSTimer,
    NSUndoManagerDidRedoChangeNotification, NSUndoManagerDidUndoChangeNotification,
)

from .design import apply_window, color, material_view, style_button, symbol
from .design import color as _theme_color
from .hotwords import validate_manual_hotword
from .status_overlay import _StateIndicatorView


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
        "workspace": "听写", "workspace_detail": "说出你的想法，文字会留在这里。",
        "nav_dictation": "听写", "hotwords": "热词词典", "local": "语音与词库保存在本机",
        "connections": "听写准备", "learn": "记住这个词", "learn_tip": "选中最终文本中的词语，保存正确写法和常见误识别。",
        "learn_title": "记住这个词", "learn_detail": "正确写法用于之后的识别。填写常见误识别后，SpeakType 会在听写结果中修正这个写法。",
        "preferred": "正确写法", "original": "常见误识别（可选）", "save": "保存词语",
        "learn_saved": "已记住「{term}」", "learn_invalid": "请输入 2–80 个字符的词语。",
        "learn_error": "词语未保存：{error}",
        "hotwords_count": "个人词库 · {count} 个已启用", "hotwords_empty": "添加人名、项目名和专业术语",
        "hotwords_changes": "本次已修正：{terms}", "hotwords_selected": "识别提示：{terms}",
        "characters": "{count} 个字符", "manage": "管理词库", "output": "文本输出",
        "view": "查看",
        "ready_summary": "听写已就绪", "needs_summary": "需要准备", "setup_entry": "权限与模型",
        "microphone_needs_check": "麦克风需要检查",
        "empty_title": "把想法说出来。", "empty_detail": "点击开始听写，或在其他应用中使用全局快捷键。",
        "listening_empty": "正在聆听…", "history_nav": "历史记录",
        "more": "更多", "navigation": "听写导航",
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
        "recent_empty": "No dictations yet", "recent_count": "Recent: {count} · Select to read",
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
        "workspace": "Dictation", "workspace_detail": "Speak your mind. Your words appear here.",
        "nav_dictation": "Dictation", "hotwords": "Vocabulary", "local": "Voice and vocabulary stay on this Mac",
        "connections": "Dictation readiness", "learn": "Remember this word", "learn_tip": "Select a word in the final text to save its spelling and a common misrecognition.",
        "learn_title": "Remember this word", "learn_detail": "Save the preferred spelling for future dictation. Add a common misrecognition to correct that spelling in dictation results.",
        "preferred": "Preferred spelling", "original": "Common misrecognition (optional)", "save": "Save word",
        "learn_saved": "Remembered “{term}”", "learn_invalid": "Enter a word containing 2–80 characters.",
        "learn_error": "Word was not saved: {error}",
        "hotwords_count": "Personal vocabulary · {count} enabled", "hotwords_empty": "Add names, projects and specialist terms",
        "hotwords_changes": "Corrected this time: {terms}", "hotwords_selected": "Recognition hints: {terms}",
        "characters": "{count} characters", "manage": "Manage vocabulary", "output": "Text output",
        "view": "View",
        "ready_summary": "Ready to dictate", "needs_summary": "Setup needed", "setup_entry": "Permissions & models",
        "microphone_needs_check": "Check microphone",
        "empty_title": "Make room for a thought.", "empty_detail": "Start dictation, or use your global shortcut in another app.",
        "listening_empty": "Listening…", "history_nav": "History",
        "more": "More", "navigation": "Dictation navigation",
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

    def toolbarAllowedItemIdentifiers_(self, toolbar):
        return ["navigation", AppKit.NSToolbarFlexibleSpaceItemIdentifier, "settings"]

    def toolbarDefaultItemIdentifiers_(self, toolbar):
        return self.toolbarAllowedItemIdentifiers_(toolbar)

    def toolbar_itemForItemIdentifier_willBeInsertedIntoToolbar_(self, toolbar, identifier, inserted):
        return self._controller._toolbar_items.get(str(identifier))

    def onNavigation_(self, sender):
        index = sender.selectedSegment()
        sender.setSelectedSegment_(0)
        if index == 1:
            self.onHotwords_(sender)
        elif index == 2:
            self._controller._show_recent()
        else:
            self.onFocusDictation_(sender)

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
        self._controller._recent_popover.close()
        self._controller._callbacks["history"]()

    def onSettings_(self, sender):
        self._controller.flush_edits()
        self._controller._callbacks["settings"]()

    def onDictionary_(self, sender):
        self._controller.flush_edits()
        self._controller._callbacks["dictionary"]()

    def onHotwords_(self, sender):
        self._controller.flush_edits()
        self._controller._on_hotwords()

    def onLearnHotword_(self, sender):
        self._controller._learn_hotword()

    def onFocusDictation_(self, sender):
        self._controller.window.makeFirstResponder_(self._controller._final_view)

    def onToggleRaw_(self, sender):
        self._controller._raw_expanded = bool(sender.state())
        self._controller._layout_workspace()

    def onSetup_(self, sender):
        self._controller.flush_edits()
        self._controller._callbacks["setup"](None)

    def onHelp_(self, sender):
        self._controller.flush_edits()
        self._controller._callbacks["setup"]("help")

    def onEditTimer_(self, timer):
        self._controller.flush_edits()

    def windowShouldClose_(self, sender):
        self._controller.flush_edits()
        self._controller._indicator.stop_all_animations()
        return True

    def windowDidResize_(self, notification):
        self._controller._layout_workspace()

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

    def textViewDidChangeSelection_(self, notification):
        if notification.object() == self._controller._final_view:
            self._controller._refresh_actions()

    def onUndoRedo_(self, notification):
        self._controller._refresh_actions()
        self._controller._final_placeholder.setHidden_(bool(self._controller.get_final_text()))
        self._controller._schedule_edit()


class _MainWindow(AppKit.NSWindow):
    def performKeyEquivalent_(self, event):
        controller = getattr(self, "_controller", None)
        modifiers = event.modifierFlags() & (_COMMAND | AppKit.NSEventModifierFlagShift | AppKit.NSEventModifierFlagOption | AppKit.NSEventModifierFlagControl)
        key = str(event.charactersIgnoringModifiers() or "").lower()
        if controller is not None and modifiers == _COMMAND and key == "y":
            controller.flush_edits()
            controller._callbacks["history"]()
            return True
        if controller is not None and modifiers == _SHIFT_COMMAND and key == "d":
            controller.flush_edits()
            controller._callbacks["dictionary"]()
            return True
        return objc.super(_MainWindow, self).performKeyEquivalent_(event)


class MainWindowController:
    WIDTH = 900
    HEIGHT = 620
    MIN_WIDTH = 780
    MIN_HEIGHT = 560

    def __init__(self, on_record, on_cancel, on_copy, on_insert, on_polish, on_translate,
                 on_history, on_settings, on_setup, on_dictionary, *, on_recent=None,
                 on_target=None, on_translate_language=None, on_edit=None, on_hotwords=None,
                 on_learn_hotword=None, language="zh", labels=None):
        self._callbacks = {
            "record": on_record, "cancel": on_cancel, "copy": on_copy, "insert": on_insert,
            "polish": on_polish, "translate": on_translate, "history": on_history,
            "settings": on_settings, "setup": on_setup, "dictionary": on_dictionary,
        }
        for name, callback in self._callbacks.items():
            if not callable(callback):
                raise TypeError(f"Main window callback must be callable: {name}")
        for name, callback in (("on_recent", on_recent), ("on_target", on_target), ("on_translate_language", on_translate_language), ("on_edit", on_edit), ("on_hotwords", on_hotwords), ("on_learn_hotword", on_learn_hotword)):
            if callback is not None and not callable(callback):
                raise TypeError(f"{name} must be callable")
        self._on_recent = on_recent
        self._on_target = on_target
        self._on_translate_language = on_translate_language
        self._on_edit = on_edit
        self._on_hotwords = on_hotwords or on_dictionary
        self._on_learn_hotword = on_learn_hotword
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
        self._readiness_details = []
        self._raw_expanded = False
        self._llm_ready = False
        self._target_apps = []
        self._selected_target_pid = None
        self._pending_edit = None
        self._edit_timer = None
        self._suppress_edit = False
        self._undo_manager = None
        self._disposed = False
        self._toolbar_items = {}

    def _label(self, parent, text, frame, *, size=13, bold=False, color=None, resize=0):
        label = AppKit.NSTextField.labelWithString_(text)
        label.setFrame_(NSMakeRect(*frame))
        label.setFont_(AppKit.NSFont.systemFontOfSize_weight_(size, AppKit.NSFontWeightSemibold if bold else AppKit.NSFontWeightRegular))
        label.setTextColor_(_theme_color("text"))
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
        style_button(button)
        if key is not None:
            button.setKeyEquivalent_(key)
            button.setKeyEquivalentModifierMask_(modifiers)
        parent.addSubview_(button)
        return button

    def _text_view(self, parent, frame, *, editable, placeholder):
        scroll = AppKit.NSScrollView.alloc().initWithFrame_(NSMakeRect(*frame))
        scroll.setBorderType_(AppKit.NSNoBorder)
        scroll.setDrawsBackground_(False)
        scroll.setAutohidesScrollers_(True)
        scroll.setHasVerticalScroller_(True)
        scroll.setHasHorizontalScroller_(False)
        scroll.setAutoresizingMask_(_FILL_RESIZE if editable else _TOP_RESIZE)
        parent.addSubview_(scroll)
        view = AppKit.NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, frame[2] - 18, frame[3]))
        view.setEditable_(editable)
        view.setSelectable_(True)
        view.setRichText_(False)
        view.setAllowsUndo_(editable)
        view.setFont_(AppKit.NSFont.systemFontOfSize_(18 if editable else 13))
        paragraph = AppKit.NSMutableParagraphStyle.alloc().init()
        paragraph.setLineSpacing_(5 if editable else 4)
        view.setDefaultParagraphStyle_(paragraph)
        view.setTextColor_(color("text" if editable else "muted"))
        view.setDrawsBackground_(False)
        view.setTextContainerInset_(NSMakeSize(4, 8))
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
        popup.setBordered_(False)
        popup.setFont_(AppKit.NSFont.systemFontOfSize_(13))
        popup.setAction_(action)
        popup.setAutoresizingMask_(resize)
        popup.setAccessibilityLabel_(label)
        popup.setToolTip_(label)
        parent.addSubview_(popup)
        return popup

    def _separator(self, parent, frame, resize=AppKit.NSViewWidthSizable):
        line = AppKit.NSBox.alloc().initWithFrame_(NSMakeRect(*frame))
        line.setBoxType_(AppKit.NSBoxSeparator)
        line.setAutoresizingMask_(resize)
        parent.addSubview_(line)
        return line

    def _build_toolbar(self):
        toolbar = AppKit.NSToolbar.alloc().initWithIdentifier_("SpeakTypeStudio")
        toolbar.setDelegate_(self._delegate)
        toolbar.setAllowsUserCustomization_(False)
        toolbar.setDisplayMode_(AppKit.NSToolbarDisplayModeIconOnly)
        toolbar.setSizeMode_(AppKit.NSToolbarSizeModeSmall)
        self._navigation_control = AppKit.NSSegmentedControl.alloc().initWithFrame_(NSMakeRect(0, 0, 286, 28))
        self._navigation_control.setSegmentCount_(3)
        self._navigation_control.setSegmentStyle_(AppKit.NSSegmentStyleTexturedRounded)
        self._navigation_control.setTrackingMode_(AppKit.NSSegmentSwitchTrackingSelectOne)
        for index, (key, image_name) in enumerate((("nav_dictation", "waveform"), ("hotwords", "character.book.closed"), ("history_nav", "clock.arrow.circlepath"))):
            self._navigation_control.setLabel_forSegment_(self.labels[key], index)
            self._navigation_control.setImage_forSegment_(symbol(image_name, self.labels[key], 13), index)
            self._navigation_control.setWidth_forSegment_((90, 106, 90)[index], index)
        self._navigation_control.setSelectedSegment_(0)
        self._navigation_control.setTarget_(self._delegate)
        self._navigation_control.setAction_(b"onNavigation:")
        self._navigation_control.setAccessibilityLabel_(self.labels["navigation"])
        navigation = AppKit.NSToolbarItem.alloc().initWithItemIdentifier_("navigation")
        navigation.setView_(self._navigation_control)
        navigation.setMinSize_(NSMakeSize(286, 28))
        navigation.setMaxSize_(NSMakeSize(286, 28))
        self._toolbar_items["navigation"] = navigation
        host = AppKit.NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 70, 28))
        self._settings_button = self._button(host, "", b"onSettings:", (0, 0, 30, 28), key=",")
        self._settings_button.setImage_(symbol("gearshape", self.labels["settings"], 15))
        self._settings_button.setImagePosition_(AppKit.NSImageOnly)
        self._settings_button.setAccessibilityLabel_(self.labels["settings"])
        self._settings_button.setToolTip_(self.labels["settings"])
        self._more_button = AppKit.NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(38, 0, 30, 28), True)
        self._more_button.setBordered_(False)
        self._more_button.setAccessibilityLabel_(self.labels["more"])
        self._more_button.addItemWithTitle_(self.labels["more"])
        self._more_button.itemAtIndex_(0).setImage_(symbol("ellipsis.circle", self.labels["more"], 16))
        self._more_button.setImagePosition_(AppKit.NSImageOnly)
        self._dictionary_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(self.labels["dictionary"], b"onDictionary:", "d")
        self._dictionary_item.setKeyEquivalentModifierMask_(_SHIFT_COMMAND)
        self._dictionary_item.setTarget_(self._delegate)
        self._more_button.menu().addItem_(self._dictionary_item)
        help_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(self.labels["help"], b"onHelp:", "")
        help_item.setTarget_(self._delegate)
        self._more_button.menu().addItem_(help_item)
        host.addSubview_(self._more_button)
        settings = AppKit.NSToolbarItem.alloc().initWithItemIdentifier_("settings")
        settings.setView_(host)
        settings.setMinSize_(NSMakeSize(70, 28))
        settings.setMaxSize_(NSMakeSize(70, 28))
        self._toolbar_items["settings"] = settings
        self.window.setToolbar_(toolbar)

    def _build_recent_popover(self):
        self._recent_popover = AppKit.NSPopover.alloc().init()
        self._recent_popover.setBehavior_(AppKit.NSPopoverBehaviorTransient)
        view = AppKit.NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 380, 300))
        self._label(view, self.labels["recent"], (16, 268, 348, 20), size=13, bold=True)
        scroll = AppKit.NSScrollView.alloc().initWithFrame_(NSMakeRect(12, 54, 356, 206))
        scroll.setBorderType_(AppKit.NSNoBorder)
        scroll.setHasVerticalScroller_(True)
        scroll.setAutohidesScrollers_(True)
        scroll.setDrawsBackground_(False)
        view.addSubview_(scroll)
        self._recent_table = AppKit.NSTableView.alloc().initWithFrame_(scroll.bounds())
        self._recent_table.setHeaderView_(None)
        self._recent_table.setRowHeight_(64)
        self._recent_table.setBackgroundColor_(AppKit.NSColor.clearColor())
        self._recent_table.setAllowsMultipleSelection_(False)
        self._recent_table.setAllowsEmptySelection_(True)
        self._recent_table.setColumnAutoresizingStyle_(AppKit.NSTableViewLastColumnOnlyAutoresizingStyle)
        self._recent_table.setAccessibilityLabel_(self.labels["recent_accessibility"])
        column = AppKit.NSTableColumn.alloc().initWithIdentifier_("record")
        column.setWidth_(340)
        column.setEditable_(False)
        column.dataCell().setFont_(AppKit.NSFont.systemFontOfSize_(12))
        column.dataCell().setTextColor_(AppKit.NSColor.labelColor())
        column.dataCell().setWraps_(True)
        column.dataCell().setUsesSingleLineMode_(False)
        column.dataCell().setLineBreakMode_(AppKit.NSLineBreakByTruncatingTail)
        self._recent_table.addTableColumn_(column)
        self._recent_table.setDelegate_(self._delegate)
        self._recent_table.setDataSource_(self._delegate)
        scroll.setDocumentView_(self._recent_table)
        self._recent_hint = self._label(view, "", (16, 18, 220, 18), size=10, color=color("muted"))
        self._history_button = self._button(view, self.labels["history"], b"onHistory:", (248, 12, 116, 28), key="y")
        controller = AppKit.NSViewController.alloc().init()
        controller.setView_(view)
        self._recent_popover.setContentViewController_(controller)
        self._recent_popover.setContentSize_(NSMakeSize(380, 300))

    def _show_recent(self):
        self.flush_edits()
        self._recent_popover.showRelativeToRect_ofView_preferredEdge_(self._navigation_control.bounds(), self._navigation_control, AppKit.NSMinYEdge)

    def _build_window(self):
        AppKit.NSApplication.sharedApplication()
        self._delegate = _MainWindowDelegate.alloc().initWithController_(self)
        style = AppKit.NSTitledWindowMask | AppKit.NSClosableWindowMask | AppKit.NSMiniaturizableWindowMask | AppKit.NSResizableWindowMask
        self.window = _MainWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, self.WIDTH, self.HEIGHT), style, AppKit.NSBackingStoreBuffered, False)
        self.window._controller = self
        self.window.setTitle_(self.labels["window"])
        self.window.setContentMinSize_(NSMakeSize(self.MIN_WIDTH, self.MIN_HEIGHT))
        self.window.setReleasedWhenClosed_(False)
        self.window.setTabbingMode_(AppKit.NSWindowTabbingModeDisallowed)
        self.window.setDelegate_(self._delegate)
        apply_window(self.window)
        self.window.center()
        content = material_view(NSMakeRect(0, 0, self.WIDTH, self.HEIGHT), material="sidebar")
        content.setAutoresizingMask_(_FILL_RESIZE)
        self.window.setContentView_(content)
        self.window.setToolbarStyle_(AppKit.NSWindowToolbarStyleUnifiedCompact)
        self._build_toolbar()
        self.window.setContentSize_(NSMakeSize(self.WIDTH, self.HEIGHT))
        self._build_recent_popover()
        header = AppKit.NSView.alloc().initWithFrame_(NSMakeRect(24, 542, 852, 58))
        header.setAutoresizingMask_(_TOP_RESIZE)
        content.addSubview_(header)
        self._indicator = _StateIndicatorView.alloc().initWithFrame_(NSMakeRect(0, 20, 22, 22))
        header.addSubview_(self._indicator)
        self._phase_label = self._label(header, "", (32, 29, 500, 21), size=14, bold=True,
                                         resize=AppKit.NSViewWidthSizable)
        self._status_label = self._label(header, "", (32, 8, 560, 18), size=11,
                                         color=color("muted"), resize=AppKit.NSViewWidthSizable)
        self._record_button = self._button(header, self.labels["start"], b"onRecord:", (676, 11, 176, 36), key="r",
                                           resize=AppKit.NSViewMinXMargin)
        style_button(self._record_button, primary=True)
        self._record_button.setFont_(AppKit.NSFont.systemFontOfSize_weight_(15, AppKit.NSFontWeightSemibold))
        self._record_button.setImage_(symbol("mic.fill", self.labels["start"]))
        self._record_button.setImagePosition_(AppKit.NSImageLeft)
        self._cancel_button = self._button(header, self.labels["cancel"], b"onCancel:", (604, 14, 64, 30), key="\x1b", modifiers=0,
                                           resize=AppKit.NSViewMinXMargin)
        self._elapsed_label = self._label(header, "", (220, 30, 190, 18), size=10, color=color("muted"))
        metadata = AppKit.NSView.alloc().initWithFrame_(NSMakeRect(24, 508, 852, 28))
        metadata.setAutoresizingMask_(_TOP_RESIZE)
        content.addSubview_(metadata)
        self._target_label = self._label(metadata, self.labels["target_picker"], (0, 7, 80, 18), size=11, color=color("muted"))
        self._target_picker = self._popup(metadata, b"onTarget:", (80, 1, 250, 28),
                                          self.labels["target_picker"], resize=AppKit.NSViewWidthSizable)
        self._target_picker.setAutoresizingMask_(0)
        self._hotkey_label = self._label(metadata, "", (480, 7, 372, 18), size=11,
                                         color=color("muted"), resize=AppKit.NSViewMinXMargin)
        self._hotkey_label.setAlignment_(AppKit.NSTextAlignmentRight)
        self._editor_material = material_view(NSMakeRect(20, 164, 860, 330), material="content", radius=14)
        self._editor_material.setAutoresizingMask_(_FILL_RESIZE)
        content.addSubview_(self._editor_material)
        self._final_view, self._final_placeholder, self._final_scroll = self._text_view(
            self._editor_material, (14, 12, 832, 284), editable=True, placeholder=self.labels["empty_title"])
        self._final_placeholder.setFont_(AppKit.NSFont.systemFontOfSize_(18))
        self._final_placeholder.setTextColor_(color("muted"))
        self._final_placeholder.removeFromSuperview()
        content.addSubview_(self._final_placeholder)
        self._empty_hint = self._label(content, self.labels["empty_detail"], (38, 400, 780, 22),
                                       size=12, color=color("muted"))
        self._live_view, self._live_placeholder, self._live_scroll = self._text_view(
            self._editor_material, (14, 12, 832, 284), editable=False, placeholder=self.labels["listening_empty"])
        self._live_view.setFont_(AppKit.NSFont.systemFontOfSize_(18))
        self._live_view.setTextColor_(color("text"))
        self._live_view.setAccessibilityLabel_(self.labels["partial"])
        paragraph = AppKit.NSMutableParagraphStyle.alloc().init()
        paragraph.setLineSpacing_(5)
        self._live_view.setDefaultParagraphStyle_(paragraph)
        self._live_placeholder.setFont_(AppKit.NSFont.systemFontOfSize_(18))
        self._live_placeholder.removeFromSuperview()
        content.addSubview_(self._live_placeholder)
        self._live_placeholder.setHidden_(True)
        self._live_scroll.setHidden_(True)
        self._editor_heading = self._label(self._editor_material, self.labels["final"], (16, 302, 400, 18), size=11,
                                            color=color("muted"), resize=_TOP_RESIZE)
        self._character_label = self._label(self._editor_material, "", (636, 302, 208, 18), size=11,
                                            color=color("muted"), resize=AppKit.NSViewMinXMargin | AppKit.NSViewMinYMargin)
        self._character_label.setAlignment_(AppKit.NSTextAlignmentRight)
        self._learn_button = self._button(content, self.labels["learn"], b"onLearnHotword:", (686, 132, 190, 28))
        self._learn_button.setImage_(symbol("text.badge.plus", self.labels["learn"]))
        self._learn_button.setImagePosition_(AppKit.NSImageLeft)
        self._learn_button.setToolTip_(self.labels["learn_tip"])
        self._hotword_summary = self._label(content, "", (24, 137, 640, 18), size=11, color=color("muted"),
                                            resize=AppKit.NSViewWidthSizable)
        self._raw_disclosure = self._button(content, "", b"onToggleRaw:", (20, 106, 18, 20))
        self._raw_disclosure.setButtonType_(AppKit.NSButtonTypeOnOff)
        self._raw_disclosure.setBezelStyle_(AppKit.NSBezelStyleDisclosure)
        self._raw_disclosure.setBordered_(True)
        self._raw_disclosure.setState_(0)
        self._raw_disclosure.setAccessibilityLabel_(self.labels["raw"])
        self._raw_heading = self._label(content, self.labels["raw"], (44, 108, 400, 18), size=11,
                                         bold=True, color=color("muted"), resize=AppKit.NSViewWidthSizable)
        self._raw_view, self._raw_placeholder, self._raw_scroll = self._text_view(
            content, (24, 132, 852, 80), editable=False, placeholder=self.labels["raw_empty"])
        self._raw_scroll.setAutoresizingMask_(AppKit.NSViewWidthSizable)
        self._raw_scroll.setHidden_(True)

        self._separator(content, (24, 88, 852, 1))
        footer = AppKit.NSView.alloc().initWithFrame_(NSMakeRect(24, 36, 852, 52))
        footer.setAutoresizingMask_(AppKit.NSViewWidthSizable)
        content.addSubview_(footer)
        self._polish_button = self._button(footer, self.labels["polish"], b"onPolish:", (0, 12, 118, 30), key="p", modifiers=_SHIFT_COMMAND)
        self._polish_button.setImage_(symbol("wand.and.stars", self.labels["polish"], 14))
        self._polish_button.setImagePosition_(AppKit.NSImageLeft)
        self._translate_button = self._button(footer, self.labels["translate"], b"onTranslate:", (124, 12, 92, 30), key="t", modifiers=_SHIFT_COMMAND)
        self._translate_button.setImage_(symbol("character.bubble", self.labels["translate"], 14))
        self._translate_button.setImagePosition_(AppKit.NSImageLeft)
        self._translation_picker = self._popup(footer, b"onTranslateLanguage:", (220, 13, 90, 28),
                                               self.labels["translate_language"])
        self._translation_picker.addItemsWithTitles_([entry[2 if self._language == "zh" else 1] for entry in TRANSLATION_LANGUAGES])
        self._polish_button.setToolTip_(self.labels["polish_tip"])
        self._translate_button.setToolTip_(self.labels["translate_tip"])
        self._copy_button = self._button(footer, self.labels["copy"], b"onCopy:", (530, 12, 100, 30),
                                         key="c", modifiers=_SHIFT_COMMAND, resize=AppKit.NSViewMinXMargin)
        self._copy_button.setImage_(symbol("doc.on.doc", self.labels["copy"], 14))
        self._copy_button.setImagePosition_(AppKit.NSImageLeft)
        self._insert_button = self._button(footer, self.labels["insert_empty"], b"onInsert:", (636, 12, 216, 30),
                                           key="\r", resize=AppKit.NSViewMinXMargin)
        self._insert_button.setImage_(symbol("arrow.turn.down.left", self.labels["insert_empty"], 14))
        self._insert_button.setImagePosition_(AppKit.NSImageLeft)
        self._copy_button.setToolTip_(self.labels["copy_tip"])
        self._insert_button.setToolTip_(self.labels["insert_tip"])
        self._readiness_summary = self._label(content, "", (24, 10, 500, 18), size=11, color=color("muted"))
        self._setup_button = self._button(content, self.labels["setup_entry"], b"onSetup:", (686, 5, 190, 28),
                                          resize=AppKit.NSViewMinXMargin)
        self._setup_button.setImage_(symbol("slider.horizontal.3", self.labels["setup_entry"], 13))
        self._setup_button.setImagePosition_(AppKit.NSImageLeft)
        self._layout_workspace()
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

    def _layout_workspace(self):
        if self.window is None or not hasattr(self, "_setup_button"):
            return
        size = self.window.contentView().bounds().size
        width = size.width - 40
        top = size.height - 126
        extra = 96 if self._raw_expanded else 0
        bottom = 164 + extra
        height = max(150, top - bottom)
        self._editor_material.setFrame_(NSMakeRect(20, bottom, width, height))
        frame = NSMakeRect(14, 12, width - 28, height - 50)
        self._final_scroll.setFrame_(frame)
        self._live_scroll.setFrame_(frame)
        for placeholder in (self._final_placeholder, self._live_placeholder):
            placeholder.setFrame_(NSMakeRect(38, top - 84, width - 44, 32))
        self._empty_hint.setFrame_(NSMakeRect(38, top - 110, width - 44, 22))
        self._learn_button.setFrame_(NSMakeRect(size.width - 214, 132 + extra, 190, 28))
        self._character_label.setFrame_(NSMakeRect(width - 224, height - 28, 208, 18))
        self._editor_heading.setFrame_(NSMakeRect(16, height - 28, width - 260, 18))
        self._hotword_summary.setFrame_(NSMakeRect(24, 137 + extra, width - 236, 18))
        self._raw_scroll.setFrame_(NSMakeRect(24, 132, size.width - 48, 80))
        self._raw_scroll.setHidden_(not self._raw_expanded)
        self._raw_placeholder.setFrame_(NSMakeRect(0, 46, width - 22, 22))
        self._raw_disclosure.setAccessibilityValue_(self._raw_expanded)

    def close(self):
        self.flush_edits()
        if self.window is not None:
            self._indicator.stop_all_animations()
            self._recent_popover.close()
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
            self._indicator.stop_all_animations()
            self._recent_popover.close()
            self._final_view.setDelegate_(None)
            self._recent_table.setDelegate_(None)
            self._recent_table.setDataSource_(None)
            self.window.setDelegate_(None)
            self.window._controller = None
            self.window.close()
        if self._delegate is not None:
            self._delegate._controller = None
        self._on_edit = None
        self._disposed = True

    def get_final_text(self) -> str:
        return str(self._final_view.string()) if self.window is not None else str(self._snapshot.get("final") or "")

    def _selected_final_text(self):
        selection = self._final_view.selectedRange()
        if selection.length == 0:
            return ""
        return str(self._final_view.textStorage().attributedSubstringFromRange_(selection).string()).strip()

    def _learn_hotword(self):
        if self._on_learn_hotword is None:
            return
        self.flush_edits()
        preferred = self._selected_final_text()
        alert = AppKit.NSAlert.alloc().init()
        alert.setMessageText_(self.labels["learn_title"])
        alert.setInformativeText_(self.labels["learn_detail"])
        alert.addButtonWithTitle_(self.labels["save"])
        alert.addButtonWithTitle_(self.labels["cancel"])
        form = AppKit.NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 360, 114))
        self._label(form, self.labels["preferred"], (0, 94, 360, 18), size=11, bold=True)
        preferred_field = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(0, 64, 360, 26))
        preferred_field.setStringValue_(preferred)
        form.addSubview_(preferred_field)
        self._label(form, self.labels["original"], (0, 38, 360, 18), size=11, bold=True)
        original_field = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(0, 8, 360, 26))
        original_field.setStringValue_(preferred)
        form.addSubview_(original_field)
        alert.setAccessoryView_(form)
        alert.window().setInitialFirstResponder_(preferred_field)
        while alert.runModal() == AppKit.NSAlertFirstButtonReturn:
            preferred = str(preferred_field.stringValue()).strip()
            original = str(original_field.stringValue()).strip()
            if self._save_hotword(original, preferred):
                return
            alert.setInformativeText_(str(self._status_label.stringValue()))

    def _save_hotword(self, original, preferred):
        try:
            validate_manual_hotword(preferred, [original] if original else [])
            self._on_learn_hotword(original, preferred)
        except ValueError as error:
            self._status_label.setStringValue_(self.labels["learn_error"].format(error=str(error)))
            self._status_label.setTextColor_(AppKit.NSColor.systemOrangeColor())
            return False
        self._status_label.setStringValue_(self.labels["learn_saved"].format(term=preferred))
        self._status_label.setTextColor_(color("accent"))
        return True

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
        self._recent_popover.close()
        self._selected_recent_id = None
        self._suppress_selection = True
        self._recent_table.deselectAll_(None)
        self._suppress_selection = False
        self._callbacks["record"]()

    def _render_readiness(self, items):
        mapped = {}
        aliases = {"mic": "microphone", "speech": "asr", "ollama": "llm", "ollama_model": "llm",
                   "insertion": "accessibility", "input_monitoring": "hotkey"}
        for item in items:
            key = str(item.get("key") or item.get("id") or "")
            mapped[aliases.get(key, key)] = item
        self._llm_ready = False
        self._readiness_details = []
        for key in ("microphone", "asr", "llm", "accessibility", "hotkey"):
            item = mapped.get(key, {})
            status = str(item.get("status") or ("ready" if item.get("ready") is True else "unknown"))
            status = {"ok": "ready", "available": "ready", "checking": "working", "loading": "working", "fail": "error", "warn": "missing"}.get(status, status)
            title = str(item.get("label") or item.get("title") or self.labels["hotkey_ready" if key == "hotkey" else key])
            status_label = str(item.get("status_label") or self.labels.get(status, self.labels["unknown"]))
            detail = str(item.get("detail") or "")
            self._readiness_details.append({"key": key, "title": title, "status": status,
                                             "status_label": status_label, "detail": detail})
            if key == "llm":
                self._llm_ready = status == "ready"
        tooltip = "\n".join(f"{item['title']} · {item['status_label']}\n{item['detail']}" for item in self._readiness_details)
        microphone_error = any(item["key"] == "microphone" and item["status"] == "error"
                               for item in self._readiness_details)
        summary = (self.labels["microphone_needs_check"] if microphone_error else
                   self.labels["ready_summary" if self._snapshot.get("ready") else "needs_summary"])
        self._readiness_summary.setStringValue_(summary)
        self._readiness_summary.setTextColor_(AppKit.NSColor.systemOrangeColor() if microphone_error else color("muted"))
        self._readiness_summary.setToolTip_(tooltip)
        self._readiness_summary.setAccessibilityLabel_(summary + "\n" + tooltip)
        self._setup_button.setToolTip_(tooltip)

    def _refresh_actions(self):
        phase = self._snapshot.get("phase", "idle")
        recording = phase == "recording"
        busy = bool(self._snapshot.get("busy")) or phase in _BUSY_PHASES
        text = bool(self.get_final_text().strip())
        target = str(self._snapshot.get("target_name") or "")
        self._record_button.setEnabled_(recording or (bool(self._snapshot.get("ready")) and not busy))
        self._record_button.setTitle_(self.labels["stop" if recording else "start"])
        self._record_button.setAccessibilityLabel_(self.labels["stop" if recording else "start"])
        style_button(self._record_button, primary=True)
        self._cancel_button.setEnabled_((busy or recording) and phase != "delivering")
        self._copy_button.setEnabled_(text and not busy and not recording)
        self._insert_button.setEnabled_(text and bool(target) and target != "SpeakType" and not busy and not recording)
        self._insert_button.setTitle_(self.labels["insert"].format(target=target) if target else self.labels["insert_empty"])
        self._insert_button.setAccessibilityLabel_(self._insert_button.title())
        style_button(self._insert_button)
        self._polish_button.setEnabled_(text and self._llm_ready and not busy and not recording)
        self._translate_button.setEnabled_(text and self._llm_ready and not busy and not recording)
        selection = self._selected_final_text()
        self._learn_button.setEnabled_(bool(self._on_learn_hotword) and 2 <= len(selection) <= 80 and not busy and not recording)
        self._character_label.setStringValue_(self.labels["characters"].format(count=len(self.get_final_text())) if text else "")
        self._learn_button.setHidden_(not text or recording)
        self._cancel_button.setHidden_(not busy and not recording)
        self._elapsed_label.setHidden_(not recording)
        self._final_scroll.setHidden_(recording)
        self._live_scroll.setHidden_(not recording)
        self._final_placeholder.setHidden_(text or recording)
        self._live_placeholder.setHidden_(not recording or bool(self._snapshot.get("partial")))
        self._empty_hint.setHidden_(text or recording)
        self._hotword_summary.setHidden_(recording)
        self._editor_heading.setStringValue_(self.labels["partial" if recording else "final"])
        for button in (self._copy_button, self._learn_button, self._polish_button, self._translate_button):
            style_button(button)
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
        self._recent_popover.close()

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
        self._phase_label.setTextColor_(AppKit.NSColor.systemRedColor() if phase == "error" else color("muted"))
        status = str(snapshot.get("status") or self.labels["workspace_detail"])
        self._status_label.setStringValue_(status)
        self._status_label.setTextColor_(color("muted"))
        self._status_label.setToolTip_(status)
        indicator_state = {"loading": "transcribing", "translating": "polishing", "delivering": "transcribing"}.get(phase, phase)
        self._indicator.set_state(indicator_state)
        raw, final, partial = (str(snapshot.get(key) or "") for key in ("raw", "final", "partial"))
        self._status_label.setHidden_(phase == "idle" and not final and not raw)
        self._live_view.setString_(partial)
        self._live_placeholder.setHidden_(bool(partial))
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
        self._indicator.update_level(max(0, min(level, 1)))
        count = snapshot.get("hotword_count", 0)
        terms = snapshot.get("hotword_terms") or []
        changes = snapshot.get("hotword_changes") or []
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("Hotword count must be a nonnegative integer")
        if not isinstance(terms, list) or any(not isinstance(term, str) for term in terms):
            raise ValueError("Hotword terms must be a list of strings")
        if not isinstance(changes, list) or any(not isinstance(change, dict) for change in changes):
            raise ValueError("Hotword changes must be a list of dictionaries")
        if changes:
            changed = [str(change.get("replacement") or change.get("term") or "") for change in changes]
            summary = self.labels["hotwords_changes"].format(terms=" · ".join(dict.fromkeys(value for value in changed if value)))
        elif terms:
            summary = self.labels["hotwords_selected"].format(terms=" · ".join(terms[:5]))
        elif count:
            summary = self.labels["hotwords_count"].format(count=count)
        else:
            summary = self.labels["hotwords_empty"]
        self._hotword_summary.setStringValue_(summary)
        details = [f"{change.get('original', '')} → {change.get('replacement', '')}" for change in changes]
        self._hotword_summary.setToolTip_("\n".join(details + terms) if details or terms else summary)
        hotkey = str(snapshot.get("hotkey") or "")
        self._hotkey_label.setStringValue_(self.labels["hotkey"].format(hotkey=hotkey) if hotkey else self.labels["hotkey_empty"])
        target = str(snapshot.get("target_name") or "")
        target_text = self.labels["target"].format(target=target) if target else self.labels["target_empty"]
        self._target_label.setStringValue_(self.labels["target_picker"])
        self._target_label.setAccessibilityLabel_(target_text)
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
