"""Main SpeakType application - menubar app with push-to-talk voice input."""

import os
import sys
import time
import threading
import logging
import subprocess
import rumps
import AppKit
import objc
from Foundation import NSObject

from .config import (
    load_config,
    save_config,
    load_custom_dictionary,
    CONFIG_DIR,
    CONFIG_FILE,
    ensure_config_dir,
)
from . import __version__
from .i18n import t, set_language, get_language
from .audio import AudioRecorder
from .asr import ASREngine
from .polish import PolishEngine
from .inserter import (
    insert_text,
    replace_selection,
    delete_chars,
    get_last_insert_diagnostic,
    reset_last_insert_diagnostic,
)
from .hotkey import HotkeyListener
from .history import DictationHistory
from .context import get_active_app, get_tone_for_app, get_scene_for_app, get_selected_text
from .commands import process_punctuation_commands, detect_edit_command, detect_action_command
from .status_overlay import StatusOverlay
from .snippets import SnippetLibrary
from .devices import list_input_devices, validate_device
from .plugins import PluginManager
from .streaming import StreamingTranscriber
from .corrections import CorrectionStore
from .applescript import run_osascript
from .permissions import (
    get_permission_status,
    request_missing_permissions,
    refresh_permissions_for_update,
)
from .runtime import BUNDLE_IDENTIFIER, get_running_bundle_path, get_runtime_version
from .runtime import get_bundle_fingerprint

logger = logging.getLogger("speaktype")
APP_VERSION = get_runtime_version(__version__)
PERMISSION_RESTART_PENDING_KEY = "permission_restart_pending_after_refresh"

# The menubar shows a single stable icon. All state feedback
# (recording / transcribing / polishing / done) lives in the unified
# status overlay. Previously we swapped between emoji for each state
# which made the menubar item visibly jump because 🎙 / 🔴 / ⏳ / ⚠️ all
# have different effective metrics.
ICON_IDLE = "\U0001f399"      # 🎙 (studio microphone)
ICON_RECORDING = ICON_IDLE
ICON_PROCESSING = ICON_IDLE
ICON_ERROR = ICON_IDLE


class _MainThreadBridge(NSObject):
    """Bridge for calling UI updates from background threads."""

    def initWithApp_(self, app):
        self = objc.super(_MainThreadBridge, self).init()
        if self is not None:
            self._app = app
            self._status_text = ""
            self._title_text = ""
        return self

    def setStatusTitle_(self, _):
        self._app._status_item.title = self._status_text

    def setAppTitle_(self, _):
        self._app.title = self._title_text

    def triggerSetup_(self, timer):
        """Called by NSTimer to start setup after wizard closes."""
        self._app._do_setup()

    def startLevelMonitor_(self, _):
        self._app._start_level_monitor_main()

    def stopLevelMonitor_(self, _):
        self._app._stop_level_monitor_main()

    def handleMaxDurationReached_(self, _):
        self._app._handle_max_duration_reached_main()

    def showPermissionRestartAlert_(self, _):
        self._app._show_permission_restart_alert_main()


class SpeakTypeApp(rumps.App):
    def __init__(self):
        super().__init__(
            name="SpeakType",
            title=ICON_IDLE,
            quit_button=None,
        )
        self.config = load_config()
        set_language(self.config.get("ui_language", "zh"))
        self._bridge = _MainThreadBridge.alloc().initWithApp_(self)

        # Resolve audio device
        device = validate_device(self.config.get("audio_device"))
        self.recorder = AudioRecorder(
            sample_rate=self.config["sample_rate"],
            device=device,
            whisper_mode_enabled=self.config.get("whisper_mode_enabled", True),
        )
        self.asr = ASREngine(
            model_name=self.config["asr_model"],
            backend="qwen",
            whisper_model="base",
        )
        self.polish_engine = PolishEngine(
            model=self.config["llm_model"],
            ollama_url=self.config["ollama_url"],
        )
        self.history = DictationHistory(max_entries=self.config["history_max_entries"])
        self.snippets = SnippetLibrary()
        self.corrections = CorrectionStore()
        self.hotkey_listener = None
        self._recording_start_time = 0
        self._is_processing = False
        self._setup_done = False
        self._first_launch = not self.config.get("setup_completed", False)
        self._settings_controller = None
        self._stats_controller = None
        self._dict_controller = None

        # Unified status overlay (recording dot + streaming preview + state phases)
        self._status_overlay = StatusOverlay()
        self._level_timer = None
        self._streaming_transcriber = None

        # "Undo last dictation" support — what we inserted on the most
        # recent successful pass, and into which app.
        self._last_insertion_text: str | None = None
        self._last_insertion_app: str | None = None
        self._last_insertion_bundle_id: str | None = None
        self._recording_stop_lock = threading.Lock()
        self._recording_stop_requested = False
        # Track the in-flight processing thread so quit can wait on it.
        self._processing_thread: threading.Thread | None = None
        self._llm_unavailable_notified = False
        self._permission_watch_thread: threading.Thread | None = None
        self._permission_watch_stop = threading.Event()
        self._last_permission_status = None
        self._permission_restart_prompt_shown = False

        # Plugin system
        self._plugin_manager = PluginManager(
            plugins_dir=self.config.get("plugins_dir", "")
        )

        self._status_item = rumps.MenuItem(t("status_init"))

        self._polish_item = rumps.MenuItem(t("menu_polish"), callback=self._toggle_polish)
        self._polish_item.state = self.config["polish_enabled"]
        self._voice_cmd_item = rumps.MenuItem(t("menu_voice_cmd"), callback=self._toggle_voice_commands)
        self._voice_cmd_item.state = self.config["voice_commands_enabled"]
        self._tone_item = rumps.MenuItem(t("menu_context_tone"), callback=self._toggle_context_tone)
        self._tone_item.state = self.config["context_aware_tone"]

        # Translation toggle + target language submenu
        self._translate_item = rumps.MenuItem(t("menu_translate"), callback=self._toggle_translate)
        self._translate_item.state = self.config.get("translate_enabled", False)

        self._translate_menu = rumps.MenuItem(t("menu_translate_to"))
        translate_langs = [
            ("en", "English"),
            ("zh", "中文"),
            ("ja", "日本語"),
            ("ko", "한국어"),
            ("es", "Español"),
            ("fr", "Français"),
            ("de", "Deutsch"),
        ]
        for code, name in translate_langs:
            item = rumps.MenuItem(name, callback=self._make_translate_target_callback(code))
            item.state = self.config.get("translate_target", "en") == code
            self._translate_menu.add(item)

        # Dictation mode submenu
        self._mode_menu = rumps.MenuItem(t("menu_dictation_mode"))
        self._mode_items = {}
        for mode_id, mode_key in [("push_to_talk", "mode_push_to_talk"), ("toggle", "mode_toggle")]:
            item = rumps.MenuItem(t(mode_key), callback=self._make_mode_callback(mode_id))
            item.state = self.config.get("dictation_mode", "push_to_talk") == mode_id
            self._mode_menu.add(item)
            self._mode_items[mode_id] = (item, mode_key)

        # Dictation language quick-switch submenu
        self._lang_menu = rumps.MenuItem(t("menu_dictation_lang"))
        self._lang_auto_item = rumps.MenuItem(t("lang_auto"), callback=self._make_lang_callback("auto"))
        self._lang_auto_item.state = self.config["language"] == "auto"
        self._lang_menu.add(self._lang_auto_item)
        for code, name in [("en", "English"), ("zh", "中文"), ("ja", "日本語"), ("ko", "한국어")]:
            item = rumps.MenuItem(name, callback=self._make_lang_callback(code))
            item.state = self.config["language"] == code
            self._lang_menu.add(item)

        # Audio device submenu
        self._device_menu = rumps.MenuItem(t("menu_audio_device"))
        self._device_default_item = rumps.MenuItem(t("device_default"), callback=self._make_device_callback(None))
        self._device_default_item.state = self.config.get("audio_device") is None
        self._device_menu.add(self._device_default_item)
        for dev in list_input_devices():
            dev_item = rumps.MenuItem(dev["name"], callback=self._make_device_callback(dev["name"]))
            dev_item.state = self.config.get("audio_device") == dev["name"]
            self._device_menu.add(dev_item)

        # UI Language submenu
        self._ui_lang_menu = rumps.MenuItem(t("menu_ui_language"))
        self._ui_lang_items = {}
        for lang_code, lang_key in [("zh", "ui_lang_zh"), ("en", "ui_lang_en")]:
            item = rumps.MenuItem(t(lang_key), callback=self._make_ui_lang_callback(lang_code))
            item.state = self.config.get("ui_language", "zh") == lang_code
            self._ui_lang_menu.add(item)
            self._ui_lang_items[lang_code] = (item, lang_key)

        self._hotkey_item = rumps.MenuItem(t("hotkey_prefix") + self._hotkey_display())

        self._prefs_item = rumps.MenuItem(t("menu_preferences"), callback=self._open_settings, key=",")
        self._dict_item = rumps.MenuItem(t("menu_dict_snippets"), callback=self._open_dict)
        self._stats_item = rumps.MenuItem(t("menu_history_stats"), callback=self._show_stats)
        self._mic_item = rumps.MenuItem(t("menu_test_mic"), callback=self._test_mic)
        self._config_item = rumps.MenuItem(t("menu_open_config"), callback=self._open_config)
        self._updates_item = rumps.MenuItem(t("menu_check_updates"), callback=self._check_updates)
        self._about_item = rumps.MenuItem(t("menu_about"), callback=self._show_about)
        self._quit_item = rumps.MenuItem(t("menu_quit"), callback=self._quit, key="q")

        self.menu = [
            rumps.MenuItem(f"SpeakType v{APP_VERSION}"),
            None,
            self._hotkey_item,
            self._status_item,
            None,
            self._polish_item,
            self._voice_cmd_item,
            self._tone_item,
            self._translate_item,
            self._translate_menu,
            self._mode_menu,
            self._lang_menu,
            self._device_menu,
            self._ui_lang_menu,
            None,
            self._prefs_item,
            self._dict_item,
            self._stats_item,
            self._mic_item,
            None,
            self._config_item,
            self._updates_item,
            self._about_item,
            None,
            self._quit_item,
        ]

    def _refresh_menu_titles(self):
        """Update all menu item titles after UI language change."""
        self._hotkey_item.title = t("hotkey_prefix") + self._hotkey_display()
        self._polish_item.title = t("menu_polish")
        self._voice_cmd_item.title = t("menu_voice_cmd")
        self._tone_item.title = t("menu_context_tone")
        self._translate_item.title = t("menu_translate")
        self._translate_menu.title = t("menu_translate_to")
        self._mode_menu.title = t("menu_dictation_mode")
        for mode_id, (item, key) in self._mode_items.items():
            item.title = t(key)
        self._lang_menu.title = t("menu_dictation_lang")
        self._lang_auto_item.title = t("lang_auto")
        self._device_menu.title = t("menu_audio_device")
        self._device_default_item.title = t("device_default")
        self._ui_lang_menu.title = t("menu_ui_language")
        for lang_code, (item, key) in self._ui_lang_items.items():
            item.title = t(key)
        self._prefs_item.title = t("menu_preferences")
        self._dict_item.title = t("menu_dict_snippets")
        self._stats_item.title = t("menu_history_stats")
        self._mic_item.title = t("menu_test_mic")
        self._config_item.title = t("menu_open_config")
        self._updates_item.title = t("menu_check_updates")
        self._about_item.title = t("menu_about")
        self._quit_item.title = t("menu_quit")

    def _toggle_translate(self, sender):
        sender.state = not sender.state
        self.config["translate_enabled"] = bool(sender.state)
        save_config(self.config)

    def _make_translate_target_callback(self, lang_code):
        def callback(sender):
            self.config["translate_target"] = lang_code
            save_config(self.config)
            if self._translate_menu:
                for item in self._translate_menu.values():
                    item.state = False
                sender.state = True
        return callback

    def _make_lang_callback(self, lang_code):
        def callback(sender):
            self.config["language"] = lang_code
            save_config(self.config)
            if self._lang_menu:
                for item in self._lang_menu.values():
                    item.state = False
                sender.state = True
        return callback

    def _make_mode_callback(self, mode_id):
        def callback(sender):
            self.config["dictation_mode"] = mode_id
            save_config(self.config)
            if self._mode_menu:
                for item in self._mode_menu.values():
                    item.state = False
                sender.state = True
            # Restart hotkey listener with new mode
            self._restart_hotkey_listener()
        return callback

    def _make_device_callback(self, device_name):
        def callback(sender):
            self.config["audio_device"] = device_name
            save_config(self.config)
            if self._device_menu:
                for item in self._device_menu.values():
                    item.state = False
                sender.state = True
            # Update recorder device
            self.recorder.device = validate_device(device_name)
        return callback

    def _make_ui_lang_callback(self, lang_code):
        def callback(sender):
            self.config["ui_language"] = lang_code
            save_config(self.config)
            set_language(lang_code)
            # Update checkmarks
            for lc, (item, _) in self._ui_lang_items.items():
                item.state = lc == lang_code
            # Refresh all menu titles to new language
            self._refresh_menu_titles()
        return callback

    def _hotkey_display(self):
        mapping = {
            "right_cmd": "Right \u2318",
            "left_cmd": "Left \u2318",
            "fn": "Fn",
            "right_alt": "Right \u2325",
            "right_ctrl": "Right \u2303",
            "ctrl+shift+space": "\u2303\u21e7Space",
            "f5": "F5",
            "f6": "F6",
        }
        return mapping.get(self.config["hotkey"], self.config["hotkey"])

    @rumps.timer(1)
    def _startup_timer(self, timer):
        """Run once after app starts to initialize engines."""
        if self._setup_done:
            timer.stop()
            return
        self._setup_done = True
        timer.stop()

        if self._first_launch:
            self._show_setup_wizard()
        else:
            self._check_permissions_and_setup()

    def _show_setup_wizard(self):
        """Show first-launch setup wizard."""
        from .setup_wizard import SetupWizardController
        self._wizard_controller = SetupWizardController(
            config=self.config,
            asr_engine=self.asr,
            on_complete=self._on_wizard_complete,
        )
        self._wizard_controller.show()

    def _check_permissions_and_setup(self):
        """Proceed with setup. Check accessibility after hotkey listener starts."""
        self._do_setup()

    def _on_wizard_complete(self):
        """Called when setup wizard finishes. Relaunch the app for clean startup."""
        import os
        app_path = "/Applications/SpeakType.app"
        if os.path.exists(app_path):
            subprocess.Popen(["open", app_path])
        rumps.quit_application()

    def _set_status(self, text):
        """Thread-safe: update status menu item title from any thread."""
        self._bridge._status_text = text
        self._bridge.performSelectorOnMainThread_withObject_waitUntilDone_(
            b"setStatusTitle:", None, False
        )

    def _set_title(self, text):
        """Thread-safe: update menubar icon title from any thread."""
        self._bridge._title_text = text
        self._bridge.performSelectorOnMainThread_withObject_waitUntilDone_(
            b"setAppTitle:", None, False
        )

    def _build_streaming_transcriber(self):
        return StreamingTranscriber(
            self.asr,
            on_partial_text=self._status_overlay.update_partial_text,
            sample_rate=self.config["sample_rate"],
        )

    def _start_streaming_preview(self) -> bool:
        if self._streaming_transcriber is not None or not self.recorder.is_recording:
            return False
        try:
            streamer = self._build_streaming_transcriber()
            self.recorder.set_stream_callback(streamer.feed_audio)
            streamer.start(language=self.config["language"])
            self._streaming_transcriber = streamer
            return True
        except Exception as e:
            logger.debug(f"Streaming preview failed to start: {e}")
            self._streaming_transcriber = None
            self.recorder.set_stream_callback(None)
            return False

    def _late_start_streaming_preview(self):
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline:
            if not self.recorder.is_recording or self._streaming_transcriber is not None:
                return
            if getattr(self.asr, "_loaded", False):
                self._start_streaming_preview()
                return
            time.sleep(0.05)

    def _prime_pipeline_for_recording(self):
        if not getattr(self.asr, "_loaded", False):
            if hasattr(self.asr, "load_async"):
                self.asr.load_async()
            else:
                threading.Thread(target=self.asr.load, daemon=True).start()

        if self.config.get("streaming_preview", True) and not getattr(self.asr, "_loaded", False):
            threading.Thread(target=self._late_start_streaming_preview, daemon=True).start()

        if self.config.get("polish_enabled") or self.config.get("translate_enabled", False):
            if hasattr(self.polish_engine, "prewarm_async"):
                self.polish_engine.prewarm_async()

    def _log_pipeline_latency(self, marks: dict[str, float]):
        start = marks.get("start")
        end = marks.get("end")
        if start is None or end is None:
            return

        def _delta(a: str, b: str) -> float:
            if a not in marks or b not in marks:
                return 0.0
            return max(0.0, marks[b] - marks[a])

        logger.info(
            "Latency: total=%.3fs transcribe=%.3fs polish=%.3fs translate=%.3fs insert=%.3fs history_enqueue=%.3fs",
            end - start,
            _delta("start", "transcribed"),
            _delta("transcribed", "polished"),
            _delta("polished", "translated"),
            _delta("translated", "inserted"),
            _delta("inserted", "history_enqueued"),
        )

    def _llm_unavailable_kind(self, error: str | None = None) -> str:
        error_text = (error or getattr(self.polish_engine, "last_error", "") or "").lower()
        if (
            "not running" in error_text
            or "connection" in error_text
            or "connection refused" in error_text
            or "failed to establish" in error_text
        ):
            return "not_running"
        if (
            "no ollama llm model" in error_text
            or "model not found" in error_text
            or "available models" in error_text
        ):
            return "model_missing"
        if "timed out" in error_text or "timeout" in error_text:
            return "timeout"
        if "returned status" in error_text:
            return "unhealthy"
        return "generic"

    def _llm_model_name_for_notice(self) -> str:
        return getattr(self.polish_engine, "model", None) or self.config.get("llm_model", "")

    def _llm_unavailable_notification_body(self, error: str | None = None) -> str:
        model = self._llm_model_name_for_notice()
        url = self.config.get("ollama_url", "http://localhost:11434")
        kind = self._llm_unavailable_kind(error)
        if kind == "not_running":
            return t("notif_llm_ollama_not_running_body", model=model)
        if kind == "model_missing":
            return t("notif_llm_model_missing_body", model=model)
        if kind == "timeout":
            return t("notif_llm_ollama_timeout_body", model=model, url=url)
        if kind == "unhealthy":
            return t("notif_llm_ollama_unhealthy_body", model=model, url=url)
        return t("notif_llm_unavail_body", model=model)

    def _llm_fallback_overlay_text(self, error: str | None = None) -> str:
        model = self._llm_model_name_for_notice()
        kind = self._llm_unavailable_kind(error)
        if kind == "not_running":
            return t("overlay_llm_ollama_not_running_raw")
        if kind == "model_missing":
            return t("overlay_llm_model_missing_raw", model=model)
        if kind == "timeout":
            return t("overlay_llm_ollama_timeout_raw")
        if kind == "unhealthy":
            return t("overlay_llm_ollama_unhealthy_raw")
        return t("overlay_llm_skipped_raw")

    def _notify_llm_unavailable_once(self, error: str | None = None):
        """Warn once when local polishing/translation falls back to raw text."""
        if getattr(self, "_llm_unavailable_notified", False):
            return
        self._llm_unavailable_notified = True
        rumps.notification(
            "SpeakType",
            t("notif_llm_unavail_title"),
            self._llm_unavailable_notification_body(error),
        )

    def _show_overlay_transcribing(self, text: str = ""):
        if not hasattr(self._status_overlay, "show_transcribing"):
            if text and hasattr(self._status_overlay, "update_partial_text"):
                self._status_overlay.update_partial_text(text)
            return
        try:
            self._status_overlay.show_transcribing(text)
        except TypeError:
            self._status_overlay.show_transcribing()
            if text and hasattr(self._status_overlay, "update_partial_text"):
                self._status_overlay.update_partial_text(text)

    def _show_overlay_done(self, text: str = "", auto_hide_after: float = 0.6):
        if not hasattr(self._status_overlay, "show_done"):
            return
        try:
            self._status_overlay.show_done(text, auto_hide_after=auto_hide_after)
        except TypeError:
            self._status_overlay.show_done(text)

    def _show_overlay_notice(self, text: str = "", auto_hide_after: float = 2.0):
        if hasattr(self._status_overlay, "show_notice"):
            try:
                self._status_overlay.show_notice(text, auto_hide_after=auto_hide_after)
                return
            except TypeError:
                self._status_overlay.show_notice(text)
                return
        self._show_overlay_done(text, auto_hide_after=auto_hide_after)

    def _show_overlay_error(self, text: str = "", auto_hide_after: float = 3.0):
        if not hasattr(self._status_overlay, "show_error"):
            self._show_overlay_done(text, auto_hide_after=auto_hide_after)
            return
        try:
            self._status_overlay.show_error(text, auto_hide_after=auto_hide_after)
        except TypeError:
            self._status_overlay.show_error(text)

    def _observe_llm_status(self) -> bool:
        error = getattr(self.polish_engine, "last_error", "")
        if error:
            logger.warning(
                "Local LLM post-processing fallback: polish/translation skipped for this dictation; raw or partially processed text will be inserted. reason=%s",
                error,
            )
            self._notify_llm_unavailable_once(error)
            return True
        else:
            self._llm_unavailable_notified = False
            return False

    def _insert_failure_hint(self, diagnostic=None) -> str:
        reason = getattr(diagnostic, "reason", "") if diagnostic is not None else ""
        if reason == "post_event_denied":
            return t("insert_hint_post_event")
        if reason in {"paste_verification_failed", "keystroke_no_ax_change", "accessibility_false_success"}:
            return t("insert_hint_not_writable")
        if reason == "no_focused_element":
            return t("insert_hint_focus")
        return t("insert_hint_generic")

    def _notify_insert_failed(self, app_info: dict | None = None):
        app_name = (app_info or {}).get("name") or "Unknown"
        diagnostic = get_last_insert_diagnostic()
        hint = self._insert_failure_hint(diagnostic)
        logger.error(
            "Text insertion failed for %s (method=%s reason=%s detail=%s)",
            app_name,
            getattr(diagnostic, "method", "unknown"),
            getattr(diagnostic, "reason", "unknown"),
            getattr(diagnostic, "detail", ""),
        )
        self._show_overlay_error(
            t("overlay_insert_failed", app=app_name),
            auto_hide_after=3.0,
        )
        rumps.notification(
            "SpeakType",
            t("notif_insert_failed_title"),
            t("notif_insert_failed_body", app=app_name, hint=hint),
        )

    def _show_successful_insert_feedback(
        self,
        app_info: dict | None,
        inserted_text: str,
        llm_fallback_used: bool = False,
    ):
        app_name = (app_info or {}).get("name") or "Unknown"
        diagnostic = get_last_insert_diagnostic()
        unverified = bool(diagnostic and diagnostic.success and not diagnostic.verified)
        if unverified and llm_fallback_used:
            logger.warning(
                "Text sent to %s but insertion could not be verified; LLM polish/translation was also skipped (method=%s reason=%s)",
                app_name,
                diagnostic.method,
                diagnostic.reason,
            )
            self._show_overlay_notice(
                t("overlay_insert_unverified_llm_skipped", app=app_name),
                auto_hide_after=2.4,
            )
            return
        if unverified:
            logger.warning(
                "Text sent to %s but insertion could not be verified (method=%s reason=%s)",
                app_name,
                diagnostic.method,
                diagnostic.reason,
            )
            self._show_overlay_notice(
                t("overlay_insert_unverified", app=app_name),
                auto_hide_after=2.2,
            )
            return
        if llm_fallback_used:
            self._show_overlay_notice(
                self._llm_fallback_overlay_text(),
                auto_hide_after=2.2,
            )

    def _do_setup(self):
        def init_engines():
            logger.info("Loading ASR engine...")
            self._set_status(t("status_loading_asr"))

            def _asr_progress(pct, status):
                self._set_status(t("status_downloading_asr", pct=pct, size=status))

            try:
                self.asr.load(progress_callback=_asr_progress)
                logger.info(f"ASR engine loaded: {self.asr.get_backend_info()}")
            except Exception as e:
                logger.error(f"ASR load failed: {e}")
                self._set_status(t("status_asr_error"))
                self._set_title(ICON_ERROR)
                rumps.notification("SpeakType", t("notif_asr_failed"), str(e))
                return

            if self.config["polish_enabled"] or self.config.get("translate_enabled", False):
                if self.polish_engine.check_available():
                    logger.info("LLM polish engine available")
                    self._llm_unavailable_notified = False
                    self.polish_engine.prewarm_async()
                else:
                    logger.warning("LLM not available")
                    self._notify_llm_unavailable_once()

            # Load plugins
            if self.config.get("plugins_enabled", False):
                try:
                    self._plugin_manager.reload_all()
                except Exception as e:
                    logger.warning(f"Plugin loading failed: {e}")

            self._set_status(t("status_ready"))
            self._set_title(ICON_IDLE)
            mode_str = t("notif_ready_mode_toggle") if self.config.get("dictation_mode") == "toggle" else t("notif_ready_mode_hold")
            rumps.notification("SpeakType", t("notif_ready_title"), t("notif_ready_body", mode_str=mode_str, hotkey=self._hotkey_display()))

        threading.Thread(target=init_engines, daemon=True).start()
        self._restart_hotkey_listener()
        self._start_permission_restart_watcher()

        # Delayed accessibility check — warn if pynput can't listen
        def _delayed_perm_check():
            import time
            time.sleep(5)
            if self.hotkey_listener and not self.hotkey_listener.is_running:
                logger.warning(
                    "Hotkey listener backend is not running (backend=%s) — accessibility may be missing",
                    self.hotkey_listener.backend_name,
                )
                rumps.notification(
                    "SpeakType",
                    t("notif_perm_missing_title"),
                    t("notif_perm_missing_body", missing=t("wizard_access_label")),
                )
        threading.Thread(target=_delayed_perm_check, daemon=True).start()

    def _start_permission_restart_watcher(self):
        """Prompt for restart if macOS grants input permissions while running."""
        if self._permission_watch_thread is not None and self._permission_watch_thread.is_alive():
            return
        try:
            status = get_permission_status()
        except Exception as e:
            logger.debug(f"Permission watcher could not read initial status: {e}")
            return

        self._last_permission_status = status
        if status.all_granted:
            if self.config.get(PERMISSION_RESTART_PENDING_KEY):
                self._prompt_for_permission_restart(
                    "Input permissions already granted after permission refresh"
                )
            return

        self._permission_watch_stop.clear()
        self._permission_watch_thread = threading.Thread(
            target=self._permission_restart_watch_loop,
            daemon=True,
            name="SpeakTypePermissionWatcher",
        )
        self._permission_watch_thread.start()

    def _permission_restart_watch_loop(self):
        while not self._permission_watch_stop.wait(2.0):
            try:
                current = get_permission_status()
            except Exception as e:
                logger.debug(f"Permission watcher read failed: {e}")
                continue

            previous = self._last_permission_status
            self._last_permission_status = current
            if (
                (
                    _permission_status_transitioned_to_granted(previous, current)
                    or (
                        self.config.get(PERMISSION_RESTART_PENDING_KEY)
                        and _permission_status_has_new_grant(previous, current)
                    )
                )
                and not self._permission_restart_prompt_shown
            ):
                self._prompt_for_permission_restart(
                    "Input permissions changed while SpeakType is running"
                )
                return

    def _prompt_for_permission_restart(self, reason: str):
        if self._permission_restart_prompt_shown:
            return
        logger.info("%s; restart required", reason)
        self._permission_restart_prompt_shown = True
        self._permission_watch_stop.set()
        if self.config.get(PERMISSION_RESTART_PENDING_KEY):
            self.config[PERMISSION_RESTART_PENDING_KEY] = False
            save_config(self.config)
        self._bridge.performSelectorOnMainThread_withObject_waitUntilDone_(
            b"showPermissionRestartAlert:", None, False
        )

    def _show_permission_restart_alert_main(self):
        alert = AppKit.NSAlert.alloc().init()
        alert.setMessageText_(t("perm_restart_title"))
        alert.setInformativeText_(t("perm_restart_body"))
        alert.setAlertStyle_(AppKit.NSAlertStyleInformational)
        alert.addButtonWithTitle_(t("perm_restart_now"))
        alert.addButtonWithTitle_(t("perm_restart_later"))
        response = alert.runModal()
        if response == AppKit.NSAlertFirstButtonReturn:
            self._relaunch_app()

    def _relaunch_app(self):
        app_path = get_running_bundle_path() or "/Applications/SpeakType.app"
        try:
            subprocess.Popen(
                ["/bin/sh", "-c", 'sleep 0.4; open "$1"', "speaktype-restart", app_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            logger.warning(f"Failed to schedule app relaunch: {e}")
        self._quit(None)

    def _restart_hotkey_listener(self):
        """(Re)start the hotkey listener with current config."""
        if self.hotkey_listener:
            self.hotkey_listener.stop()

        mode = self.config.get("dictation_mode", "push_to_talk")

        if mode == "toggle":
            self.hotkey_listener = HotkeyListener(
                hotkey_name=self.config["hotkey"],
                mode="toggle",
                on_toggle=self._on_toggle,
            )
        else:
            self.hotkey_listener = HotkeyListener(
                hotkey_name=self.config["hotkey"],
                mode="push_to_talk",
                on_press=self._on_hotkey_press,
                on_release=self._on_hotkey_release,
            )

        self.hotkey_listener.start()
        logger.info("Hotkey backend active: %s", self.hotkey_listener.backend_name)

    # --- Push-to-talk handlers ---

    def _on_hotkey_press(self):
        if self._is_processing:
            return
        self._start_recording()

    def _on_hotkey_release(self):
        if not self.recorder.is_recording:
            return
        self._stop_recording()

    # --- Toggle mode handler ---

    def _on_toggle(self, is_active: bool):
        if is_active:
            if self._is_processing:
                return
            self._start_recording()
        else:
            if self.recorder.is_recording:
                self._stop_recording()

    # --- Common recording logic ---

    def _start_recording(self):
        streamer = None
        self.recorder.set_whisper_state_callback(self._on_whisper_state_change)

        if self.config.get("streaming_preview", True) and self.asr._loaded:
            streamer = self._build_streaming_transcriber()
        else:
            self.recorder.set_stream_callback(None)

        max_seconds = self.config.get("max_recording_seconds")
        try:
            max_seconds = float(max_seconds) if max_seconds else None
            if max_seconds is not None and max_seconds <= 0:
                max_seconds = None
        except (TypeError, ValueError):
            max_seconds = None

        # Set this before opening PortAudio. AudioRecorder marks itself as
        # recording while opening the stream, so a fast hotkey release can race
        # into _stop_recording before recorder.start() returns.
        self._recording_start_time = time.time()

        try:
            started = self.recorder.start(
                max_seconds=max_seconds,
                on_max_duration=self._on_max_duration_reached,
            )
        except Exception as e:
            started = False
            logger.error(f"Recorder start raised: {e}")

        if not started:
            self.recorder.set_stream_callback(None)
            self.recorder.set_whisper_state_callback(None)
            self._streaming_transcriber = None
            with self._recording_stop_lock:
                self._recording_stop_requested = False
            self._recording_start_time = 0
            err = getattr(self.recorder, "last_start_error", None)
            message = str(err) if err else "Could not open microphone."
            logger.error(f"Recording failed to start: {message}")
            self._show_overlay_error(t("overlay_mic_start_failed"), auto_hide_after=3.0)
            rumps.notification("SpeakType", t("notif_error"), message)
            return

        with self._recording_stop_lock:
            self._recording_stop_requested = False

        logger.info("Recording started")
        if self.config["sound_feedback"]:
            _play_sound("Tink")

        if self.config.get("plugins_enabled"):
            self._plugin_manager.run_hook("on_recording_start")

        self._prime_pipeline_for_recording()
        self._status_overlay.show_recording()
        self._start_level_monitor()

        if streamer is not None:
            try:
                self.recorder.set_stream_callback(streamer.feed_audio)
                streamer.start(language=self.config["language"])
                self._streaming_transcriber = streamer
            except Exception as e:
                logger.debug(f"Streaming preview failed to start: {e}")
                self._streaming_transcriber = None
                self.recorder.set_stream_callback(None)
        else:
            self._streaming_transcriber = None

    def _on_whisper_state_change(self, new_state: str):
        """Forward whisper detector state into the overlay (any thread)."""
        try:
            self._status_overlay.set_whisper_mode(new_state == "whisper")
        except Exception as e:
            logger.debug(f"Failed to update overlay whisper indicator: {e}")

    def _on_max_duration_reached(self):
        """Audio thread fired the watchdog — bounce the stop onto the main thread."""
        logger.info("max_recording_seconds reached; auto-stopping")
        try:
            self._bridge.performSelectorOnMainThread_withObject_waitUntilDone_(
                b"handleMaxDurationReached:", None, False
            )
        except Exception as e:
            logger.debug(f"max_duration main-thread dispatch failed: {e}")

    def _handle_max_duration_reached_main(self):
        try:
            if self.hotkey_listener and self.hotkey_listener.mode == "toggle":
                if self.hotkey_listener._toggle_active:
                    self.hotkey_listener._toggle_active = False
            self._stop_recording()
        except Exception as e:
            logger.debug(f"max_duration auto-stop failed: {e}")

    def _stop_recording(self):
        with self._recording_stop_lock:
            if self._recording_stop_requested or not self.recorder.is_recording:
                return
            self._recording_stop_requested = True

        start_time = self._recording_start_time or time.time()
        duration = max(0.0, time.time() - start_time)
        logger.info(f"Recording stopped after {duration:.1f}s")
        if self.config["sound_feedback"]:
            _play_sound("Pop")
        self._is_processing = True

        # Notify plugins
        if self.config.get("plugins_enabled"):
            self._plugin_manager.run_hook("on_recording_stop")

        # Stop the level monitor and any streaming transcription
        self._stop_level_monitor()
        preview_text = ""
        if self._streaming_transcriber:
            preview_text = self._streaming_transcriber.stop(wait=False) or ""
            self._streaming_transcriber = None
        self.recorder.set_stream_callback(None)

        # Move the overlay into transcribing state while we wait on ASR
        if hasattr(self.asr, "_loaded") and not getattr(self.asr, "_loaded", False):
            logger.info("ASR model is still loading; showing cold-start transcription status")
            self._show_overlay_transcribing(t("overlay_asr_loading"))
        elif preview_text:
            self._show_overlay_transcribing(t("overlay_finalizing_preview"))
        else:
            self._show_overlay_transcribing()

        can_use_in_memory_audio = (
            getattr(self.asr, "backend", "qwen") == "qwen"
            and not self.config.get("plugins_enabled")
            and hasattr(self.recorder, "stop_audio")
        )
        audio_input = self.recorder.stop_audio() if can_use_in_memory_audio else self.recorder.stop()
        if audio_input is None:
            reason = getattr(self.recorder, "last_stop_reason", "") or "unknown"
            message = getattr(self.recorder, "last_stop_message", "") or ""
            logger.info("No usable audio captured (reason=%s message=%s duration=%.2fs)", reason, message, duration)
            self._is_processing = False
            overlay_key = {
                "too_short": "overlay_audio_too_short",
                "too_quiet": "overlay_audio_too_quiet",
                "no_frames": "overlay_no_audio",
                "not_recording": "overlay_no_audio",
            }.get(reason, "overlay_no_audio")
            self._show_overlay_error(t(overlay_key), auto_hide_after=2.0)
            return

        self._processing_thread = threading.Thread(
            target=self._process_audio,
            args=(audio_input, duration),
            daemon=True,
        )
        self._processing_thread.start()

    def _start_level_monitor(self):
        try:
            self._bridge.performSelectorOnMainThread_withObject_waitUntilDone_(
                b"startLevelMonitor:", None, True
            )
        except Exception as e:
            logger.debug(f"Failed to dispatch level monitor start: {e}")
            self._level_timer = None

    def _start_level_monitor_main(self):
        """Poll the recorder's audio level and feed it into the overlay."""
        if self._level_timer is not None:
            try:
                self._level_timer.stop()
            except Exception:
                pass
            self._level_timer = None
        try:
            self._level_timer = rumps.Timer(self._poll_audio_level, 0.08)
            self._level_timer.start()
        except Exception as e:
            logger.debug(f"Failed to start level monitor: {e}")
            self._level_timer = None

    def _stop_level_monitor(self):
        try:
            self._bridge.performSelectorOnMainThread_withObject_waitUntilDone_(
                b"stopLevelMonitor:", None, True
            )
        except Exception as e:
            logger.debug(f"Failed to dispatch level monitor stop: {e}")
        try:
            self._status_overlay.update_audio_level(0.0)
        except Exception:
            pass

    def _stop_level_monitor_main(self):
        if self._level_timer is not None:
            try:
                self._level_timer.stop()
            except Exception:
                pass
            self._level_timer = None

    def _poll_audio_level(self, sender):
        if not self.recorder.is_recording:
            try:
                sender.stop()
            except Exception:
                pass
            self._level_timer = None
            return
        try:
            level = self.recorder.get_level()
        except Exception:
            level = 0.0
        self._status_overlay.update_audio_level(level)

    def _process_audio(self, audio_input, duration: float):
        marks = {"start": time.perf_counter()}
        llm_fallback_used = False
        try:
            app_info = get_active_app()
            tone = get_tone_for_app(app_info) if self.config["context_aware_tone"] else "neutral"

            # Plugin: pre_transcribe
            if self.config.get("plugins_enabled"):
                audio_input = self._plugin_manager.run_hook("pre_transcribe", audio_input) or audio_input

            logger.info("Transcribing...")
            if hasattr(self.asr, "_loaded") and not getattr(self.asr, "_loaded", False):
                self._show_overlay_transcribing(t("overlay_asr_loading"))
            raw_text = self.asr.transcribe(audio_input, language=self.config["language"])
            marks["transcribed"] = time.perf_counter()

            if not raw_text.strip():
                logger.info("Empty transcription")
                self._show_overlay_error(t("overlay_empty_transcription"), auto_hide_after=1.8)
                return

            logger.info(f"Raw: {raw_text}")

            # Plugin: post_transcribe
            if self.config.get("plugins_enabled"):
                raw_text = self._plugin_manager.run_hook("post_transcribe", raw_text) or raw_text

            # Apply user-defined corrections (e.g. "PI thon" -> "Python")
            try:
                raw_text = self.corrections.apply(raw_text)
            except Exception as e:
                logger.debug(f"Correction store apply failed: {e}")

            # Local action commands (undo last dictation, etc.)
            if self.config["voice_commands_enabled"]:
                action = detect_action_command(raw_text)
                if action == "undo_last":
                    if self._handle_undo_last():
                        self._status_overlay.show_done("\u21b6")  # ↶ undo glyph
                    else:
                        self._status_overlay.hide(delay=0.4)
                    return

            # Check for snippet triggers
            snippet_text = self.snippets.match(raw_text)
            if snippet_text:
                logger.info(f"Snippet matched: {raw_text} -> {snippet_text[:40]}")
                self._status_overlay.show_done(snippet_text)
                reset_last_insert_diagnostic()
                inserted_ok = insert_text(
                    snippet_text,
                    method=self.config["insert_method"],
                    app_name=app_info.get("name", ""),
                    bundle_id=app_info.get("bundle_id", ""),
                )
                if not inserted_ok:
                    self._notify_insert_failed(app_info)
                    return
                self._show_successful_insert_feedback(app_info, snippet_text)
                self._remember_last_insertion(snippet_text, app_info)
                return

            # Check for edit commands
            if self.config["voice_commands_enabled"]:
                is_edit, command = detect_edit_command(raw_text)
                if is_edit:
                    self._status_overlay.show_polishing(raw_text)
                    if self._handle_edit_command(command, tone, app_info):
                        self._status_overlay.show_done(command)
                    else:
                        self._status_overlay.hide(delay=0.4)
                    return

            # Process punctuation commands
            text = process_punctuation_commands(raw_text) if self.config["voice_commands_enabled"] else raw_text

            # Plugin: pre_polish
            if self.config.get("plugins_enabled"):
                result = self._plugin_manager.run_hook("pre_polish", text, tone)
                if isinstance(result, tuple) and len(result) == 2:
                    text, tone = result
                elif isinstance(result, str):
                    text = result

            combined_llm_path = self.config["polish_enabled"] and self.config.get("translate_enabled", False) and not self.config.get("plugins_enabled")

            # Polish with LLM
            if combined_llm_path:
                self._status_overlay.show_polishing(text)
                target = self.config.get("translate_target", "en")
                logger.info("Polishing and translating to %s...", target)
                scene_id = None
                scene_template = None
                if self.config.get("scene_prompts_enabled", True):
                    scene_id = get_scene_for_app(app_info)
                    overrides = self.config.get("scene_prompts") or {}
                    scene_template = overrides.get(scene_id) if isinstance(overrides, dict) else None
                polished = self.polish_engine.polish_and_translate(
                    text,
                    tone=tone,
                    target_lang=target,
                    auto_punctuation=self.config.get("auto_punctuation", True),
                    filler_removal=self.config.get("filler_removal", True),
                    scene=scene_id,
                    scene_template=scene_template,
                )
                llm_fallback_used = self._observe_llm_status() or llm_fallback_used
                marks["polished"] = time.perf_counter()
                marks["translated"] = marks["polished"]
            else:
                if self.config["polish_enabled"]:
                    self._status_overlay.show_polishing(text)
                    logger.info("Polishing text...")
                    scene_id = None
                    scene_template = None
                    if self.config.get("scene_prompts_enabled", True):
                        scene_id = get_scene_for_app(app_info)
                        overrides = self.config.get("scene_prompts") or {}
                        scene_template = overrides.get(scene_id) if isinstance(overrides, dict) else None
                    polished = self.polish_engine.polish(
                        text,
                        tone=tone,
                        language=self.config["language"],
                        auto_punctuation=self.config.get("auto_punctuation", True),
                        filler_removal=self.config.get("filler_removal", True),
                        scene=scene_id,
                        scene_template=scene_template,
                    )
                    llm_fallback_used = self._observe_llm_status() or llm_fallback_used
                else:
                    polished = text
                marks["polished"] = time.perf_counter()

                # Plugin: post_polish
                if self.config.get("plugins_enabled"):
                    polished = self._plugin_manager.run_hook("post_polish", polished) or polished

                # Translate if enabled
                if self.config.get("translate_enabled", False):
                    target = self.config.get("translate_target", "en")
                    self._status_overlay.show_polishing(polished)
                    logger.info(f"Translating to {target}...")
                    polished = self.polish_engine.translate(polished, target_lang=target)
                    llm_fallback_used = self._observe_llm_status() or llm_fallback_used
                marks["translated"] = time.perf_counter()

            logger.info(f"Final: {polished}")

            # Plugin: pre_insert
            if self.config.get("plugins_enabled"):
                polished = self._plugin_manager.run_hook("pre_insert", polished)
                if polished is None:
                    self._status_overlay.hide(delay=0.4)
                    return

            # Show the final text in the overlay before inserting
            self._status_overlay.show_done(polished)

            # Insert text at cursor
            logger.info(
                "Inserting text via %s into %s",
                self.config["insert_method"],
                app_info.get("name", "Unknown"),
            )
            reset_last_insert_diagnostic()
            inserted_ok = insert_text(
                polished,
                method=self.config["insert_method"],
                app_name=app_info.get("name", ""),
                bundle_id=app_info.get("bundle_id", ""),
            )
            if not inserted_ok:
                self._notify_insert_failed(app_info)
                return
            marks["inserted"] = time.perf_counter()
            self._show_successful_insert_feedback(app_info, polished, llm_fallback_used)
            self._remember_last_insertion(polished, app_info)

            # Plugin: post_insert
            if self.config.get("plugins_enabled"):
                self._plugin_manager.run_hook("post_insert", polished)

            # Save history
            if self.config["history_enabled"]:
                self.history.add_async(
                    raw_text=raw_text,
                    polished_text=polished,
                    app_name=app_info.get("name", ""),
                    duration_sec=duration,
                )
            marks["history_enqueued"] = time.perf_counter()
        except Exception as e:
            logger.error(f"Processing failed: {e}")
            self._show_overlay_error(t("overlay_processing_failed"), auto_hide_after=3.0)
            rumps.notification("SpeakType", t("notif_error"), str(e))
        finally:
            marks["end"] = time.perf_counter()
            self._log_pipeline_latency(marks)
            self._is_processing = False

    def _remember_last_insertion(self, text: str, app_info: dict | None = None):
        self._last_insertion_text = text or None
        self._last_insertion_app = (app_info or {}).get("name", "") or None
        self._last_insertion_bundle_id = (app_info or {}).get("bundle_id", "") or None

    def _clear_last_insertion(self):
        self._last_insertion_text = None
        self._last_insertion_app = None
        self._last_insertion_bundle_id = None

    def _handle_undo_last(self) -> bool:
        """Voice "undo that" — delete the most recently inserted text."""
        if not self._last_insertion_text:
            logger.info("Undo requested but no prior insertion is recorded")
            if self.config["sound_feedback"]:
                _play_sound("Basso")
            return False

        current_app = get_active_app()
        current_bundle_id = current_app.get("bundle_id", "")
        current_app_name = current_app.get("name", "")
        if (
            self._last_insertion_bundle_id
            and current_bundle_id
            and self._last_insertion_bundle_id != current_bundle_id
        ):
            logger.info(
                "Undo skipped because focus moved to %s [%s] from %s [%s]",
                current_app_name,
                current_bundle_id,
                self._last_insertion_app,
                self._last_insertion_bundle_id,
            )
            if self.config["sound_feedback"]:
                _play_sound("Basso")
            return False
        if (
            not current_bundle_id
            and self._last_insertion_app
            and current_app_name
            and self._last_insertion_app != current_app_name
        ):
            logger.info(
                "Undo skipped because focus moved to %s from %s",
                current_app_name,
                self._last_insertion_app,
            )
            if self.config["sound_feedback"]:
                _play_sound("Basso")
            return False

        char_count = len(self._last_insertion_text)
        logger.info(f"Undoing last insertion ({char_count} chars)")
        try:
            delete_chars(char_count)
        except Exception as e:
            logger.error(f"Undo delete failed: {e}")
            return False

        self._clear_last_insertion()
        return True

    def _handle_edit_command(self, command: str, tone: str, app_info: dict | None = None) -> bool:
        try:
            selected = get_selected_text()
            if not selected:
                logger.info("No text selected for edit command")
                if self.config["sound_feedback"]:
                    _play_sound("Basso")
                return False
            logger.info(f"Edit command: '{command}' on: '{selected[:50]}...'")
            result = self.polish_engine.edit_text(command, selected, tone)
            self._observe_llm_status()
            replace_selection(result)
            self._remember_last_insertion(result, app_info or get_active_app())
            return True
        except Exception as e:
            logger.error(f"Edit command failed: {e}")
            return False
        finally:
            self._is_processing = False

    def _open_settings(self, _):
        """Open the native Settings window."""
        from .settings_window import SettingsWindowController, is_auto_start_enabled

        config_with_auto = dict(self.config)
        config_with_auto["auto_start"] = is_auto_start_enabled()

        self._settings_controller = SettingsWindowController(
            config=config_with_auto,
            on_save=self._apply_settings,
        )
        self._settings_controller.show()

    def _open_dict(self, _):
        """Open the dictionary, snippets & corrections editor."""
        from .dict_window import DictWindowController
        self._dict_controller = DictWindowController(self.snippets, self.corrections)
        self._dict_controller.show()

    def _apply_settings(self, new_config: dict):
        """Apply new settings from the Settings window."""
        old_hotkey = self.config.get("hotkey")
        old_asr = self.config.get("asr_model")
        old_mode = self.config.get("dictation_mode")
        old_ui_lang = self.config.get("ui_language", "zh")
        old_plugins_enabled = self.config.get("plugins_enabled", False)
        old_plugins_dir = self.config.get("plugins_dir", "")

        self.config.update(new_config)
        save_config(self.config)

        # Update UI language if changed
        new_ui_lang = new_config.get("ui_language", old_ui_lang)
        if new_ui_lang != old_ui_lang:
            set_language(new_ui_lang)
            self._refresh_menu_titles()
            for lc, (item, _) in self._ui_lang_items.items():
                item.state = lc == new_ui_lang
        else:
            self._hotkey_item.title = t("hotkey_prefix") + self._hotkey_display()

        # Restart hotkey listener if hotkey or mode changed
        if (new_config.get("hotkey") != old_hotkey or
                new_config.get("dictation_mode") != old_mode):
            self._restart_hotkey_listener()

        # Reload ASR model if changed
        if new_config.get("asr_model") != old_asr:
            self.asr = ASREngine(
                model_name=self.config["asr_model"],
                backend="qwen",
                whisper_model="base",
            )
            self.asr.load_async()

        # Update polish engine
        self.polish_engine = PolishEngine(
            model=self.config["llm_model"],
            ollama_url=self.config["ollama_url"],
        )
        if self.config.get("polish_enabled") or self.config.get("translate_enabled", False):
            self._llm_unavailable_notified = False
            self.polish_engine.prewarm_async()

        # Update recorder device
        self.recorder.device = validate_device(self.config.get("audio_device"))

        plugins_enabled_changed = self.config.get("plugins_enabled", False) != old_plugins_enabled
        plugins_dir_changed = self.config.get("plugins_dir", "") != old_plugins_dir
        if plugins_dir_changed:
            self._plugin_manager = PluginManager(
                plugins_dir=self.config.get("plugins_dir", "")
            )
        if plugins_enabled_changed or plugins_dir_changed:
            if self.config.get("plugins_enabled", False):
                try:
                    self._plugin_manager.reload_all()
                except Exception as e:
                    logger.warning(f"Plugin reload failed: {e}")
            else:
                self._plugin_manager.clear()

        # Update toggle states directly via instance vars
        self._polish_item.state = self.config["polish_enabled"]
        self._voice_cmd_item.state = self.config["voice_commands_enabled"]
        self._tone_item.state = self.config["context_aware_tone"]

        rumps.notification("SpeakType", t("notif_settings_saved_title"), t("notif_settings_saved_body"))

    def _toggle_polish(self, sender):
        sender.state = not sender.state
        self.config["polish_enabled"] = bool(sender.state)
        save_config(self.config)

    def _toggle_voice_commands(self, sender):
        sender.state = not sender.state
        self.config["voice_commands_enabled"] = bool(sender.state)
        save_config(self.config)

    def _toggle_context_tone(self, sender):
        sender.state = not sender.state
        self.config["context_aware_tone"] = bool(sender.state)
        save_config(self.config)

    def _show_stats(self, _):
        from .stats_window import StatsWindowController
        self._stats_controller = StatsWindowController(self.history)
        self._stats_controller.show()

    def _test_mic(self, _):
        def _do_test():
            if self.recorder.is_recording or self._is_processing:
                rumps.notification("SpeakType", t("notif_mic_test"), t("notif_cannot_test"))
                return
            rumps.notification("SpeakType", t("notif_mic_test"), t("notif_mic_recording"))
            device = validate_device(self.config.get("audio_device"))
            test_recorder = AudioRecorder(
                sample_rate=self.config["sample_rate"],
                device=device,
            )
            test_recorder.start()
            time.sleep(2)
            path = test_recorder.stop()
            if path:
                size = os.path.getsize(path)
                os.unlink(path)
                rumps.notification("SpeakType", t("notif_mic_test"), t("notif_mic_ok", size=size))
            else:
                rumps.notification("SpeakType", t("notif_mic_test"), t("notif_mic_fail"))
        threading.Thread(target=_do_test, daemon=True).start()

    def _reload_config(self, _):
        self.config = load_config()
        rumps.notification("SpeakType", t("notif_config_reloaded"), t("notif_config_reloaded_body"))

    def _open_config(self, _):
        subprocess.run(["open", str(CONFIG_DIR)])

    def _check_updates(self, _):
        def _do_check():
            from .updates import check_for_update

            result = check_for_update(APP_VERSION)
            if result.error and not result.latest_version:
                rumps.notification(
                    "SpeakType",
                    t("notif_update_check_failed_title"),
                    t("notif_update_check_failed_body", error=result.error[:120]),
                )
                return
            if result.has_update:
                rumps.notification(
                    "SpeakType",
                    t("notif_update_available_title"),
                    t(
                        "notif_update_available_body",
                        latest=result.latest_version or "?",
                        current=APP_VERSION,
                    ),
                )
                # Open the release page so the user can grab the .dmg.
                target = result.release_url or result.download_url
                if target:
                    try:
                        subprocess.Popen(["open", target])
                    except Exception as e:
                        logger.debug(f"Failed to open release URL: {e}")
            else:
                rumps.notification(
                    "SpeakType",
                    t("notif_up_to_date_title"),
                    t("notif_up_to_date_body", version=APP_VERSION),
                )

        threading.Thread(target=_do_check, daemon=True).start()

    def _show_about(self, _):
        rumps.notification(
            t("menu_about"),
            t("notif_about_subtitle", version=APP_VERSION),
            f"Backend: {self.asr.get_backend_info()}\n"
            "\u00a9 2025 SpeakType"
        )

    def _quit(self, _):
        self._permission_watch_stop.set()
        if self.hotkey_listener:
            self.hotkey_listener.stop()
        self._stop_level_monitor()
        if self._streaming_transcriber is not None:
            try:
                self._streaming_transcriber.stop()
            except Exception:
                pass
            self._streaming_transcriber = None
        # Wait briefly for any in-flight transcription/polish thread so we
        # don't yank the rug out from under a write the user expects.
        if self._processing_thread is not None and self._processing_thread.is_alive():
            try:
                self._processing_thread.join(timeout=2.0)
            except Exception:
                pass
        try:
            self._status_overlay.hide()
        except Exception:
            pass
        rumps.quit_application()


def _play_sound(name: str):
    try:
        subprocess.Popen(
            ["afplay", f"/System/Library/Sounds/{name}.aiff"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def _check_permissions():
    """Check and prompt for required macOS permissions (non-blocking)."""
    try:
        status = get_permission_status()
        logger.info(
            "Permission status: accessibility=%s listen_event=%s post_event=%s",
            status.accessibility,
            status.listen_event,
            status.post_event,
        )

        issues = []
        if not status.accessibility:
            issues.append(t("perm_name_accessibility"))
        if not status.listen_event:
            issues.append(t("perm_name_input_monitoring"))
        if not status.post_event:
            issues.append(t("perm_name_post_event"))

        if issues:
            request_missing_permissions(status)
            refreshed = get_permission_status()
            logger.info(
                "Permission status after request: accessibility=%s listen_event=%s post_event=%s",
                refreshed.accessibility,
                refreshed.listen_event,
                refreshed.post_event,
            )

        try:
            result = run_osascript(
                'tell application "System Events" to return name of first process whose frontmost is true',
                timeout=3,
            )
            if result.returncode != 0:
                if "Accessibility" not in issues:
                    issues.append("Accessibility")
        except Exception:
            if "Accessibility" not in issues:
                issues.append("Accessibility")

        if issues:
            missing = " / ".join(issues)
            logger.warning(f"Missing permissions: {missing}")
            title = _escape_applescript_text(t("notif_perm_missing_title"))
            body = _escape_applescript_text(t("notif_perm_missing_body", missing=missing))
            subprocess.run([
                "osascript", "-e",
                f'display notification "{body}" with title "{title}"'
            ], capture_output=True)
    except Exception as e:
        logger.warning(f"Permission check failed: {e}")


def _escape_applescript_text(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _permission_status_transitioned_to_granted(previous, current) -> bool:
    if previous is None or current is None:
        return False
    return not previous.all_granted and current.all_granted


def _permission_status_has_new_grant(previous, current) -> bool:
    if previous is None or current is None:
        return False
    fields = ("accessibility", "listen_event", "post_event")
    return any(
        not bool(getattr(previous, field, False))
        and bool(getattr(current, field, False))
        for field in fields
    )


def _refresh_permissions_after_bundle_update(config: dict):
    """Force a permission re-request once per newly installed bundled build."""
    current_version = APP_VERSION
    previous_version = str(config.get("last_seen_version") or "")
    running_bundle = get_running_bundle_path()
    current_fingerprint = get_bundle_fingerprint(running_bundle) if running_bundle else ""
    previous_fingerprint = str(config.get("last_seen_bundle_fingerprint") or "")
    existing_config = CONFIG_FILE.exists()

    if not previous_version and not previous_fingerprint:
        config["last_seen_version"] = current_version
        if current_fingerprint:
            config["last_seen_bundle_fingerprint"] = current_fingerprint
        if running_bundle and existing_config:
            config[PERMISSION_RESTART_PENDING_KEY] = True
            save_config(config)
            logger.info(
                "Existing config has no bundle marker; forcing one-time permission refresh for %s",
                current_version,
            )
            refresh_permissions_for_update(BUNDLE_IDENTIFIER)
            return
        save_config(config)
        logger.info("Recording current bundle for permission refresh tracking: %s", current_version)
        return

    version_changed = previous_version != current_version
    bundle_changed = bool(
        running_bundle
        and current_fingerprint
        and previous_fingerprint
        and previous_fingerprint != current_fingerprint
    )
    missing_fingerprint_for_bundle = bool(running_bundle and current_fingerprint and not previous_fingerprint)

    if not version_changed and not bundle_changed and not missing_fingerprint_for_bundle:
        return

    config["last_seen_version"] = current_version
    if current_fingerprint:
        config["last_seen_bundle_fingerprint"] = current_fingerprint
    if running_bundle:
        config[PERMISSION_RESTART_PENDING_KEY] = True
    save_config(config)

    if not running_bundle:
        logger.info(
            "Detected version change outside bundled app (%s -> %s); skipping permission reset",
            previous_version,
            current_version,
        )
        return

    logger.info(
        "Detected bundled app install/update %s -> %s (bundle_changed=%s); resetting permissions for %s",
        previous_version,
        current_version,
        bundle_changed or missing_fingerprint_for_bundle,
        BUNDLE_IDENTIFIER,
    )
    refresh_permissions_for_update(BUNDLE_IDENTIFIER)


def run():
    # Ensure UTF-8 I/O when launched from py2app (Finder sets ASCII encoding)
    import io
    for _name in ('stdout', 'stderr'):
        _stream = getattr(sys, _name, None)
        if _stream and hasattr(_stream, 'buffer') and getattr(_stream, 'encoding', 'utf-8') != 'utf-8':
            setattr(sys, _name, io.TextIOWrapper(_stream.buffer, encoding='utf-8', errors='replace'))

    log_file = CONFIG_DIR / "speaktype.log"
    ensure_config_dir()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(str(log_file), mode="a", encoding="utf-8"),
        ],
        force=True,
    )

    config = load_config()
    _refresh_permissions_after_bundle_update(config)
    _check_permissions()

    logger.info("Starting SpeakType v%s...", APP_VERSION)
    app = SpeakTypeApp()
    app.run()
