"""Native macOS Settings window using PyObjC."""

import logging
import AppKit
import objc
from Foundation import NSObject, NSMakeRect

logger = logging.getLogger("speaktype.settings")

# Hotkey options
HOTKEY_OPTIONS = [
    ("right_cmd", "右 \u2318（按住）"),
    ("left_cmd", "左 \u2318（按住）"),
    ("right_alt", "右 \u2325（按住）"),
    ("right_ctrl", "右 \u2303（按住）"),
    ("ctrl+shift+space", "\u2303\u21e7Space（按住）"),
    ("f5", "F5（按住）"),
    ("f6", "F6（按住）"),
]

DICTATION_MODE_OPTIONS = [
    ("push_to_talk", "按住说话"),
    ("toggle", "按下开关"),
]

LANGUAGE_OPTIONS = [
    ("auto", "自动检测"),
    ("en", "English"),
    ("zh", "\u4e2d\u6587 (Chinese)"),
    ("ja", "\u65e5\u672c\u8a9e (Japanese)"),
    ("ko", "\ud55c\uad6d\uc5b4 (Korean)"),
    ("es", "Espa\u00f1ol (Spanish)"),
    ("fr", "Fran\u00e7ais (French)"),
    ("de", "Deutsch (German)"),
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

    def _build_window(self):
        frame = NSMakeRect(0, 0, 520, 740)
        style = (
            AppKit.NSTitledWindowMask
            | AppKit.NSClosableWindowMask
            | AppKit.NSMiniaturizableWindowMask
        )
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, AppKit.NSBackingStoreBuffered, False
        )
        self.window.setTitle_("SpeakType 偏好设置")
        self.window.center()
        self.window.setLevel_(AppKit.NSFloatingWindowLevel)
        self.window.setTabbingMode_(AppKit.NSWindowTabbingModeDisallowed)

        content = self.window.contentView()
        y = 700

        # --- General Section ---
        y = self._add_section_header(content, "通用", y)
        y = self._add_popup(content, "快捷键：", "hotkey", HOTKEY_OPTIONS, y)
        y = self._add_popup(content, "听写模式：", "dictation_mode", DICTATION_MODE_OPTIONS, y)
        y = self._add_popup(content, "语言：", "language", LANGUAGE_OPTIONS, y)
        y = self._add_popup(content, "输入方式：", "insert_method",
                            [("paste", "粘贴 (\u2318V) \u2014 快速"), ("type", "逐字输入 \u2014 兼容")], y)

        # Audio device
        from .devices import list_input_devices
        device_options = [("", "系统默认")]
        for dev in list_input_devices():
            device_options.append((dev["name"], dev["name"]))
        y = self._add_popup(content, "音频设备：", "audio_device", device_options, y)

        y -= 10

        # --- AI Models Section ---
        y = self._add_section_header(content, "AI 模型", y)
        y = self._add_popup(content, "语音识别后端：", "asr_backend", ASR_BACKEND_OPTIONS, y)
        y = self._add_popup(content, "Qwen ASR 模型：", "asr_model", ASR_MODEL_OPTIONS, y)
        y = self._add_popup(content, "Whisper 模型：", "whisper_model", WHISPER_MODEL_OPTIONS, y)
        y = self._add_popup(content, "大语言模型：", "llm_model", LLM_MODEL_OPTIONS, y)
        y = self._add_text_field(content, "Ollama 地址：", "ollama_url", y)

        y -= 10

        # --- Features Section ---
        y = self._add_section_header(content, "功能", y)
        y = self._add_checkbox(content, "启用文本润色 (LLM)", "polish_enabled", y)
        y = self._add_checkbox(content, "启用语音指令", "voice_commands_enabled", y)
        y = self._add_checkbox(content, "智能语气", "context_aware_tone", y)
        y = self._add_checkbox(content, "声音反馈", "sound_feedback", y)
        y = self._add_checkbox(content, "保存听写历史", "history_enabled", y)
        y = self._add_checkbox(content, "转写后翻译", "translate_enabled", y)
        y = self._add_popup(content, "翻译目标语言：", "translate_target", TRANSLATE_LANG_OPTIONS, y)

        y -= 10

        # --- Plugins Section ---
        y = self._add_section_header(content, "插件", y)
        y = self._add_checkbox(content, "启用插件系统", "plugins_enabled", y)

        y -= 10

        # --- System Section ---
        y = self._add_section_header(content, "系统", y)
        y = self._add_checkbox(content, "登录时启动", "auto_start", y)

        y -= 20

        # --- Buttons ---
        self._delegate = _ButtonDelegate.alloc().initWithCallbacks_cancel_(
            self._do_save, self._do_cancel
        )

        save_btn = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(310, 15, 90, 32))
        save_btn.setTitle_("保存")
        save_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        save_btn.setKeyEquivalent_("\r")
        save_btn.setTarget_(self._delegate)
        save_btn.setAction_(b"onSave:")
        content.addSubview_(save_btn)

        cancel_btn = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(410, 15, 90, 32))
        cancel_btn.setTitle_("取消")
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
