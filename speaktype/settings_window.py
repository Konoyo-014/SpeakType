"""Native macOS Settings window using PyObjC."""

import logging
import AppKit
import objc
from Foundation import NSObject, NSMakeRect

logger = logging.getLogger("speaktype.settings")

# Hotkey options
HOTKEY_OPTIONS = [
    ("right_cmd", "Right ⌘ (Hold)"),
    ("left_cmd", "Left ⌘ (Hold)"),
    ("right_alt", "Right ⌥ (Hold)"),
    ("right_ctrl", "Right ⌃ (Hold)"),
    ("ctrl+shift+space", "⌃⇧Space (Hold)"),
    ("f5", "F5 (Hold)"),
    ("f6", "F6 (Hold)"),
]

LANGUAGE_OPTIONS = [
    ("auto", "Auto Detect"),
    ("en", "English"),
    ("zh", "中文 (Chinese)"),
    ("ja", "日本語 (Japanese)"),
    ("ko", "한국어 (Korean)"),
    ("es", "Español (Spanish)"),
    ("fr", "Français (French)"),
    ("de", "Deutsch (German)"),
]

LLM_MODEL_OPTIONS = [
    ("huihui_ai/qwen3.5-abliterated:9b-Claude", "Qwen 3.5 9B Abliterated (Default)"),
    ("qwen3.5:4b", "Qwen 3.5 4B (Fast/Lightweight)"),
    ("qwen3.5:9b", "Qwen 3.5 9B (Standard)"),
    ("qwen3.5:14b", "Qwen 3.5 14B (Best Quality)"),
]

ASR_MODEL_OPTIONS = [
    ("mlx-community/Qwen3-ASR-1.7B-8bit", "Qwen3-ASR 1.7B (Recommended)"),
    ("mlx-community/Qwen3-ASR-0.6B-4bit", "Qwen3-ASR 0.6B (Faster)"),
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

    def _build_window(self):
        frame = NSMakeRect(0, 0, 520, 580)
        style = (
            AppKit.NSTitledWindowMask
            | AppKit.NSClosableWindowMask
            | AppKit.NSMiniaturizableWindowMask
        )
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, AppKit.NSBackingStoreBuffered, False
        )
        self.window.setTitle_("SpeakType Settings")
        self.window.center()
        self.window.setLevel_(AppKit.NSFloatingWindowLevel)
        # Disable window tabbing to prevent crash on macOS 13+
        self.window.setTabbingMode_(AppKit.NSWindowTabbingModeDisallowed)

        content = self.window.contentView()
        y = 540

        # --- General Section ---
        y = self._add_section_header(content, "General", y)
        y = self._add_popup(content, "Hotkey:", "hotkey", HOTKEY_OPTIONS, y)
        y = self._add_popup(content, "Language:", "language", LANGUAGE_OPTIONS, y)
        y = self._add_popup(content, "Insert Method:", "insert_method",
                            [("paste", "Paste (Cmd+V) — Fast"), ("type", "Keystroke — Compatible")], y)

        y -= 10

        # --- AI Models Section ---
        y = self._add_section_header(content, "AI Models", y)
        y = self._add_popup(content, "ASR Model:", "asr_model", ASR_MODEL_OPTIONS, y)
        y = self._add_popup(content, "LLM Model:", "llm_model", LLM_MODEL_OPTIONS, y)
        y = self._add_text_field(content, "Ollama URL:", "ollama_url", y)

        y -= 10

        # --- Features Section ---
        y = self._add_section_header(content, "Features", y)
        y = self._add_checkbox(content, "Enable Text Polishing (LLM)", "polish_enabled", y)
        y = self._add_checkbox(content, "Enable Voice Commands", "voice_commands_enabled", y)
        y = self._add_checkbox(content, "Context-Aware Tone", "context_aware_tone", y)
        y = self._add_checkbox(content, "Sound Feedback", "sound_feedback", y)
        y = self._add_checkbox(content, "Save Dictation History", "history_enabled", y)
        y = self._add_checkbox(content, "Translate After Transcription", "translate_enabled", y)
        y = self._add_popup(content, "Translate To:", "translate_target",
                            [("en", "English"), ("zh", "中文"), ("ja", "日本語"),
                             ("ko", "한국어"), ("es", "Español"), ("fr", "Français"), ("de", "Deutsch")], y)

        y -= 10

        # --- System Section ---
        y = self._add_section_header(content, "System", y)
        y = self._add_checkbox(content, "Start at Login", "auto_start", y)

        y -= 20

        # --- Buttons ---
        self._delegate = _ButtonDelegate.alloc().initWithCallbacks_cancel_(
            self._do_save, self._do_cancel
        )

        save_btn = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(310, 15, 90, 32))
        save_btn.setTitle_("Save")
        save_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        save_btn.setKeyEquivalent_("\r")
        save_btn.setTarget_(self._delegate)
        save_btn.setAction_(b"onSave:")
        content.addSubview_(save_btn)

        cancel_btn = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(410, 15, 90, 32))
        cancel_btn.setTitle_("Cancel")
        cancel_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        cancel_btn.setKeyEquivalent_("\x1b")
        cancel_btn.setTarget_(self._delegate)
        cancel_btn.setAction_(b"onCancel:")
        content.addSubview_(cancel_btn)

    def _add_section_header(self, view, title, y):
        y -= 8
        label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(20, y - 20, 480, 18))
        label.setStringValue_(title)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setFont_(AppKit.NSFont.boldSystemFontOfSize_(13))
        view.addSubview_(label)

        separator = AppKit.NSBox.alloc().initWithFrame_(NSMakeRect(20, y - 24, 480, 1))
        separator.setBoxType_(AppKit.NSBoxSeparator)
        view.addSubview_(separator)

        return y - 32

    def _add_popup(self, view, label_text, key, options, y):
        label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(30, y - 26, 140, 20))
        label.setStringValue_(label_text)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        view.addSubview_(label)

        popup = AppKit.NSPopUpButton.alloc().initWithFrame_(NSMakeRect(175, y - 28, 310, 26))
        current_val = self.config.get(key, "")
        selected_idx = 0
        for i, (val, display) in enumerate(options):
            popup.addItemWithTitle_(display)
            if val == current_val:
                selected_idx = i
        popup.selectItemAtIndex_(selected_idx)
        view.addSubview_(popup)

        self._controls[key] = ("popup", popup, options)
        return y - 34

    def _add_checkbox(self, view, label_text, key, y):
        checkbox = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(30, y - 24, 440, 20))
        checkbox.setButtonType_(AppKit.NSSwitchButton)
        checkbox.setTitle_(label_text)
        checkbox.setState_(1 if self.config.get(key, False) else 0)
        view.addSubview_(checkbox)

        self._controls[key] = ("checkbox", checkbox, None)
        return y - 28

    def _add_text_field(self, view, label_text, key, y):
        label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(30, y - 26, 140, 20))
        label.setStringValue_(label_text)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        view.addSubview_(label)

        field = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(175, y - 28, 310, 24))
        field.setStringValue_(str(self.config.get(key, "")))
        view.addSubview_(field)

        self._controls[key] = ("text", field, None)
        return y - 34

    def _read_controls(self) -> dict:
        result = dict(self.config)
        for key, (ctrl_type, ctrl, extra) in self._controls.items():
            if ctrl_type == "popup":
                options = extra
                idx = ctrl.indexOfSelectedItem()
                if 0 <= idx < len(options):
                    result[key] = options[idx][0]
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
    import os
    from pathlib import Path

    launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
    plist_path = launch_agents_dir / "com.speaktype.app.plist"

    if enabled:
        launch_agents_dir.mkdir(parents=True, exist_ok=True)
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        python_path = os.path.join(project_dir, "venv", "bin", "python3")
        main_path = os.path.join(project_dir, "main.py")

        app_path = os.path.join(project_dir, "dist", "SpeakType.app")
        if os.path.exists(app_path):
            program_args = ["open", app_path]
        else:
            program_args = [python_path, main_path]

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
    <string>{project_dir}</string>
</dict>
</plist>"""
        with open(plist_path, "w") as f:
            f.write(plist_content)
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
