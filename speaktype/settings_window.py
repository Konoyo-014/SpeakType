"""Native macOS Settings window using PyObjC."""

import logging
from pathlib import Path
import AppKit
import objc
from Foundation import NSObject, NSMakeRect, NSMakePoint
from .i18n import t
from .runtime import get_launch_program_args


class _FlippedView(AppKit.NSView):
    """NSView subclass with top-down Y coordinates for natural layout flow."""

    def isFlipped(self):
        return True

logger = logging.getLogger("speaktype.settings")

def _hotkey_options():
    return [
        ("right_cmd", t("hotkey_right_cmd")),
        ("left_cmd", t("hotkey_left_cmd")),
        ("right_alt", t("hotkey_right_alt")),
        ("right_ctrl", t("hotkey_right_ctrl")),
        ("ctrl+shift+space", t("hotkey_ctrl_shift_space")),
        ("f5", t("hotkey_f5")),
        ("f6", t("hotkey_f6")),
    ]


def _dictation_mode_options():
    return [
        ("push_to_talk", t("mode_opt_push")),
        ("toggle", t("mode_opt_toggle")),
    ]


def _language_options():
    return [
        ("auto", t("lang_auto")),
        ("en", "English"),
        ("zh", "\u4e2d\u6587 (Chinese)"),
        ("ja", "\u65e5\u672c\u8a9e (Japanese)"),
        ("ko", "\ud55c\uad6d\uc5b4 (Korean)"),
        ("es", "Espa\u00f1ol (Spanish)"),
        ("fr", "Fran\u00e7ais (French)"),
        ("de", "Deutsch (German)"),
    ]


def _insert_method_options():
    return [
        ("paste", t("settings_insert_paste")),
        ("type", t("settings_insert_type")),
    ]


def _ui_language_options():
    return [
        ("zh", t("ui_lang_zh")),
        ("en", t("ui_lang_en")),
    ]


LLM_MODEL_OPTIONS = [
    ("huihui_ai/qwen3.5-abliterated:9b-Claude", "Qwen 3.5 9B Abliterated (Default)"),
    ("qwen3.5:4b", "Qwen 3.5 4B (Fast/Lightweight)"),
    ("qwen3.5:9b", "Qwen 3.5 9B (Standard)"),
    ("qwen3.5:14b", "Qwen 3.5 14B (Best Quality)"),
]

ASR_BACKEND_OPTIONS = [
    ("qwen", "Qwen3-ASR (mlx-audio)"),
    ("whisper", "Whisper (OpenAI / mlx-whisper)"),
]

ASR_MODEL_OPTIONS = [
    ("mlx-community/Qwen3-ASR-1.7B-8bit", "Qwen3-ASR 1.7B (Recommended)"),
    ("mlx-community/Qwen3-ASR-0.6B-4bit", "Qwen3-ASR 0.6B (Faster)"),
]

WHISPER_MODEL_OPTIONS = [
    ("tiny", "Whisper Tiny (fastest, least accurate)"),
    ("base", "Whisper Base (good balance)"),
    ("small", "Whisper Small (better accuracy)"),
    ("medium", "Whisper Medium (high accuracy)"),
    ("large", "Whisper Large (best accuracy, slow)"),
]

TRANSLATE_LANG_OPTIONS = [
    ("en", "English"), ("zh", "\u4e2d\u6587"), ("ja", "\u65e5\u672c\u8a9e"),
    ("ko", "\ud55c\uad6d\uc5b4"), ("es", "Espa\u00f1ol"), ("fr", "Fran\u00e7ais"), ("de", "Deutsch"),
]


class _ButtonDelegate(NSObject):
    """ObjC delegate to handle button clicks."""

    def initWithCallbacks_cancel_(self, save_cb, cancel_cb):
        self = objc.super(_ButtonDelegate, self).init()
        if self is not None:
            self._save_cb = save_cb
            self._cancel_cb = cancel_cb
        return self

    def onSave_(self, sender):
        if self._save_cb:
            self._save_cb()

    def onCancel_(self, sender):
        if self._cancel_cb:
            self._cancel_cb()


class SettingsWindowController:
    """Manages the Settings window."""

    def __init__(self, config: dict, on_save=None):
        self.config = dict(config)
        self.on_save = on_save
        self.window = None
        self._controls = {}
        self._delegate = None

    def show(self):
        if self.window and self.window.isVisible():
            self.window.makeKeyAndOrderFront_(None)
            AppKit.NSApp.activateIgnoringOtherApps_(True)
            return

        self._build_window()
        self.window.makeKeyAndOrderFront_(None)
        AppKit.NSApp.activateIgnoringOtherApps_(True)

    WINDOW_WIDTH = 520
    WINDOW_HEIGHT = 560
    BUTTON_BAR_HEIGHT = 56
    DOC_HEIGHT = 760

    def _build_window(self):
        frame = NSMakeRect(0, 0, self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        style = (
            AppKit.NSTitledWindowMask
            | AppKit.NSClosableWindowMask
            | AppKit.NSMiniaturizableWindowMask
        )
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, AppKit.NSBackingStoreBuffered, False
        )
        self.window.setTitle_(t("settings_title"))
        self.window.center()
        self.window.setLevel_(AppKit.NSFloatingWindowLevel)
        self.window.setTabbingMode_(AppKit.NSWindowTabbingModeDisallowed)

        content = self.window.contentView()

        # --- Scrollable content area (top of the window) ---
        scroll_frame = NSMakeRect(
            0,
            self.BUTTON_BAR_HEIGHT,
            self.WINDOW_WIDTH,
            self.WINDOW_HEIGHT - self.BUTTON_BAR_HEIGHT,
        )
        scroll_view = AppKit.NSScrollView.alloc().initWithFrame_(scroll_frame)
        scroll_view.setHasVerticalScroller_(True)
        scroll_view.setHasHorizontalScroller_(False)
        scroll_view.setBorderType_(AppKit.NSNoBorder)
        scroll_view.setDrawsBackground_(False)
        scroll_view.setAutohidesScrollers_(True)
        scroll_view.setAutoresizingMask_(
            AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable
        )
        content.addSubview_(scroll_view)

        # Flipped document view so coordinates grow downward.
        doc_view = _FlippedView.alloc().initWithFrame_(
            NSMakeRect(0, 0, self.WINDOW_WIDTH, self.DOC_HEIGHT)
        )
        scroll_view.setDocumentView_(doc_view)

        # Populate the document view top-down.
        y = 14

        # --- General Section ---
        y = self._add_section_header(doc_view, t("settings_section_general"), y)
        y = self._add_popup(doc_view, t("settings_hotkey"), "hotkey", _hotkey_options(), y)
        y = self._add_popup(doc_view, t("settings_dictation_mode"), "dictation_mode", _dictation_mode_options(), y)
        y = self._add_popup(doc_view, t("settings_language"), "language", _language_options(), y)
        y = self._add_popup(doc_view, t("settings_insert_method"), "insert_method", _insert_method_options(), y)

        from .devices import list_input_devices
        device_options = [("", t("device_default"))]
        for dev in list_input_devices():
            device_options.append((dev["name"], dev["name"]))
        y = self._add_popup(doc_view, t("settings_audio_device"), "audio_device", device_options, y)
        y = self._add_popup(doc_view, t("settings_ui_language"), "ui_language", _ui_language_options(), y)

        y += 6

        # --- AI Models Section ---
        # Intentionally omits the Whisper backend + Whisper model dropdowns —
        # SpeakType is Qwen3-ASR only from v2.1 onwards.
        y = self._add_section_header(doc_view, t("settings_section_ai"), y)
        y = self._add_popup(doc_view, t("settings_qwen_model"), "asr_model", ASR_MODEL_OPTIONS, y)
        y = self._add_popup(doc_view, t("settings_llm_model"), "llm_model", LLM_MODEL_OPTIONS, y)
        y = self._add_text_field(doc_view, t("settings_ollama_url"), "ollama_url", y)

        y += 6

        # --- Features Section ---
        y = self._add_section_header(doc_view, t("settings_section_features"), y)
        y = self._add_checkbox(doc_view, t("settings_cb_polish"), "polish_enabled", y)
        y = self._add_checkbox(doc_view, t("settings_cb_voice_cmd"), "voice_commands_enabled", y)
        y = self._add_checkbox(doc_view, t("settings_cb_tone"), "context_aware_tone", y)
        y = self._add_checkbox(doc_view, t("settings_cb_sound"), "sound_feedback", y)
        y = self._add_checkbox(doc_view, t("settings_cb_history"), "history_enabled", y)
        y = self._add_checkbox(doc_view, t("settings_cb_streaming"), "streaming_preview", y)
        y = self._add_checkbox(doc_view, t("settings_cb_translate"), "translate_enabled", y)
        y = self._add_popup(doc_view, t("settings_translate_to"), "translate_target", TRANSLATE_LANG_OPTIONS, y)

        y += 6

        # --- Plugins Section ---
        y = self._add_section_header(doc_view, t("settings_section_plugins"), y)
        y = self._add_checkbox(doc_view, t("settings_cb_plugins"), "plugins_enabled", y)

        y += 6

        # --- System Section ---
        y = self._add_section_header(doc_view, t("settings_section_system"), y)
        y = self._add_checkbox(doc_view, t("settings_cb_auto_start"), "auto_start", y)

        # Scroll back to the top now that the document view is populated.
        scroll_view.contentView().scrollToPoint_(NSMakePoint(0, 0))
        scroll_view.reflectScrolledClipView_(scroll_view.contentView())

        # --- Fixed button bar (bottom of the window, outside the scroll view) ---
        self._delegate = _ButtonDelegate.alloc().initWithCallbacks_cancel_(
            self._do_save, self._do_cancel
        )

        # Thin separator above the buttons to visually separate them from the scroll.
        sep = AppKit.NSBox.alloc().initWithFrame_(
            NSMakeRect(0, self.BUTTON_BAR_HEIGHT - 1, self.WINDOW_WIDTH, 1)
        )
        sep.setBoxType_(AppKit.NSBoxSeparator)
        sep.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewMaxYMargin)
        content.addSubview_(sep)

        save_btn = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(310, 12, 90, 32))
        save_btn.setTitle_(t("settings_btn_save"))
        save_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        save_btn.setKeyEquivalent_("\r")
        save_btn.setTarget_(self._delegate)
        save_btn.setAction_(b"onSave:")
        save_btn.setAutoresizingMask_(AppKit.NSViewMinXMargin | AppKit.NSViewMaxYMargin)
        content.addSubview_(save_btn)

        cancel_btn = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(410, 12, 90, 32))
        cancel_btn.setTitle_(t("settings_btn_cancel"))
        cancel_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        cancel_btn.setKeyEquivalent_("\x1b")
        cancel_btn.setTarget_(self._delegate)
        cancel_btn.setAction_(b"onCancel:")
        cancel_btn.setAutoresizingMask_(AppKit.NSViewMinXMargin | AppKit.NSViewMaxYMargin)
        content.addSubview_(cancel_btn)

    # ------------------------------------------------------------------ #
    # Layout helpers — all take a top-down y (flipped coordinate space)   #
    # and return the y for the next widget.                               #
    # ------------------------------------------------------------------ #

    SECTION_HEADER_HEIGHT = 28
    ROW_HEIGHT = 30
    CHECKBOX_HEIGHT = 24

    def _add_section_header(self, view, title, y):
        y += 6  # top breathing room
        label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(20, y, 480, 18))
        label.setStringValue_(title)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setFont_(AppKit.NSFont.boldSystemFontOfSize_(13))
        view.addSubview_(label)

        separator = AppKit.NSBox.alloc().initWithFrame_(NSMakeRect(20, y + 20, 480, 1))
        separator.setBoxType_(AppKit.NSBoxSeparator)
        view.addSubview_(separator)

        return y + self.SECTION_HEADER_HEIGHT

    def _add_popup(self, view, label_text, key, options, y):
        label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(30, y + 4, 140, 20))
        label.setStringValue_(label_text)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        view.addSubview_(label)

        popup = AppKit.NSPopUpButton.alloc().initWithFrame_(NSMakeRect(175, y + 2, 310, 26))
        current_val = self.config.get(key, "")
        if current_val is None:
            current_val = ""
        selected_idx = 0
        for i, (val, display) in enumerate(options):
            popup.addItemWithTitle_(display)
            if val == current_val:
                selected_idx = i
        popup.selectItemAtIndex_(selected_idx)
        view.addSubview_(popup)

        self._controls[key] = ("popup", popup, options)
        return y + self.ROW_HEIGHT

    def _add_checkbox(self, view, label_text, key, y):
        checkbox = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(30, y + 2, 440, 20))
        checkbox.setButtonType_(AppKit.NSSwitchButton)
        checkbox.setTitle_(label_text)
        checkbox.setState_(1 if self.config.get(key, False) else 0)
        view.addSubview_(checkbox)

        self._controls[key] = ("checkbox", checkbox, None)
        return y + self.CHECKBOX_HEIGHT

    def _add_text_field(self, view, label_text, key, y):
        label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(30, y + 4, 140, 20))
        label.setStringValue_(label_text)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        view.addSubview_(label)

        field = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(175, y + 2, 310, 24))
        field.setStringValue_(str(self.config.get(key, "")))
        view.addSubview_(field)

        self._controls[key] = ("text", field, None)
        return y + self.ROW_HEIGHT

    def _read_controls(self) -> dict:
        result = dict(self.config)
        for key, (ctrl_type, ctrl, extra) in self._controls.items():
            if ctrl_type == "popup":
                options = extra
                idx = ctrl.indexOfSelectedItem()
                if 0 <= idx < len(options):
                    val = options[idx][0]
                    result[key] = val if val != "" else None
            elif ctrl_type == "checkbox":
                result[key] = bool(ctrl.state())
            elif ctrl_type == "text":
                result[key] = ctrl.stringValue()
        return result

    def _do_save(self):
        new_config = self._read_controls()
        auto_start = new_config.pop("auto_start", False)
        _set_auto_start(auto_start)
        if self.on_save:
            self.on_save(new_config)
        self.window.close()

    def _do_cancel(self):
        self.window.close()


def _set_auto_start(enabled: bool):
    """Enable/disable auto-start at login via LaunchAgent."""
    launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
    plist_path = launch_agents_dir / "com.speaktype.app.plist"

    if enabled:
        launch_agents_dir.mkdir(parents=True, exist_ok=True)
        program_args, working_dir = get_launch_program_args(__file__)
        args_xml = "\n        ".join(f"<string>{arg}</string>" for arg in program_args)
        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.speaktype.app</string>
    <key>ProgramArguments</key>
    <array>
        {args_xml}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>WorkingDirectory</key>
    <string>{working_dir}</string>
</dict>
</plist>"""
        plist_path.write_text(plist_content, encoding="utf-8")
        logger.info(f"Auto-start enabled: {plist_path}")
    else:
        if plist_path.exists():
            plist_path.unlink()
            logger.info("Auto-start disabled")


def is_auto_start_enabled() -> bool:
    """Check if auto-start is currently enabled."""
    from pathlib import Path
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.speaktype.app.plist"
    return plist_path.exists()
