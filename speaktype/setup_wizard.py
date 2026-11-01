"""First-launch setup wizard — native macOS window guiding new users."""

import os
import shutil
import subprocess
import threading
import logging
import AppKit
import objc
import requests
from Foundation import NSObject, NSMakeRect

from .i18n import t, localized_hotkey_display
from .config import save_config
from .applescript import run_osascript
from .permissions import get_permission_status, request_missing_permissions
from .permissions import microphone_is_authorized, request_microphone_if_needed
from .polish import NO_PROXY_FOR_LOCAL_OLLAMA
from .polish import ollama_model_is_available

logger = logging.getLogger("speaktype.setup_wizard")


def command_for_copy_sender(sender, fallback: str, commands: dict[int, str]) -> str:
    """Return the command associated with a specific Copy Command button."""
    try:
        tag = int(sender.tag())
    except Exception:
        tag = 0
    return str(commands.get(tag) or fallback or "")


def copy_confirmation_title() -> str:
    return t("wizard_btn_copied")


def setup_wizard_llm_labels() -> dict[str, str]:
    return {
        "ollama": t("wizard_ollama_label"),
        "service": t("wizard_ollama_service_label"),
        "model": t("wizard_llm_model_label"),
    }


def setup_wizard_download_status_text(status: str) -> str:
    normalized = str(status or "").strip()
    if not normalized or normalized.lower().startswith("starting"):
        return t("wizard_asr_starting")
    if normalized.lower() == "done":
        return t("wizard_asr_done_short")
    return normalized


def setup_wizard_download_error_text(error: str) -> str:
    detail = str(error or "").strip()
    lower = detail.lower()
    if not detail:
        return t("wizard_asr_error_unknown")
    if "unknown argument" in lower and "huggingface_hub.snapshot_download" in detail:
        return t("wizard_asr_error_downloader")
    if "404" in detail or "not found" in lower:
        return t("wizard_asr_error_model_not_found")
    if any(token in lower for token in ("timeout", "timed out", "connection", "network", "http")):
        return t("wizard_asr_error_network", error=detail[:80])
    return t("wizard_asr_error", error=detail[:80])


def setup_wizard_asr_state_label_height(text: str) -> int:
    length = len(str(text or ""))
    if length > 96:
        return 60
    if length > 42:
        return 42
    return 22


def _check_mic_permission() -> bool:
    request_microphone_if_needed()
    return microphone_is_authorized()


def _check_accessibility_permission() -> bool:
    """Check if accessibility permission is granted."""
    status = get_permission_status()
    if status.accessibility and status.post_event:
        return True

    request_missing_permissions(status)
    refreshed = get_permission_status()
    return refreshed.accessibility and refreshed.post_event


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


def _check_ollama_running(ollama_url: str = "http://localhost:11434") -> bool:
    """Check if the local Ollama HTTP service is reachable."""
    try:
        resp = requests.get(
            f"{ollama_url.rstrip('/')}/api/tags",
            timeout=1,
            proxies=NO_PROXY_FOR_LOCAL_OLLAMA,
        )
        return resp.status_code == 200
    except Exception:
        return False


def _check_ollama_model(model_name: str, ollama_url: str = "http://localhost:11434") -> bool:
    """Check if a specific Ollama model is pulled."""
    try:
        response = requests.get(f"{ollama_url.rstrip('/')}/api/tags", timeout=3,
                                proxies=NO_PROXY_FOR_LOCAL_OLLAMA)
        response.raise_for_status()
        return ollama_model_is_available(model_name, [model["name"] for model in response.json()["models"]])
    except requests.RequestException:
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
        self._ctrl._copy_command(sender)

    def onDownload_(self, sender):
        self._ctrl._start_asr_download()

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
    WINDOW_WIDTH = 560
    WINDOW_HEIGHT = 520
    CONTENT_X = 34
    CONTENT_WIDTH = 492
    TOP_Y = 420
    BUTTON_Y = 20

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
        self._copy_commands = {}
        self._copy_tag = 0
        self._download_thread = None
        self._asr_download_state = "idle"
        self._asr_download_error = ""

    def show(self):
        if self.window and self.window.isVisible():
            self.window.makeKeyAndOrderFront_(None)
            return
        self._build_window()
        self.window.makeKeyAndOrderFront_(None)
        AppKit.NSApp.activateIgnoringOtherApps_(True)

    def _build_window(self):
        frame = NSMakeRect(0, 0, self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
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
        self._progress_bar = None
        self._progress_label = None
        self._copy_commands = {}
        self._copy_tag = 0
        self._add_step_indicator(self.window.contentView())
        step = self.STEPS[self._step_idx]
        getattr(self, f"_build_{step}")()

    def _next_step(self):
        if self._step_idx < len(self.STEPS) - 1:
            self._step_idx += 1
            self._show_step()

    def _skip_step(self):
        if self.STEPS[self._step_idx] == "llm":
            self.config["polish_enabled"] = False
            self.config["translate_enabled"] = False
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

    def _copy_command(self, sender=None):
        command = command_for_copy_sender(sender, self._command_text, self._copy_commands)
        pb = AppKit.NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(command, AppKit.NSPasteboardTypeString)
        try:
            sender.setTitle_(copy_confirmation_title())
        except Exception:
            pass

    # --- UI helpers ---

    def _add_title(self, view, text, y):
        label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(self.CONTENT_X, y, self.CONTENT_WIDTH, 28))
        label.setStringValue_(text)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setFont_(AppKit.NSFont.boldSystemFontOfSize_(18))
        view.addSubview_(label)
        return y - 36

    def _add_body(self, view, text, y, height=80):
        label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(self.CONTENT_X, y - height, self.CONTENT_WIDTH, height))
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

        label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(44, y, 245, 20))
        label.setStringValue_(label_text)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setFont_(AppKit.NSFont.systemFontOfSize_(13))
        view.addSubview_(label)

        status_label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(310, y, 220, 20))
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

    def _add_step_indicator(self, view):
        current = self._step_idx + 1
        total = len(self.STEPS)
        label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(self.CONTENT_X, 472, self.CONTENT_WIDTH, 18))
        label.setStringValue_(t("wizard_step_progress", current=current, total=total))
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setFont_(AppKit.NSFont.systemFontOfSize_(11))
        label.setTextColor_(AppKit.NSColor.secondaryLabelColor())
        view.addSubview_(label)

        track = AppKit.NSView.alloc().initWithFrame_(NSMakeRect(self.CONTENT_X, 456, self.CONTENT_WIDTH, 6))
        track.setWantsLayer_(True)
        track_layer = track.layer()
        if track_layer is not None:
            track_layer.setCornerRadius_(3)
            track_layer.setBackgroundColor_(AppKit.NSColor.tertiaryLabelColor().colorWithAlphaComponent_(0.22).CGColor())
        view.addSubview_(track)

        fraction = current / max(total, 1)
        fill = AppKit.NSView.alloc().initWithFrame_(NSMakeRect(self.CONTENT_X, 456, max(8, round(self.CONTENT_WIDTH * fraction)), 6))
        fill.setWantsLayer_(True)
        fill_layer = fill.layer()
        if fill_layer is not None:
            fill_layer.setCornerRadius_(3)
            fill_layer.setBackgroundColor_(AppKit.NSColor.controlAccentColor().CGColor())
        view.addSubview_(fill)

    def _right_x(self, width=120, margin=30):
        return self.WINDOW_WIDTH - margin - width

    def _add_command_box(self, view, command, y):
        """Add a copyable command box."""
        self._command_text = command

        box = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(44, y, 482, 24))
        box.setStringValue_(command)
        box.setBezeled_(True)
        box.setDrawsBackground_(True)
        box.setEditable_(False)
        box.setSelectable_(True)
        box.setFont_(AppKit.NSFont.monospacedSystemFontOfSize_weight_(11, AppKit.NSFontWeightRegular))
        view.addSubview_(box)

        button = self._add_button(view, t("wizard_btn_copy"), b"onCopy:", 416, y - 36, width=110)
        self._copy_tag += 1
        button.setTag_(self._copy_tag)
        self._copy_commands[self._copy_tag] = command
        return y - 50

    # --- Step builders ---

    def _build_welcome(self):
        content = self.window.contentView()
        y = self.TOP_Y
        y = self._add_title(content, t("wizard_welcome_title"), y)
        y = self._add_body(content, t("wizard_welcome_body"), y, height=100)
        self._add_button(content, t("wizard_btn_start"), b"onNext:", self._right_x(), self.BUTTON_Y, key_equiv="\r")

    def _build_permissions(self):
        content = self.window.contentView()
        y = self.TOP_Y
        y = self._add_title(content, t("wizard_step_permissions"), y)
        y = self._add_body(content, t("wizard_perm_body"), y, height=90)

        mic_ok = _check_mic_permission()
        access_ok = _check_accessibility_permission()

        y -= 10
        y = self._add_status_row(content, t("wizard_mic_label"), mic_ok, y, key="mic")
        y = self._add_status_row(content, t("wizard_access_label"), access_ok, y, key="access")
        y = self._add_status_row(content, t("wizard_listen_label"), get_permission_status().listen_event, y, key="listen")

        y -= 20
        self._add_button(content, t("wizard_btn_open_settings"), b"onOpenSettings:", 44, y, width=150)
        self._add_button(content, t("wizard_btn_refresh"), b"onRefresh:", 204, y, width=100)

        self._add_button(content, t("wizard_btn_next"), b"onNext:", self._right_x(), self.BUTTON_Y, key_equiv="\r")

    def _build_asr(self):
        content = self.window.contentView()
        y = self.TOP_Y
        y = self._add_title(content, t("wizard_step_asr"), y)
        y = self._add_body(content, t("wizard_asr_body"), y, height=60)

        from .model_download import is_model_cached
        cached = is_model_cached(self.config.get("asr_model", "mlx-community/Qwen3-ASR-1.7B-8bit"))

        y -= 10
        if cached:
            # Already cached
            status_label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(44, y, 480, 20))
            status_label.setStringValue_(t("wizard_asr_cached") if cached else t("wizard_asr_done"))
            status_label.setBezeled_(False)
            status_label.setDrawsBackground_(False)
            status_label.setEditable_(False)
            status_label.setSelectable_(False)
            status_label.setFont_(AppKit.NSFont.systemFontOfSize_(13))
            status_label.setTextColor_(AppKit.NSColor.systemGreenColor())
            content.addSubview_(status_label)
            self._add_button(content, t("wizard_btn_next"), b"onNext:", self._right_x(), self.BUTTON_Y, key_equiv="\r")
        elif self._asr_download_state == "running":
            # Show progress while the user-confirmed download runs.
            self._progress_label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(44, y, 480, 20))
            self._progress_label.setStringValue_(
                t("wizard_asr_downloading", pct=0, size=setup_wizard_download_status_text(""))
            )
            self._progress_label.setBezeled_(False)
            self._progress_label.setDrawsBackground_(False)
            self._progress_label.setEditable_(False)
            self._progress_label.setSelectable_(False)
            self._progress_label.setFont_(AppKit.NSFont.systemFontOfSize_(13))
            content.addSubview_(self._progress_label)

            y -= 30
            self._progress_bar = AppKit.NSProgressIndicator.alloc().initWithFrame_(
                NSMakeRect(44, y, 480, 20)
            )
            self._progress_bar.setIndeterminate_(False)
            self._progress_bar.setMinValue_(0)
            self._progress_bar.setMaxValue_(100)
            self._progress_bar.setDoubleValue_(0)
            self._progress_bar.setStyle_(AppKit.NSProgressIndicatorStyleBar)
            content.addSubview_(self._progress_bar)
        else:
            status_text = (
                setup_wizard_download_error_text(self._asr_download_error)
                if self._asr_download_state == "error"
                else t("wizard_asr_missing")
            )
            status_height = setup_wizard_asr_state_label_height(status_text)
            status_bottom = y - max(0, status_height - 20)
            status_label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(44, status_bottom, 480, status_height))
            status_label.setStringValue_(status_text)
            status_label.setBezeled_(False)
            status_label.setDrawsBackground_(False)
            status_label.setEditable_(False)
            status_label.setSelectable_(False)
            status_label.setFont_(AppKit.NSFont.systemFontOfSize_(13))
            status_label.setLineBreakMode_(AppKit.NSLineBreakByWordWrapping)
            status_label.setUsesSingleLineMode_(False)
            if hasattr(status_label.cell(), "setWraps_"):
                status_label.cell().setWraps_(True)
            status_label.setTextColor_(
                AppKit.NSColor.systemRedColor()
                if self._asr_download_state == "error"
                else AppKit.NSColor.systemOrangeColor()
            )
            content.addSubview_(status_label)

            hint = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(44, status_bottom - 64, 480, 54))
            hint.setStringValue_(t("wizard_asr_download_ready"))
            hint.setBezeled_(False)
            hint.setDrawsBackground_(False)
            hint.setEditable_(False)
            hint.setSelectable_(False)
            hint.setFont_(AppKit.NSFont.systemFontOfSize_(12))
            hint.setLineBreakMode_(AppKit.NSLineBreakByWordWrapping)
            hint.setUsesSingleLineMode_(False)
            if hasattr(hint.cell(), "setWraps_"):
                hint.cell().setWraps_(True)
            hint.setTextColor_(AppKit.NSColor.secondaryLabelColor())
            content.addSubview_(hint)

            self._add_button(content, t("wizard_btn_download"), b"onDownload:", 44, self.BUTTON_Y, width=120)
            self._add_button(content, t("wizard_btn_later"), b"onSkip:", 184, self.BUTTON_Y, width=120)

    def _start_asr_download(self):
        if self._download_thread is not None and self._download_thread.is_alive():
            return
        self._asr_download_state = "running"
        self._asr_download_error = ""
        self._show_step()
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
            self._asr_download_state = "error"
            self._asr_download_error = status
            self._show_step()
            return

        if pct >= 100 and str(status).lower() == "done":
            self._asr_download_state = "done"
            self._show_step()
            return

        if self._progress_bar:
            self._progress_bar.setDoubleValue_(min(pct, 99))
        if self._progress_label:
            self._progress_label.setStringValue_(
                t("wizard_asr_downloading", pct=min(pct, 99), size=setup_wizard_download_status_text(status))
            )

    def _build_llm(self):
        content = self.window.contentView()
        y = self.TOP_Y
        y = self._add_title(content, t("wizard_step_llm"), y)
        y = self._add_body(content, t("wizard_llm_body"), y, height=72)

        ollama_ok = _check_ollama_installed()
        ollama_url = self.config.get("ollama_url", "http://localhost:11434")
        ollama_running = _check_ollama_running(ollama_url) if ollama_ok else False
        model_name = self.config.get("llm_model", "huihui_ai/qwen3.5-abliterated:9b-Claude")
        model_ok = _check_ollama_model(model_name, self.config.get("ollama_url", "http://localhost:11434")) if ollama_ok else False
        labels = setup_wizard_llm_labels()

        y -= 10
        y = self._add_status_row(content, labels["ollama"], ollama_ok, y,
                                 ok_text=t("wizard_ollama_ok"), fail_text=t("wizard_ollama_missing"))

        if not ollama_ok:
            y -= 5
            hint = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(44, y, 400, 18))
            hint.setStringValue_(t("wizard_ollama_install_hint"))
            hint.setBezeled_(False)
            hint.setDrawsBackground_(False)
            hint.setEditable_(False)
            hint.setSelectable_(False)
            hint.setFont_(AppKit.NSFont.systemFontOfSize_(12))
            hint.setTextColor_(AppKit.NSColor.secondaryLabelColor())
            content.addSubview_(hint)
            y -= 24
            y = self._add_command_box(content, "brew install ollama", y)

        if ollama_ok:
            y = self._add_status_row(content, labels["service"], ollama_running, y,
                                     ok_text=t("wizard_ollama_running_ok"),
                                     fail_text=t("wizard_ollama_running_missing"))

            if not ollama_running:
                y -= 5
                hint = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(44, y, 420, 18))
                hint.setStringValue_(t("wizard_ollama_start_hint"))
                hint.setBezeled_(False)
                hint.setDrawsBackground_(False)
                hint.setEditable_(False)
                hint.setSelectable_(False)
                hint.setFont_(AppKit.NSFont.systemFontOfSize_(12))
                hint.setTextColor_(AppKit.NSColor.secondaryLabelColor())
                content.addSubview_(hint)
                y -= 24
                y = self._add_command_box(content, "ollama serve", y)

            y = self._add_status_row(content, labels["model"], model_ok, y,
                                     ok_text=t("wizard_model_ok"), fail_text=t("wizard_model_missing"))

            if not model_ok:
                y -= 5
                hint = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(44, y, 400, 18))
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

        self._add_button(content, t("wizard_btn_refresh"), b"onRefresh:", 44, self.BUTTON_Y, width=100)
        self._add_button(content, t("wizard_btn_skip"), b"onSkip:", 298, self.BUTTON_Y, width=100)
        self._add_button(content, t("wizard_btn_next"), b"onNext:", self._right_x(), self.BUTTON_Y, key_equiv="\r")

    def _build_complete(self):
        content = self.window.contentView()
        y = self.TOP_Y
        y = self._add_title(content, t("wizard_step_complete"), y)

        hotkey = self.config.get("hotkey", "right_cmd")
        hotkey_display = localized_hotkey_display(hotkey)
        y = self._add_body(content, t("wizard_complete_body", hotkey=hotkey_display), y, height=100)

        self._add_button(content, t("wizard_btn_done"), b"onDone:", self._right_x(width=170), self.BUTTON_Y, width=170, key_equiv="\r")
