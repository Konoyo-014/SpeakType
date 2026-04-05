"""First-launch setup wizard — native macOS window guiding new users."""

import os
import shutil
import subprocess
import threading
import logging
import AppKit
import objc
from Foundation import NSObject, NSMakeRect

from .i18n import t
from .config import save_config

logger = logging.getLogger("speaktype.setup_wizard")


def _check_mic_permission() -> bool:
    """Check if microphone permission is granted by testing audio device access."""
    try:
        import sounddevice as sd
        sd.query_devices(kind='input')
        return True
    except Exception:
        return False


def _check_accessibility_permission() -> bool:
    """Check if accessibility permission is granted."""
    try:
        # Try PyObjC ApplicationServices first
        from ApplicationServices import AXIsProcessTrusted
        return AXIsProcessTrusted()
    except ImportError:
        pass
    try:
        # Fallback: try Quartz-based check
        import Quartz
        trusted = Quartz.CGRequestPostEventAccess()
        return bool(trusted)
    except Exception:
        pass
    try:
        # Last resort: osascript
        result = subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to return name of first process'],
            capture_output=True, timeout=3,
        )
        return result.returncode == 0
    except Exception:
        return False


def _find_ollama() -> str:
    """Find the ollama binary path."""
    # Check standard locations (py2app may not have full PATH)
    for path in [
        shutil.which("ollama"),
        "/opt/homebrew/bin/ollama",
        "/usr/local/bin/ollama",
    ]:
        if path and os.path.isfile(path):
            return path
    # Homebrew Cellar search
    cellar = "/opt/homebrew/Cellar/ollama"
    if os.path.isdir(cellar):
        for ver in sorted(os.listdir(cellar), reverse=True):
            candidate = os.path.join(cellar, ver, "bin", "ollama")
            if os.path.isfile(candidate):
                return candidate
    return ""


def _check_ollama_installed() -> bool:
    """Check if Ollama is installed."""
    return bool(_find_ollama())


def _check_ollama_model(model_name: str) -> bool:
    """Check if a specific Ollama model is pulled."""
    ollama = _find_ollama()
    if not ollama:
        return False
    try:
        result = subprocess.run(
            [ollama, "list"], capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            base = model_name.split(":")[0]
            return base in result.stdout
    except Exception:
        pass
    return False


class _WizardDelegate(NSObject):
    """ObjC delegate for wizard button actions."""

    def initWithController_(self, ctrl):
        self = objc.super(_WizardDelegate, self).init()
        if self is not None:
            self._ctrl = ctrl
        return self

    def onNext_(self, sender):
        self._ctrl._next_step()

    def onSkip_(self, sender):
        self._ctrl._skip_step()

    def onRefresh_(self, sender):
        self._ctrl._refresh_current()

    def onOpenSettings_(self, sender):
        subprocess.Popen(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy"])

    def onCopy_(self, sender):
        self._ctrl._copy_command()

    def onDone_(self, sender):
        self._ctrl._finish()


class _ProgressUpdater(NSObject):
    """Thread-safe bridge to update UI from background thread."""

    def initWithController_(self, ctrl):
        self = objc.super(_ProgressUpdater, self).init()
        if self is not None:
            self._ctrl = ctrl
            self._pct = 0.0
            self._status = ""
        return self

    def updateProgress_(self, _):
        self._ctrl._update_progress_ui(self._pct, self._status)


class SetupWizardController:
    """Multi-step setup wizard for first-time users."""

    STEPS = ["welcome", "permissions", "asr", "llm", "complete"]

    def __init__(self, config: dict, asr_engine=None, on_complete=None):
        self.config = config
        self.asr_engine = asr_engine
        self.on_complete = on_complete
        self.window = None
        self._delegate = None
        self._progress_updater = None
        self._step_idx = 0
        self._progress_bar = None
        self._progress_label = None
        self._status_labels = {}
        self._command_text = ""
        self._download_thread = None

    def show(self):
        if self.window and self.window.isVisible():
            self.window.makeKeyAndOrderFront_(None)
            return
        self._build_window()
        self.window.makeKeyAndOrderFront_(None)
        AppKit.NSApp.activateIgnoringOtherApps_(True)

    def _build_window(self):
        frame = NSMakeRect(0, 0, 520, 440)
        style = (
            AppKit.NSTitledWindowMask
            | AppKit.NSClosableWindowMask
        )
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, AppKit.NSBackingStoreBuffered, False
        )
        self.window.setTitle_(t("wizard_title"))
        self.window.center()
        self.window.setLevel_(AppKit.NSFloatingWindowLevel)
        self.window.setTabbingMode_(AppKit.NSWindowTabbingModeDisallowed)
        self.window.setReleasedWhenClosed_(False)

        self._delegate = _WizardDelegate.alloc().initWithController_(self)
        self._progress_updater = _ProgressUpdater.alloc().initWithController_(self)
        self._show_step()

    def _clear_content(self):
        content = self.window.contentView()
        for sub in list(content.subviews()):
            sub.removeFromSuperview()

    def _show_step(self):
        self._clear_content()
        step = self.STEPS[self._step_idx]
        getattr(self, f"_build_{step}")()

    def _next_step(self):
        if self._step_idx < len(self.STEPS) - 1:
            self._step_idx += 1
            self._show_step()

    def _skip_step(self):
        self._next_step()

    def _refresh_current(self):
        self._show_step()

    def _finish(self):
        self.config["setup_completed"] = True
        save_config(self.config)
        # Hide the window instead of closing to avoid Cocoa crash
        self.window.orderOut_(None)
        if self.on_complete:
            self.on_complete()

    def _copy_command(self):
        pb = AppKit.NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(self._command_text, AppKit.NSPasteboardTypeString)

    # --- UI helpers ---

    def _add_title(self, view, text, y):
        label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(30, y, 460, 28))
        label.setStringValue_(text)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setFont_(AppKit.NSFont.boldSystemFontOfSize_(18))
        view.addSubview_(label)
        return y - 36

    def _add_body(self, view, text, y, height=80):
        label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(30, y - height, 460, height))
        label.setStringValue_(text)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setFont_(AppKit.NSFont.systemFontOfSize_(13))
        label.setLineBreakMode_(AppKit.NSLineBreakByWordWrapping)
        label.setUsesSingleLineMode_(False)
        # Use maximumNumberOfLines if available
        if hasattr(label.cell(), 'setWraps_'):
            label.cell().setWraps_(True)
        view.addSubview_(label)
        return y - height - 8

    def _add_status_row(self, view, label_text, ok, y, key=None, ok_text=None, fail_text=None):
        status = (ok_text or t("wizard_perm_ok")) if ok else (fail_text or t("wizard_perm_missing"))
        color = AppKit.NSColor.systemGreenColor() if ok else AppKit.NSColor.systemRedColor()

        label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(40, y, 250, 20))
        label.setStringValue_(label_text)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setFont_(AppKit.NSFont.systemFontOfSize_(13))
        view.addSubview_(label)

        status_label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(300, y, 180, 20))
        status_label.setStringValue_(status)
        status_label.setBezeled_(False)
        status_label.setDrawsBackground_(False)
        status_label.setEditable_(False)
        status_label.setSelectable_(False)
        status_label.setFont_(AppKit.NSFont.systemFontOfSize_(13))
        status_label.setTextColor_(color)
        view.addSubview_(status_label)

        if key:
            self._status_labels[key] = status_label
        return y - 28

    def _add_button(self, view, title, action, x, y, width=120, key_equiv=""):
        btn = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(x, y, width, 32))
        btn.setTitle_(title)
        btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        btn.setTarget_(self._delegate)
        btn.setAction_(action)
        if key_equiv:
            btn.setKeyEquivalent_(key_equiv)
        view.addSubview_(btn)
        return btn

    def _add_command_box(self, view, command, y):
        """Add a copyable command box."""
        self._command_text = command

        box = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(40, y, 360, 24))
        box.setStringValue_(command)
        box.setBezeled_(True)
        box.setDrawsBackground_(True)
        box.setEditable_(False)
        box.setSelectable_(True)
        box.setFont_(AppKit.NSFont.monospacedSystemFontOfSize_weight_(12, AppKit.NSFontWeightRegular))
        view.addSubview_(box)

        self._add_button(view, t("wizard_btn_copy"), b"onCopy:", 410, y - 4, width=80)
        return y - 36

    # --- Step builders ---

    def _build_welcome(self):
        content = self.window.contentView()
        y = 390
        y = self._add_title(content, t("wizard_welcome_title"), y)
        y = self._add_body(content, t("wizard_welcome_body"), y, height=100)
        self._add_button(content, t("wizard_btn_start"), b"onNext:", 370, 20, key_equiv="\r")

    def _build_permissions(self):
        content = self.window.contentView()
        y = 390
        y = self._add_title(content, t("wizard_step_permissions"), y)
        y = self._add_body(content, t("wizard_perm_body"), y, height=70)

        mic_ok = _check_mic_permission()
        access_ok = _check_accessibility_permission()

        y -= 10
        y = self._add_status_row(content, t("wizard_mic_label"), mic_ok, y, key="mic")
        y = self._add_status_row(content, t("wizard_access_label"), access_ok, y, key="access")

        y -= 20
        self._add_button(content, t("wizard_btn_open_settings"), b"onOpenSettings:", 40, y, width=150)
        self._add_button(content, t("wizard_btn_refresh"), b"onRefresh:", 200, y, width=100)

        self._add_button(content, t("wizard_btn_next"), b"onNext:", 370, 20, key_equiv="\r")

    def _build_asr(self):
        content = self.window.contentView()
        y = 390
        y = self._add_title(content, t("wizard_step_asr"), y)
        y = self._add_body(content, t("wizard_asr_body"), y, height=60)

        from .model_download import is_model_cached
        cached = is_model_cached(self.config.get("asr_model", "mlx-community/Qwen3-ASR-1.7B-8bit"))

        y -= 10
        if cached:
            # Already cached
            status_label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(40, y, 440, 20))
            status_label.setStringValue_(t("wizard_asr_cached"))
            status_label.setBezeled_(False)
            status_label.setDrawsBackground_(False)
            status_label.setEditable_(False)
            status_label.setSelectable_(False)
            status_label.setFont_(AppKit.NSFont.systemFontOfSize_(13))
            status_label.setTextColor_(AppKit.NSColor.systemGreenColor())
            content.addSubview_(status_label)
            self._add_button(content, t("wizard_btn_next"), b"onNext:", 370, 20, key_equiv="\r")
        else:
            # Show progress bar and start download
            self._progress_label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(40, y, 440, 20))
            self._progress_label.setStringValue_(t("wizard_asr_downloading", pct=0, size="0/0 MB"))
            self._progress_label.setBezeled_(False)
            self._progress_label.setDrawsBackground_(False)
            self._progress_label.setEditable_(False)
            self._progress_label.setSelectable_(False)
            self._progress_label.setFont_(AppKit.NSFont.systemFontOfSize_(13))
            content.addSubview_(self._progress_label)

            y -= 30
            self._progress_bar = AppKit.NSProgressIndicator.alloc().initWithFrame_(
                NSMakeRect(40, y, 440, 20)
            )
            self._progress_bar.setIndeterminate_(False)
            self._progress_bar.setMinValue_(0)
            self._progress_bar.setMaxValue_(100)
            self._progress_bar.setDoubleValue_(0)
            self._progress_bar.setStyle_(AppKit.NSProgressIndicatorStyleBar)
            content.addSubview_(self._progress_bar)

            # Start download in background
            self._download_thread = threading.Thread(target=self._do_download, daemon=True)
            self._download_thread.start()

    def _do_download(self):
        """Run model download in background thread."""
        model_name = self.config.get("asr_model", "mlx-community/Qwen3-ASR-1.7B-8bit")

        def on_progress(pct, status):
            self._progress_updater._pct = pct
            self._progress_updater._status = status
            self._progress_updater.performSelectorOnMainThread_withObject_waitUntilDone_(
                b"updateProgress:", None, False
            )

        try:
            from .model_download import download_model_with_progress
            download_model_with_progress(model_name, callback=on_progress)
            on_progress(100.0, "Done")
        except Exception as e:
            logger.error(f"Download failed in wizard: {e}")
            self._progress_updater._pct = -1
            self._progress_updater._status = str(e)
            self._progress_updater.performSelectorOnMainThread_withObject_waitUntilDone_(
                b"updateProgress:", None, False
            )

    def _update_progress_ui(self, pct, status):
        """Called on main thread to update progress UI."""
        if pct < 0:
            # Error
            if self._progress_label:
                self._progress_label.setStringValue_(t("wizard_asr_error", error=status[:60]))
                self._progress_label.setTextColor_(AppKit.NSColor.systemRedColor())
            self._add_button(self.window.contentView(), t("wizard_btn_next"), b"onNext:", 370, 20, key_equiv="\r")
            return

        if self._progress_bar:
            self._progress_bar.setDoubleValue_(pct)
        if self._progress_label:
            if pct >= 100:
                self._progress_label.setStringValue_(t("wizard_asr_done"))
                self._progress_label.setTextColor_(AppKit.NSColor.systemGreenColor())
                self._add_button(self.window.contentView(), t("wizard_btn_next"), b"onNext:", 370, 20, key_equiv="\r")
            else:
                self._progress_label.setStringValue_(t("wizard_asr_downloading", pct=pct, size=status))

    def _build_llm(self):
        content = self.window.contentView()
        y = 390
        y = self._add_title(content, t("wizard_step_llm"), y)
        y = self._add_body(content, t("wizard_llm_body"), y, height=60)

        ollama_ok = _check_ollama_installed()
        model_name = self.config.get("llm_model", "huihui_ai/qwen3.5-abliterated:9b-Claude")
        model_ok = _check_ollama_model(model_name) if ollama_ok else False

        y -= 10
        y = self._add_status_row(content, "Ollama", ollama_ok, y,
                                 ok_text=t("wizard_ollama_ok"), fail_text=t("wizard_ollama_missing"))

        if not ollama_ok:
            y -= 5
            hint = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(40, y, 200, 18))
            hint.setStringValue_(t("wizard_ollama_install_hint"))
            hint.setBezeled_(False)
            hint.setDrawsBackground_(False)
            hint.setEditable_(False)
            hint.setSelectable_(False)
            hint.setFont_(AppKit.NSFont.systemFontOfSize_(12))
            hint.setTextColor_(AppKit.NSColor.secondaryLabelColor())
            content.addSubview_(hint)
            y -= 24
            y = self._add_command_box(content, "brew install ollama && ollama serve", y)

        y = self._add_status_row(content, "LLM Model", model_ok, y,
                                 ok_text=t("wizard_model_ok"), fail_text=t("wizard_model_missing"))

        if ollama_ok and not model_ok:
            y -= 5
            hint = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(40, y, 200, 18))
            hint.setStringValue_(t("wizard_model_pull_hint"))
            hint.setBezeled_(False)
            hint.setDrawsBackground_(False)
            hint.setEditable_(False)
            hint.setSelectable_(False)
            hint.setFont_(AppKit.NSFont.systemFontOfSize_(12))
            hint.setTextColor_(AppKit.NSColor.secondaryLabelColor())
            content.addSubview_(hint)
            y -= 24
            y = self._add_command_box(content, f"ollama pull {model_name}", y)

        self._add_button(content, t("wizard_btn_refresh"), b"onRefresh:", 40, 20, width=100)
        self._add_button(content, t("wizard_btn_skip"), b"onSkip:", 250, 20, width=100)
        self._add_button(content, t("wizard_btn_next"), b"onNext:", 370, 20, key_equiv="\r")

    def _build_complete(self):
        content = self.window.contentView()
        y = 390
        y = self._add_title(content, t("wizard_step_complete"), y)

        hotkey_map = {
            "right_cmd": "右 ⌘", "left_cmd": "左 ⌘", "fn": "Fn",
            "right_alt": "右 ⌥", "right_ctrl": "右 ⌃",
        }
        hotkey = self.config.get("hotkey", "right_cmd")
        hotkey_display = hotkey_map.get(hotkey, hotkey)
        y = self._add_body(content, t("wizard_complete_body", hotkey=hotkey_display), y, height=100)

        self._add_button(content, t("wizard_btn_done"), b"onDone:", 320, 20, width=170, key_equiv="\r")
