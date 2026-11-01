"""Main SpeakType application - menubar app with push-to-talk voice input."""

import os
import sys
import time
import threading
import logging
import subprocess
from pathlib import Path
from weakref import WeakSet
import rumps
import AppKit
import objc
from Foundation import NSDate, NSObject, NSRunLoop

from .config import (
    load_config,
    save_config,
    load_custom_dictionary,
    CONFIG_DIR,
    CONFIG_FILE,
    ensure_config_dir,
)
from . import __version__
from .i18n import t, set_language, get_language, localized_hotkey_display
from .audio import AudioRecorder
from .asr import ASREngine
from .polish import PolishEngine
from .inserter import (
    insert_text,
    capture_verified_insertion,
    undo_verified_insertion,
    get_last_insert_diagnostic,
    reset_last_insert_diagnostic,
)
from .hotkey import HotkeyListener
from .history import DictationHistory
from .context import get_active_app, get_tone_for_app, get_scene_for_app, get_selected_text
from .delivery_target import capture_target_field, prepare_unchanged_target
from .commands import process_punctuation_commands, detect_edit_command, detect_action_command
from .status_overlay import StatusOverlay
from .snippets import SnippetLibrary
from .devices import list_input_devices, validate_device
from .plugins import PluginManager
from .streaming import StreamingTranscriber
from .corrections import CorrectionStore
from .edit_observer import EditObservation, PostInsertEditObserver
from .hotwords import ActiveHotwordContext, HotwordStore, extract_confident_corrections
from .applescript import run_osascript
from .permissions import (
    get_permission_status,
    microphone_is_authorized,
    request_missing_permissions,
)
from .runtime import BUNDLE_IDENTIFIER, get_running_bundle_path, get_runtime_version
from .runtime import get_bundle_fingerprint
from .window_lifecycle import show_or_create_window_controller as _show_or_create_window_controller

logger = logging.getLogger("speaktype")
APP_VERSION = get_runtime_version(__version__)
PERMISSION_RESTART_PENDING_KEY = "permission_restart_pending_after_refresh"
PREVIEW_REUSE_MAX_UNCOVERED_SECONDS = 0.65
PREVIEW_REUSE_MAX_AGE_SECONDS = 8.0
TAIL_ASR_MIN_UNCOVERED_SECONDS = 0.12
TAIL_ASR_MAX_UNCOVERED_SECONDS = 2.4
TAIL_ASR_PADDING_SECONDS = 0.25
PREVIEW_FINAL_ACCELERATION_ENABLED = False
HOTKEY_RELEASE_GUARD_GRACE_SECONDS = 0.55
HOTKEY_RELEASE_GUARD_INTERVAL_SECONDS = 0.18
HOTKEY_RELEASE_GUARD_MISSES = 2

# The menubar shows a single stable icon. All state feedback
# (recording / transcribing / polishing / done) lives in the unified
# status overlay. Previously we swapped between emoji for each state
# which made the menubar item visibly jump because 🎙 / 🔴 / ⏳ / ⚠️ all
# have different effective metrics.
ICON_IDLE = "\U0001f399"      # 🎙 (studio microphone)
ICON_RECORDING = ICON_IDLE
ICON_PROCESSING = ICON_IDLE
ICON_ERROR = ICON_IDLE


def _merge_transcript_text(prefix: str, suffix: str) -> str:
    """Merge a preview transcript with a short tail transcript."""
    prefix = (prefix or "").strip()
    suffix = (suffix or "").strip()
    if not prefix:
        return suffix
    if not suffix:
        return prefix

    prefix_fold = prefix.casefold()
    suffix_fold = suffix.casefold()
    max_overlap = min(len(prefix), len(suffix), 120)
    for overlap in range(max_overlap, 0, -1):
        if prefix_fold[-overlap:] == suffix_fold[:overlap]:
            return (prefix + suffix[overlap:]).strip()

    return _join_transcript_parts(prefix, suffix)


def _join_transcript_parts(prefix: str, suffix: str) -> str:
    if not prefix or not suffix:
        return f"{prefix}{suffix}".strip()
    left = prefix[-1]
    right = suffix[0]
    if left.isspace() or right.isspace():
        return f"{prefix}{suffix}".strip()
    if _is_cjk_char(left) or _is_cjk_char(right):
        return f"{prefix}{suffix}".strip()
    if left in "([{/" or right in ".,!?;:)]}%":
        return f"{prefix}{suffix}".strip()
    return f"{prefix} {suffix}".strip()


def _is_cjk_char(ch: str) -> bool:
    if not ch:
        return False
    code = ord(ch)
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0x3040 <= code <= 0x30FF
        or 0xAC00 <= code <= 0xD7AF
    )


def about_notification_body(backend_info: str) -> str:
    return t("notif_about_body", backend=backend_info)


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

    def refreshMainWindow_(self, _):
        self._app._refresh_main_window_main()

    def flushMainEdits_(self, _):
        if self._app._main_controller:
            self._app._main_controller.flush_edits()

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

    def refreshHotwordMenu_(self, _):
        self._app._update_hotword_menu_title()


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
        recent = self.history.get_recent(1)
        self._latest_dictation = recent[-1] if recent and self.config["history_enabled"] else None
        self._dictation_lock = threading.Lock()
        self._main_state_lock = threading.RLock()
        self._operation_lock = threading.RLock()
        self._model_workers = WeakSet()
        self._asr_engines = WeakSet([self.asr])
        self._polish_engines = WeakSet([self.polish_engine])
        self._operation_id = 0
        self._quitting = False
        self._operation_cancel = threading.Event()
        self._delivery_operation_id = None
        self._recording_operation_id = None
        self._starting_operation_id = None
        self._stopping_operation_id = None
        self._recording_target = {}
        self._recording_field = None
        self._recording_preview_only = False
        self._last_external_app = {}
        self._main_controller = None
        self._setup_center = None
        self._readiness_thread = None
        self._engine_thread = None
        self._engine_error = ""
        self._pending_trial = False
        self._main_state = {"phase": "idle", "status": "", "raw": "", "final": "",
                            "partial": "", "level": 0.0, "elapsed": 0.0,
                            "target_name": "", "ready": False, "readiness": [], "busy": False}
        if self._latest_dictation:
            self._main_state.update(raw=self._latest_dictation.get("raw", ""),
                                    final=self._latest_dictation.get("polished", ""))
        self.snippets = SnippetLibrary()
        self.corrections = CorrectionStore()
        self.hotwords = HotwordStore()
        self.hotkey_listener = None
        self._recording_start_time = 0
        self._is_processing = False
        self._setup_done = False
        self._first_launch = not self.config.get("setup_completed", False)
        self._settings_controller = None
        self._stats_controller = None
        self._history_controller = None
        self._dict_controller = None
        self._diagnostics_controller = None

        # Unified status overlay (recording dot + streaming preview + state phases)
        self._status_overlay = StatusOverlay()
        self._level_timer = None
        self._streaming_transcriber = None
        self._edit_observer = PostInsertEditObserver(
            observation_seconds=self.config.get("hotword_observation_seconds", 18),
            stable_seconds=self.config.get("hotword_observation_stable_seconds", 1.2),
        )

        # "Undo last dictation" support — what we inserted on the most
        # recent successful pass, and into which app.
        self._last_insertion_text: str | None = None
        self._last_insertion_snapshot = None
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
        self._release_guard_thread = None
        self._release_guard_stop = threading.Event()

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
        self._main_item = rumps.MenuItem(t("menu_main_window"), callback=self._show_main_window, key="0")
        self._prepare_item = rumps.MenuItem(t("menu_setup_center"), callback=self._show_setup_center)
        self._dict_item = rumps.MenuItem(t("menu_dict_snippets"), callback=self._open_dict)
        self._hotwords_item = rumps.MenuItem(self._hotword_status_title(), callback=self._open_hotwords_window)
        self._stats_item = rumps.MenuItem(t("menu_history_stats"), callback=self._show_stats)
        self._history_item = rumps.MenuItem(t("menu_dictation_history"), callback=self._show_history)
        self._copy_last_item = rumps.MenuItem(t("menu_copy_last_dictation"), callback=self._copy_last_dictation)
        self._insert_last_item = rumps.MenuItem(t("menu_insert_last_dictation"), callback=self._insert_last_dictation)
        self._diagnostics_item = rumps.MenuItem(t("menu_diagnostics"), callback=self._show_diagnostics)
        self._mic_item = rumps.MenuItem(t("menu_test_mic"), callback=self._test_mic)
        self._config_item = rumps.MenuItem(t("menu_open_config"), callback=self._open_config)
        self._updates_item = rumps.MenuItem(t("menu_check_updates"), callback=self._check_updates)
        self._about_item = rumps.MenuItem(t("menu_about"), callback=self._show_about)
        self._quit_item = rumps.MenuItem(t("menu_quit"), callback=self._quit, key="q")

        self.menu = [
            rumps.MenuItem(f"SpeakType v{APP_VERSION}"),
            self._main_item,
            self._prepare_item,
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
            self._hotwords_item,
            self._stats_item,
            self._history_item,
            self._copy_last_item,
            self._insert_last_item,
            self._diagnostics_item,
            self._mic_item,
            None,
            self._config_item,
            self._updates_item,
            self._about_item,
            None,
            self._quit_item,
        ]

    def _refresh_menu_titles(self):
        self._main_item.title = t("menu_main_window")
        self._prepare_item.title = t("menu_setup_center")
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
        self._update_hotword_menu_title()
        self._stats_item.title = t("menu_history_stats")
        self._history_item.title = t("menu_dictation_history")
        self._copy_last_item.title = t("menu_copy_last_dictation")
        self._insert_last_item.title = t("menu_insert_last_dictation")
        self._diagnostics_item.title = t("menu_diagnostics")
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
            self._apply_settings({**self.config, "ui_language": lang_code})
        return callback

    def _hotkey_display(self):
        return localized_hotkey_display(self.config["hotkey"])

    def _hotword_status_title(self) -> str:
        total = 0
        active = 0
        try:
            entries = self.hotwords.get_all()
            total = len(entries)
            active = sum(1 for entry in entries if entry.get("active"))
        except Exception:
            pass
        return t("menu_hotwords_status", active=active, total=total)

    def _update_hotword_menu_title(self):
        item = getattr(self, "_hotwords_item", None)
        if item is not None:
            item.title = self._hotword_status_title()

    def _refresh_hotword_menu_on_main(self):
        try:
            self._bridge.performSelectorOnMainThread_withObject_waitUntilDone_(
                b"refreshHotwordMenu:", None, False
            )
        except Exception:
            self._update_hotword_menu_title()

    @rumps.timer(1)
    def _startup_timer(self, timer):
        """Run once after app starts to initialize engines."""
        if self._quitting:
            return
        if self._setup_done:
            timer.stop()
            return
        self._setup_done = True
        timer.stop()

        self._show_main_window(None)
        self._readiness_timer = rumps.Timer(lambda _: self._refresh_main_readiness(), 3)
        self._readiness_timer.start()

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
        self._show_main_window(None)
        self._refresh_main_readiness()

    def _desktop_text(self, chinese, english):
        return chinese if get_language() == "zh" else english

    def _new_polish_engine(self):
        config = dict(self.config)
        engine = PolishEngine(model=config["llm_model"], ollama_url=config["ollama_url"])
        with self._operation_lock:
            self._polish_engines.add(engine)
        return engine

    def _start_model_worker(self, target, *, name, args=(), kwargs=None):
        with self._operation_lock:
            if self._quitting:
                return None
            worker = threading.Thread(target=target, name=name, args=args,
                                      kwargs=kwargs or {}, daemon=True)
            self._model_workers.add(worker)
            worker.start()
            return worker

    def _active_model_workers(self):
        with self._operation_lock:
            workers = set(self._model_workers)
            workers.update(worker for worker in (
                self._engine_thread, self._processing_thread, self._readiness_thread,
                self._permission_watch_thread, self._release_guard_thread, self._edit_observer._thread,
            )
                           if worker is not None)
            if self._setup_center is not None:
                workers.update(self._setup_center.worker_threads)
            if self._diagnostics_controller is not None:
                workers.update(self._diagnostics_controller.worker_threads)
            for engine in set(self._asr_engines) | {self.asr}:
                workers.update(worker for worker in (engine._load_thread, engine._warmup_thread)
                               if worker is not None)
            for engine in set(self._polish_engines) | {self.polish_engine}:
                workers.update(worker for worker in (engine._prewarm_thread, engine._chat_prewarm_thread)
                               if worker is not None)
            return [worker for worker in workers if worker.is_alive()]

    def _wait_for_model_workers(self, deadline):
        previous = None
        while True:
            workers = self._active_model_workers()
            if not workers:
                logger.info("Model workers finished before quit")
                return True
            names = sorted({worker.name for worker in workers})
            if names != previous:
                logger.info("Waiting for model workers before quit: %s", ", ".join(names))
                previous = names
            if time.monotonic() >= deadline or threading.current_thread() in workers:
                logger.warning("Quit postponed while model workers remain active: %s", ", ".join(names))
                return False
            NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.02))
            workers[0].join(timeout=min(0.02, max(0, deadline - time.monotonic())))

    def _new_operation(self):
        with self._operation_lock:
            self._operation_cancel.set()
            self._operation_id += 1
            self._operation_cancel = threading.Event()
            self._delivery_operation_id = None
            return self._operation_id

    def _operation_current(self, operation_id):
        with self._operation_lock:
            return operation_id == self._operation_id and not self._operation_cancel.is_set()

    def _update_operation_state(self, operation_id, **changes):
        with self._operation_lock:
            if not self._operation_current(operation_id):
                return False
            self._update_main_state(**changes)
            return True

    def _finish_operation(self, operation_id):
        with self._operation_lock:
            if self._operation_current(operation_id):
                self._is_processing = False
                self._delivery_operation_id = None
                self._update_main_state(busy=False)

    def _update_main_state(self, **changes):
        with self._main_state_lock:
            self._main_state.update(changes)
        if self._quitting:
            return
        if threading.current_thread() is threading.main_thread():
            self._refresh_main_window_main()
        else:
            self._bridge.performSelectorOnMainThread_withObject_waitUntilDone_(b"refreshMainWindow:", None, False)

    def _flush_main_edits(self):
        if self._main_controller is None:
            return
        if threading.current_thread() is threading.main_thread():
            self._main_controller.flush_edits()
        else:
            self._bridge.performSelectorOnMainThread_withObject_waitUntilDone_(b"flushMainEdits:", None, True)

    def _refresh_main_window_main(self):
        if self._quitting or self._main_controller is None:
            return
        with self._main_state_lock:
            snapshot = dict(self._main_state)
        snapshot.update(recent=self.history.get_recent(8), hotkey=self._hotkey_display(),
                        target_name=self._last_external_app.get("name", ""),
                        target_pid=self._last_external_app.get("pid"),
                        translate_target=self.config.get("translate_target", "en"),
                        target_apps=[{"name": str(app.localizedName() or ""),
                                      "bundle_id": str(app.bundleIdentifier() or ""),
                                      "pid": int(app.processIdentifier())}
                                     for app in AppKit.NSWorkspace.sharedWorkspace().runningApplications()
                                     if app.activationPolicy() == AppKit.NSApplicationActivationPolicyRegular
                                     and app.processIdentifier() != os.getpid()
                                     and app.bundleIdentifier() != BUNDLE_IDENTIFIER])
        self._main_controller.update_state(snapshot)
        if self._quitting:
            return
        if snapshot.get("ready") and self._pending_trial:
            self._pending_trial = False
            self._start_recording(preview_only=True)
            return
        if snapshot.get("asr_cached") and not self.asr._loaded and self._engine_thread is None:
            self._do_setup()

    def _remember_external_app(self):
        info = get_active_app()
        if info.get("pid") != os.getpid() and info.get("bundle_id") != BUNDLE_IDENTIFIER:
            if info.get("bundle_id") or info.get("name") not in {"", "Unknown", "Python"}:
                self._last_external_app = dict(info)
        return dict(self._last_external_app)

    def _show_main_window(self, _=None):
        if self._quitting:
            return
        from .main_window import MainWindowController
        self._remember_external_app()
        if self._main_controller is None:
            self._main_controller = MainWindowController(
                on_record=self._main_record, on_cancel=self._main_cancel,
                on_copy=self._main_copy, on_insert=self._main_insert,
                on_polish=lambda text: self._main_transform(text, False),
                on_translate=lambda text: self._main_transform(text, True),
                on_history=lambda: self._show_history(None), on_settings=lambda: self._open_settings(None),
                on_setup=self._show_setup_center, on_dictionary=lambda: self._open_dict(None),
                on_recent=self._main_select_recent, language=self.config.get("ui_language", "zh"),
                on_target=self._main_select_target, on_translate_language=self._main_set_translate_language,
                on_edit=self._main_edit,
            )
        self._main_controller.show()
        self._refresh_main_window_main()
        self._refresh_main_readiness()

    def _show_setup_center(self, action=None):
        if self._quitting:
            return
        if action == "help":
            from .help_window import HelpWindowController
            self._help_controller = _show_or_create_window_controller(
                getattr(self, "_help_controller", None),
                lambda: HelpWindowController(self.config.get("ui_language", "zh"), self._hotkey_display()),
            )
            return
        from .setup_center import SetupCenterController
        if self._setup_center is None:
            self._setup_center = SetupCenterController(
                config=dict(self.config), on_change=self._apply_desktop_settings,
                on_test=self._main_test_recording, on_ready=self._return_from_setup,
            )
        self._setup_center.show()
        self._setup_center.refresh()

    def _return_from_setup(self):
        if not self.asr._loaded and (self._engine_thread is None or not self._engine_thread.is_alive()):
            self._engine_thread = None
            self._engine_error = ""
        self._show_main_window(None)

    def _main_test_recording(self):
        if self._setup_center:
            self._setup_center.close()
        self._show_main_window(None)
        if self.asr._loaded:
            self._start_recording(preview_only=True)
        else:
            self._pending_trial = True
            self._refresh_main_readiness()

    def _apply_desktop_settings(self, patch):
        self._apply_settings({**self.config, **patch})
        self._refresh_main_readiness()

    def _refresh_main_readiness(self):
        with self._operation_lock:
            if self._quitting or self._readiness_thread and self._readiness_thread.is_alive():
                return

        def inspect():
            from .model_download import is_model_cached
            mic = microphone_is_authorized()
            permissions = get_permission_status()
            try:
                cached = is_model_cached(self.config["asr_model"])
            except Exception as error:
                self._update_main_state(phase="error", ready=False, status=str(error))
                return
            llm = PolishEngine(self.config["llm_model"], self.config["ollama_url"])
            enabled = self.config["polish_enabled"] or self.config.get("translate_enabled", False)
            llm_ready = llm.check_available()
            rows = [
                {"key": "microphone", "label": self._desktop_text("麦克风", "Microphone"),
                 "status": "ready" if mic else "missing",
                 "detail": self._desktop_text("录音权限已授权" if mic else "需要授予麦克风权限",
                                               "Microphone allowed" if mic else "Microphone permission required"),
                 "action": "permissions", "action_label": self._desktop_text("检查权限", "Permissions")},
                {"key": "asr", "label": self._desktop_text("语音识别", "Speech recognition"),
                 "status": "ready" if self.asr._loaded else "error" if self._engine_error else "working" if cached else "missing",
                 "detail": self._engine_error or self.config["asr_model"], "action": "asr",
                 "action_label": self._desktop_text("管理模型", "Manage model")},
                {"key": "llm", "label": self._desktop_text("本地润色与翻译", "Local polish and translation"),
                 "status": "ready" if llm_ready else "missing" if enabled else "optional",
                 "detail": self.config["llm_model"] if enabled or llm_ready else self._desktop_text("自动处理已关闭，可直接听写", "Automatic processing is off; dictation is available"),
                 "action": "llm", "action_label": self._desktop_text("配置润色", "Configure")},
                {"key": "accessibility", "label": self._desktop_text("文字插入", "Text insertion"),
                 "status": "ready" if permissions.accessibility and permissions.post_event else "missing",
                 "detail": self._desktop_text("辅助功能与输入控制", "Accessibility and input control"),
                 "action": "permissions", "action_label": self._desktop_text("检查权限", "Permissions")},
                {"key": "hotkey", "label": self._desktop_text("全局快捷键", "Global shortcut"),
                 "status": "ready" if permissions.listen_event else "missing",
                 "detail": self._hotkey_display(), "action": "permissions",
                 "action_label": self._desktop_text("检查权限", "Permissions")},
            ]
            self._update_main_state(readiness=rows, asr_cached=cached, ready=mic and self.asr._loaded)

        with self._operation_lock:
            if self._quitting or self._readiness_thread and self._readiness_thread.is_alive():
                return
            self._readiness_thread = threading.Thread(target=inspect, daemon=True, name="SpeakTypeReadiness")
            self._readiness_thread.start()

    def _reset_hotkey_recording_state(self):
        if self.hotkey_listener:
            self.hotkey_listener.reset_recording_state()

    def _main_record(self):
        if self._quitting:
            return
        if self.recorder.is_recording:
            self._stop_recording()
        elif not self._is_processing:
            self._start_recording(preview_only=True)

    def _main_cancel(self):
        with self._operation_lock:
            with self._main_state_lock:
                if self._delivery_operation_id == self._operation_id or self._main_state.get("phase") == "delivering":
                    return
            cancelled_operation_id = self._operation_id
            self._operation_cancel.set()
        if self.recorder.is_recording:
            self.recorder.set_stream_callback(None)
            self.recorder.stop_audio()
        if self._streaming_transcriber:
            self._streaming_transcriber.stop(wait=False)
            self._streaming_transcriber = None
        self._release_guard_stop.set()
        self._stop_level_monitor()
        self._reset_hotkey_recording_state()
        with self._operation_lock:
            if cancelled_operation_id != self._operation_id:
                return
            self._is_processing = False
            with self._dictation_lock:
                entry = dict(self._latest_dictation or {})
            if entry.get("operation_id") == cancelled_operation_id and entry.get("outcome") == "pending":
                self._finish_dictation_delivery(entry, False, outcome="cancelled")
            self._status_overlay.hide()
            self._update_main_state(phase="cancelled", busy=False, level=0,
                                    raw=entry.get("raw", ""), final=entry.get("polished", ""),
                                    status=self._desktop_text("已取消，现有文本已保留。", "Cancelled. Available text has been kept."))

    def _update_latest_final_text(self, text):
        with self._dictation_lock:
            entry = self._latest_dictation
            if entry is not None:
                changed = entry.get("polished") != text
                entry["polished"] = text
                entry = dict(entry)
            else:
                changed = False
        if entry is None:
            entry = self._retain_dictation("", text, self._last_external_app)
            changed = True
        elif changed and entry.get("id"):
            self.history.update_text(entry["id"], text)
        if changed:
            entry["outcome"] = "saved"
            with self._dictation_lock:
                self._latest_dictation["outcome"] = "saved"
            if entry.get("id"):
                self.history.set_outcome(entry["id"], "saved")
        self._update_main_state(raw=entry.get("raw", ""), final=text)
        return entry

    def _main_edit(self, text):
        self._update_latest_final_text(text)

    def _begin_delivery(self, operation_id, status=None):
        with self._operation_lock:
            if not self._operation_current(operation_id):
                return False
            self._delivery_operation_id = operation_id
            self._update_main_state(phase="delivering", status=status or self._desktop_text("正在插入文字…", "Inserting text…"))
            return True

    def _main_copy(self, text):
        if not text:
            return
        self._update_latest_final_text(text)
        self._copy_last_dictation(None)
        self._update_main_state(status=self._desktop_text("文本已复制。", "Text copied."))

    def _main_insert(self, text):
        if not text or self._is_processing or self._quitting:
            return
        if not self._last_external_app:
            self._update_main_state(status=self._desktop_text("请先选择其他应用中的输入框，再打开 SpeakType。", "Select a field in another app, then open SpeakType."))
            return
        with self._operation_lock:
            entry = self._update_latest_final_text(text)
            target = dict(self._last_external_app)
            operation_id = self._new_operation()
            self._is_processing = True
            self._update_main_state(busy=True)
            self._begin_delivery(operation_id)

        def deliver():
            try:
                if not self._operation_current(operation_id):
                    return
                inserted = insert_text(text, method=self.config["insert_method"],
                                       app_name=target.get("name", ""), bundle_id=target.get("bundle_id", ""),
                                       target_pid=target.get("pid"))
                if not self._finish_dictation_delivery(entry, inserted, operation_id=operation_id):
                    return
                if inserted:
                    self._remember_last_insertion(text, target)
                else:
                    self._notify_insert_failed(target)
            finally:
                self._finish_operation(operation_id)

        with self._operation_lock:
            self._processing_thread = self._start_model_worker(deliver, name="SpeakTypeWindowInsert")

    def _main_transform(self, text, translate):
        if not text or self._is_processing or self._quitting:
            return
        with self._operation_lock:
            operation_id = self._new_operation()
            entry = self._update_latest_final_text(text)
            entry.update(operation_id=operation_id, outcome="pending")
            with self._dictation_lock:
                self._latest_dictation.update(operation_id=operation_id, outcome="pending")
            if entry.get("id"):
                self.history.set_outcome(entry["id"], "pending")
            self._is_processing = True
            polish_engine = self._new_polish_engine()
            self._update_main_state(busy=True, phase="translating" if translate else "polishing",
                                    status=self._desktop_text("正在处理文本…", "Processing text…"))

        def transform():
            try:
                if not polish_engine.check_available():
                    raise RuntimeError(polish_engine.last_error)
                result = (polish_engine.translate(text, target_lang=self.config.get("translate_target", "en"))
                          if translate else polish_engine.polish(text, language=self.config.get("language", "auto")))
                if polish_engine.last_error:
                    raise RuntimeError(polish_engine.last_error)
                self._commit_dictation_text(entry, result, operation_id, outcome="saved",
                                            status=self._desktop_text("文本已准备好，可以复制或插入。", "Text is ready to copy or insert."))
            except Exception as error:
                with self._operation_lock:
                    if self._commit_dictation_text(entry, entry["polished"], operation_id, outcome="saved"):
                        self._update_main_state(phase="error", status=str(error))
            finally:
                self._finish_operation(operation_id)

        with self._operation_lock:
            self._processing_thread = self._start_model_worker(transform, name="SpeakTypeTextTransform")

    def _main_select_recent(self, entry_id):
        if self._is_processing or self.recorder.is_recording:
            return
        entry = next(item for item in self.history.snapshot() if item["id"] == entry_id)
        with self._dictation_lock:
            self._latest_dictation = dict(entry)
        self._update_main_state(phase="done", raw=entry["raw"], final=entry["polished"],
                                status=self._desktop_text("已打开这条听写。", "Dictation opened."))

    def _main_select_target(self, app_info):
        app = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(int(app_info["pid"]))
        if app is None or app.isTerminated() or app.processIdentifier() == os.getpid():
            self._update_main_state(status=self._desktop_text("目标应用已经关闭，请重新选择。", "The target app closed. Choose another app."))
            return
        if str(app.bundleIdentifier() or "") != app_info.get("bundle_id", ""):
            raise ValueError("The selected application no longer matches its process")
        self._last_external_app = dict(app_info)
        self._update_main_state(target_name=app_info["name"],
                                status=self._desktop_text("已选择目标应用，请确保其中有可编辑输入框。", "Target selected. Make sure it has an editable field."))

    def _main_set_translate_language(self, code):
        self.config["translate_target"] = code
        save_config(self.config)
        self._update_main_state(translate_target=code)

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
        operation_id = self._recording_operation_id

        def partial(text):
            with self._operation_lock:
                if self._operation_current(operation_id):
                    self._status_overlay.update_partial_text(text)
                    self._update_main_state(partial=text)

        return StreamingTranscriber(
            self.asr,
            on_partial_text=partial,
            sample_rate=self.config["sample_rate"],
        )

    def _hotword_context_for_app(
        self,
        app_info: dict | None = None,
        scene_id: str | None = None,
    ) -> ActiveHotwordContext:
        if not self.config.get("hotword_context_enabled", True):
            return ActiveHotwordContext(terms=[], context="")
        store = getattr(self, "hotwords", None)
        if store is None or not hasattr(store, "active_context"):
            return ActiveHotwordContext(terms=[], context="")
        try:
            app_info = app_info or get_active_app()
            scene = scene_id if scene_id is not None else get_scene_for_app(app_info)
            return store.active_context(
                app_info=app_info,
                scene=scene,
                language=self.config.get("language", "auto"),
                limit=int(self.config.get("hotword_max_context_terms", 30) or 30),
            )
        except Exception as e:
            logger.debug(f"Failed to build hotword context: {e}")
            return ActiveHotwordContext(terms=[], context="")

    def _start_edit_observation(
        self,
        *,
        raw_text: str,
        inserted_text: str,
        app_info: dict | None,
        scene_id: str = "",
    ):
        with self._operation_lock:
            if self._quitting or not self.config.get("hotword_learning_enabled", True):
                return
            observer = getattr(self, "_edit_observer", None)
            if observer is None or not hasattr(observer, "start"):
                return
            try:
                observer.start(
                    raw_text=raw_text,
                    inserted_text=inserted_text,
                    app_info=app_info or {},
                    scene=scene_id,
                    language=self.config.get("language", "auto"),
                    on_edit=self._handle_observed_edit,
                )
            except Exception as e:
                logger.debug(f"Post-insert edit observation did not start: {e}")

    def _cancel_edit_observation(self):
        observer = getattr(self, "_edit_observer", None)
        if observer is not None and hasattr(observer, "cancel"):
            try:
                observer.cancel()
            except Exception:
                pass

    def _handle_observed_edit(self, observation: EditObservation):
        with self._operation_lock:
            if self._quitting:
                return
            if threading.current_thread() is not threading.main_thread():
                self._model_workers.add(threading.current_thread())
        logger.info(
            "Observed post-insert edit for hotword learning (inserted_len=%d edited_len=%d app=%s)",
            len(observation.inserted_text or ""),
            len(observation.edited_text or ""),
            (observation.app_info or {}).get("name", "Unknown"),
        )
        polish_engine = self._new_polish_engine()
        analyzer = getattr(polish_engine, "analyze_edit_learning", None)
        if not callable(analyzer):
            return
        payload = analyzer(
            observation.raw_text,
            observation.inserted_text,
            observation.edited_text,
            app_name=(observation.app_info or {}).get("name", ""),
            scene=observation.scene,
            language=observation.language,
        )
        store = getattr(self, "hotwords", None)
        learned = []
        if store is not None and hasattr(store, "learn_from_payload"):
            learned = store.learn_from_payload(
                payload,
                app_info=observation.app_info,
                scene=observation.scene,
                language=observation.language,
                raw_text=observation.raw_text,
                edited_text=observation.edited_text,
            )

        if self.config.get("hotword_auto_corrections_enabled", True):
            for correction in extract_confident_corrections(
                payload,
                raw_text=observation.raw_text,
                inserted_text=observation.inserted_text,
                edited_text=observation.edited_text,
            ):
                try:
                    self.corrections.add(correction["wrong"], correction["right"])
                except Exception as e:
                    logger.debug(f"Failed to add learned correction: {e}")

        if learned:
            logger.info(
                "Learned hotwords: %s",
                ", ".join(entry.get("term", "") for entry in learned),
            )
            self._refresh_hotword_menu_on_main()

    def _transcribe_with_hotwords(self, audio_input, hotword_context: str = "") -> str:
        try:
            return self.asr.transcribe(
                audio_input,
                language=self.config["language"],
                hotword_context=hotword_context,
            )
        except TypeError as e:
            if "hotword_context" not in str(e):
                raise
            return self.asr.transcribe(audio_input, language=self.config["language"])

    def _start_streaming_preview(self) -> bool:
        with self._operation_lock:
            if self._quitting or self._streaming_transcriber is not None or not self.recorder.is_recording:
                return False
            try:
                streamer = self._build_streaming_transcriber()
                self.recorder.set_stream_callback(streamer.feed_audio)
                context = self._hotword_context_for_app()
                streamer.start(language=self.config["language"], hotword_context=context.context)
                self._model_workers.add(streamer._thread)
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
        with self._operation_lock:
            if self._quitting:
                return
            if not self.asr._loaded:
                self.asr.load_async()
            if self.config.get("streaming_preview", True) and not self.asr._loaded:
                self._start_model_worker(self._late_start_streaming_preview, name="SpeakTypeLatePreview")
            if self.config.get("polish_enabled") or self.config.get("translate_enabled", False):
                self.polish_engine.chat_prewarm_async()

    def _setup_llm_engine(self):
        if not (self.config.get("polish_enabled") or self.config.get("translate_enabled", False)):
            return

        try:
            if self.polish_engine.check_available():
                logger.info("LLM polish engine available")
                self._llm_unavailable_notified = False
                self.polish_engine.prewarm_async()
                return
        except Exception as e:
            logger.warning("LLM availability check failed: %s", e)

        logger.warning("LLM not available")
        self._notify_llm_unavailable_once()

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
            _delta("inserted", "history_saved"),
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

    def _observe_llm_status(self, engine=None) -> bool:
        error = (self.polish_engine if engine is None else engine).last_error
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
        llm_error: str | None = None,
    ):
        app_name = (app_info or {}).get("name") or "Unknown"
        diagnostic = get_last_insert_diagnostic()
        unverified = bool(diagnostic and diagnostic.success and not diagnostic.verified)
        if unverified and llm_fallback_used:
            logger.warning(
                "Text sent to %s without AX verification; LLM polish/translation was also skipped (method=%s reason=%s)",
                app_name,
                diagnostic.method,
                diagnostic.reason,
            )
            self._show_overlay_notice(
                self._llm_fallback_overlay_text(llm_error),
                auto_hide_after=2.2,
            )
            return
        if unverified:
            logger.warning(
                "Text sent to %s without AX verification (method=%s reason=%s); keeping final text visible and relying on diagnostics/logs for details",
                app_name,
                diagnostic.method,
                diagnostic.reason,
            )
            return
        if llm_fallback_used:
            self._show_overlay_notice(
                self._llm_fallback_overlay_text(llm_error),
                auto_hide_after=2.2,
            )

    def _do_setup(self):
        with self._operation_lock:
            if self._engine_thread is not None or self._quitting:
                return
            engine = self.asr

        def init_engines():
            if self.config["polish_enabled"] or self.config.get("translate_enabled", False):
                self._start_model_worker(self._setup_llm_engine, name="SpeakTypeLLMSetup")

            with self._operation_lock:
                if not self._update_asr_engine_state(engine, phase="loading", status=self._desktop_text("正在加载语音模型…", "Loading speech model…")):
                    return
                self._set_status(t("status_loading_asr"))
            logger.info("Loading ASR engine...")

            def _asr_progress(pct, status):
                with self._operation_lock:
                    if self._update_asr_engine_state(engine, status=t("status_downloading_asr", pct=pct, size=status)):
                        self._set_status(t("status_downloading_asr", pct=pct, size=status))

            try:
                engine.load(progress_callback=_asr_progress)
                logger.info(f"ASR engine loaded: {engine.get_backend_info()}")
            except Exception as e:
                logger.error(f"ASR load failed: {e}")
                with self._operation_lock:
                    if self.asr is engine:
                        self._engine_error = str(e)
                    if self._update_asr_engine_state(engine, phase="error", ready=False, status=str(e)):
                        self._set_status(t("status_asr_error"))
                        self._set_title(ICON_ERROR)
                        self._engine_error = str(e)
                        rumps.notification("SpeakType", t("notif_asr_failed"), str(e))
                return

            # Load plugins
            if self.config.get("plugins_enabled", False):
                try:
                    self._plugin_manager.reload_all()
                except Exception as e:
                    logger.warning(f"Plugin loading failed: {e}")

            with self._operation_lock:
                if self._update_asr_engine_state(engine, phase="idle", ready=microphone_is_authorized(),
                                                status=self._desktop_text("可以开始听写。点击录音按钮，或在其他应用中使用快捷键。",
                                                                          "Ready. Click Record, or use the shortcut in another app.")):
                    self._set_status(t("status_ready"))
                    self._set_title(ICON_IDLE)

        with self._operation_lock:
            if self.asr is not engine or self._quitting or self._engine_thread is not None:
                return
            self._engine_thread = self._start_model_worker(init_engines, name="SpeakTypeEngines")
        self._restart_hotkey_listener()
        self._start_permission_restart_watcher()

        # Delayed accessibility check — warn if pynput can't listen
        def _delayed_perm_check():
            if self._permission_watch_stop.wait(5) or self._quitting:
                return
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
        self._start_model_worker(_delayed_perm_check, name="SpeakTypePermissionCheck")

    def _update_asr_engine_state(self, engine, **changes):
        with self._operation_lock:
            if self.asr is not engine or self._quitting:
                return False
            if self._is_processing or self.recorder.is_recording:
                changes.pop("phase", None)
                changes.pop("status", None)
            self._update_main_state(**changes)
            return True

    def _start_permission_restart_watcher(self):
        """Prompt for restart if macOS grants input permissions while running."""
        with self._operation_lock:
            if self._quitting:
                return
            if (self._permission_watch_thread is not None and self._permission_watch_thread.is_alive()
                    and not self._permission_watch_stop.is_set()):
                return
        try:
            status = get_permission_status()
        except Exception as e:
            logger.debug(f"Permission watcher could not read initial status: {e}")
            return

        with self._operation_lock:
            if self._quitting:
                return
            self._last_permission_status = status
            if status.all_granted:
                if self.config.get(PERMISSION_RESTART_PENDING_KEY):
                    self._prompt_for_permission_restart(
                        "Input permissions already granted after permission refresh"
                    )
                return
            self._permission_watch_stop = threading.Event()
            self._permission_watch_thread = self._start_model_worker(
                self._permission_restart_watch_loop, name="SpeakTypePermissionWatcher",
                args=(self._permission_watch_stop,))

    def _permission_restart_watch_loop(self, stop_event):
        while not stop_event.wait(2.0):
            try:
                current = get_permission_status()
            except Exception as e:
                logger.debug(f"Permission watcher read failed: {e}")
                continue
            if stop_event.is_set() or self._quitting:
                return
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
                self._restart_hotkey_listener()
                self._refresh_main_readiness()
                return

    def _prompt_for_permission_restart(self, reason: str):
        if self._quitting or self._permission_restart_prompt_shown:
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
        if self._quitting:
            return
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
        if self._quitting or not self._prepare_to_quit():
            return
        bundle_path = get_running_bundle_path()
        command = [str(Path(bundle_path) / "Contents/MacOS/SpeakType")] if bundle_path else [
            sys.executable, str(Path(__file__).resolve().parents[1] / "main.py")
        ]
        try:
            subprocess.Popen(
                ["/bin/sh", "-c", 'while kill -0 "$1" 2>/dev/null; do sleep 0.1; done; shift; exec "$@"',
                 "speaktype-restart", str(os.getpid()), *command],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as e:
            logger.warning(f"Failed to schedule app relaunch: {e}")
            self._resume_after_quit(str(e))
            return
        self._finish_quit()

    def _restart_hotkey_listener(self):
        """(Re)start the hotkey listener with current config."""
        if self.hotkey_listener:
            self.hotkey_listener.stop()
        if self._quitting:
            return
        permissions = get_permission_status()
        if not permissions.listen_event or not permissions.accessibility:
            self.hotkey_listener = None
            return

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
            self._reset_hotkey_recording_state()
            return
        self._start_recording()

    def _on_hotkey_release(self):
        if not self.recorder.is_recording:
            return
        self._stop_recording()

    # --- Toggle mode handler ---

    def _on_toggle(self, is_active: bool):
        if self.recorder.is_recording:
            self._stop_recording()
        elif self._is_processing:
            self._reset_hotkey_recording_state()
        else:
            self._start_recording()

    # --- Common recording logic ---

    def _start_recording(self, preview_only=False):
        with self._operation_lock:
            if self._quitting:
                return
            if threading.current_thread() is not threading.main_thread():
                self._model_workers.add(threading.current_thread())
        if self._is_processing or self.recorder.is_recording or self._quitting or self._stopping_operation_id is not None:
            self._reset_hotkey_recording_state()
            return
        self._flush_main_edits()
        if not microphone_is_authorized():
            self._reset_hotkey_recording_state()
            self._update_main_state(phase="error", status=self._desktop_text("请在权限与模型准备中授予麦克风权限。", "Allow microphone access in Permissions and Models."))
            return
        if not self.asr._loaded:
            self._reset_hotkey_recording_state()
            self._update_main_state(phase="loading", ready=False,
                                    status=self._desktop_text("语音模型尚未准备好，请打开权限与模型准备。",
                                                              "Speech model is not ready. Open Permissions and Models."))
            self._refresh_main_readiness()
            return
        current = get_active_app()
        own_app = current.get("pid") == os.getpid() or current.get("bundle_id") == BUNDLE_IDENTIFIER
        recording_preview_only = bool(preview_only or own_app)
        recording_target = dict(self._last_external_app if own_app else current)
        try:
            recording_field = None if recording_preview_only else capture_target_field(current)
        except RuntimeError as error:
            self._reset_hotkey_recording_state()
            self._update_main_state(phase="error", status=str(error))
            return
        with self._operation_lock:
            if self._starting_operation_id is not None or self._quitting or self.recorder.is_recording:
                self._reset_hotkey_recording_state()
                return
            operation_id = self._new_operation()
            self._recording_operation_id = operation_id
            self._starting_operation_id = operation_id
            self._recording_preview_only = recording_preview_only
            self._recording_target = recording_target
            self._recording_field = recording_field
            if not own_app:
                self._last_external_app = dict(current)
            with self._recording_stop_lock:
                self._recording_stop_requested = False
        self._cancel_edit_observation()
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

        with self._operation_lock:
            abandoned = not self._operation_current(operation_id) or self._quitting
        if abandoned:
            if self.recorder.is_recording:
                self.recorder.stop_audio()
            with self._operation_lock:
                if self._starting_operation_id == operation_id:
                    self._starting_operation_id = None
            return

        if not started:
            with self._operation_lock:
                if not self._operation_current(operation_id) or self._quitting:
                    if self._starting_operation_id == operation_id:
                        self._starting_operation_id = None
                    return
                self._reset_hotkey_recording_state()
                self.recorder.set_stream_callback(None)
                self.recorder.set_whisper_state_callback(None)
                self._streaming_transcriber = None
                with self._recording_stop_lock:
                    self._recording_stop_requested = False
                self._recording_start_time = 0
                err = self.recorder.last_start_error
                message = str(err) if err else "Could not open microphone."
                logger.error(f"Recording failed to start: {message}")
                self._show_overlay_error(t("overlay_mic_start_failed"), auto_hide_after=3.0)
                rumps.notification("SpeakType", t("notif_error"), message)
                self._update_main_state(phase="error", busy=False, status=message)
                if self._starting_operation_id == operation_id:
                    self._starting_operation_id = None
            return

        with self._recording_stop_lock:
            stop_already_requested = self._recording_stop_requested
        if stop_already_requested:
            with self._operation_lock:
                if self._starting_operation_id == operation_id:
                    self._starting_operation_id = None
            return

        with self._operation_lock:
            if self._starting_operation_id == operation_id:
                self._starting_operation_id = None
            if not self._operation_current(operation_id):
                return
            logger.info("Recording started")
            if self.hotkey_listener and self.hotkey_listener.mode == "toggle":
                self.hotkey_listener._toggle_active = True
            self._update_main_state(phase="recording", busy=True, raw="", final="", partial="", elapsed=0,
                                    status=self._desktop_text("正在录音，再次点击即可停止。", "Recording. Click again to stop."))
        if self.config["sound_feedback"]:
            _play_sound("Tink")

        if self.config.get("plugins_enabled"):
            self._plugin_manager.run_hook("on_recording_start")

        if not self._operation_current(operation_id):
            return
        self._prime_pipeline_for_recording()
        context = self._hotword_context_for_app(self._recording_target)
        recording_note = ""
        if context.terms:
            recording_note = t("overlay_hotwords_active", count=len(context.terms))
        with self._operation_lock:
            if not self._operation_current(operation_id):
                return
            self._status_overlay.show_recording(recording_note)
        self._start_level_monitor()

        if streamer is not None:
            try:
                with self._operation_lock:
                    if not self._operation_current(operation_id):
                        return
                    self.recorder.set_stream_callback(streamer.feed_audio)
                    streamer.start(language=self.config["language"], hotword_context=context.context)
                    self._model_workers.add(streamer._thread)
                    self._streaming_transcriber = streamer
            except Exception as e:
                logger.debug(f"Streaming preview failed to start: {e}")
                self._streaming_transcriber = None
                self.recorder.set_stream_callback(None)
        else:
            self._streaming_transcriber = None

        if not self._recording_preview_only:
            self._start_hotkey_release_guard()

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
        stop_started = time.perf_counter()
        with self._operation_lock:
            if self._quitting:
                return
            if threading.current_thread() is not threading.main_thread():
                self._model_workers.add(threading.current_thread())
            operation_id = self._recording_operation_id
            if not self._operation_current(operation_id):
                return
            with self._recording_stop_lock:
                if self._recording_stop_requested or not self.recorder.is_recording:
                    return
                self._recording_stop_requested = True
            self._stopping_operation_id = operation_id
            recorder = self.recorder
            target = dict(self._recording_target)
            target_field = self._recording_field
            insert_result = not self._recording_preview_only
            streamer = self._streaming_transcriber
            self._streaming_transcriber = None
            duration = max(0.0, time.time() - (self._recording_start_time or time.time()))
            self._is_processing = True
            self._update_main_state(phase="transcribing", busy=True, level=0,
                                    status=self._desktop_text("正在识别语音…", "Transcribing…"))
        try:
            self._reset_hotkey_recording_state()
            self._release_guard_stop.set()
            logger.info(f"Recording stopped after {duration:.1f}s")
            if self.config["sound_feedback"]:
                _play_sound("Pop")
            if self.config.get("plugins_enabled"):
                self._plugin_manager.run_hook("on_recording_stop")
            self._stop_level_monitor()
            preview_text = ""
            preview_snapshot = None
            if streamer is not None:
                preview_snapshot = streamer.snapshot()
                preview_text = streamer.stop(wait=False) or ""
            recorder.set_stream_callback(None)
            can_use_in_memory_audio = self.asr.backend == "qwen" and not self.config.get("plugins_enabled")
            audio_input = recorder.stop_audio() if can_use_in_memory_audio else recorder.stop()
            audio_ready_at = time.perf_counter()
            with self._operation_lock:
                if not self._operation_current(operation_id):
                    if isinstance(audio_input, (str, os.PathLike)):
                        Path(audio_input).unlink(missing_ok=True)
                    return
                if audio_input is None:
                    reason = recorder.last_stop_reason or "unknown"
                    message = recorder.last_stop_message or ""
                    overlay_key = {"too_short": "overlay_audio_too_short", "too_quiet": "overlay_audio_too_quiet",
                                   "no_frames": "overlay_no_audio", "not_recording": "overlay_no_audio"}.get(reason, "overlay_no_audio")
                    self._show_overlay_error(t(overlay_key), auto_hide_after=2.0)
                    self._is_processing = False
                    self._update_main_state(phase="error", busy=False, status=message or t(overlay_key))
                    return
                self._show_overlay_transcribing(t("overlay_finalizing_preview") if preview_text else "")
                self._processing_thread = self._start_model_worker(
                    self._process_audio, name="SpeakTypeTranscription", args=(audio_input, duration, preview_snapshot),
                    kwargs={"app_info": target, "insert_result": insert_result,
                            "operation_id": operation_id, "target_field": target_field})
            logger.info("Stop latency: finalize_audio=%.3fs dispatch_processing=%.3fs",
                        audio_ready_at - stop_started, time.perf_counter() - audio_ready_at)
        finally:
            with self._operation_lock:
                if self._stopping_operation_id == operation_id:
                    self._stopping_operation_id = None

    def _start_hotkey_release_guard(self):
        if self.config.get("dictation_mode", "push_to_talk") != "push_to_talk":
            return
        listener = self.hotkey_listener
        if listener is None or not hasattr(listener, "is_physically_pressed"):
            return
        self._release_guard_stop.set()
        self._release_guard_stop = threading.Event()
        self._release_guard_thread = self._start_model_worker(
            self._hotkey_release_guard_loop,
            args=(self._release_guard_stop,),
            name="SpeakTypeHotkeyReleaseGuard",
        )

    def _hotkey_release_guard_loop(self, stop_event: threading.Event):
        if stop_event.wait(HOTKEY_RELEASE_GUARD_GRACE_SECONDS):
            return
        missed_release_count = 0
        while not stop_event.wait(HOTKEY_RELEASE_GUARD_INTERVAL_SECONDS):
            if not getattr(self.recorder, "is_recording", False):
                return
            listener = self.hotkey_listener
            if listener is None or not hasattr(listener, "is_physically_pressed"):
                return
            physical_pressed = listener.is_physically_pressed()
            if physical_pressed is None:
                return
            if physical_pressed:
                missed_release_count = 0
                continue

            missed_release_count += 1
            if missed_release_count < HOTKEY_RELEASE_GUARD_MISSES:
                continue

            logger.warning("Hotkey release appears to have been missed; auto-stopping recording")
            try:
                if hasattr(listener, "clear_pressed_state"):
                    listener.clear_pressed_state()
            except Exception as e:
                logger.debug(f"Failed to clear stale hotkey state: {e}")
            self._stop_recording()
            return

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
        if not self.recorder.is_recording or not self._operation_current(self._recording_operation_id) or self._quitting:
            return
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
        self._update_main_state(level=level, elapsed=max(0, time.time() - self._recording_start_time))

    def _preview_reuse_candidate(self, audio_input, preview_snapshot) -> str:
        if not PREVIEW_FINAL_ACCELERATION_ENABLED:
            return ""
        if preview_snapshot is None:
            return ""
        text = (getattr(preview_snapshot, "text", "") or "").strip()
        if not text:
            return ""
        if not self.config.get("streaming_preview", True) or self.config.get("plugins_enabled"):
            return ""
        if getattr(self.asr, "backend", "qwen") != "qwen":
            return ""

        sample_rate = int(self.config.get("sample_rate", 16000) or 16000)
        original_samples = int(getattr(self.recorder, "last_audio_original_samples", 0) or 0)
        if original_samples <= 0:
            try:
                original_samples = len(audio_input)
            except Exception:
                original_samples = 0
        covered_samples = int(getattr(preview_snapshot, "covered_samples", 0) or 0)
        if original_samples <= 0 or covered_samples <= 0:
            return ""

        uncovered = original_samples - covered_samples
        max_uncovered = int(sample_rate * PREVIEW_REUSE_MAX_UNCOVERED_SECONDS)
        if uncovered > max_uncovered:
            logger.info(
                "Skipping preview transcript reuse: uncovered_tail=%.3fs > %.3fs",
                uncovered / sample_rate,
                PREVIEW_REUSE_MAX_UNCOVERED_SECONDS,
            )
            return ""

        if not bool(getattr(self.recorder, "last_audio_tail_quiet", False)):
            logger.info(
                "Skipping preview transcript reuse: tail audio is not quiet (rms=%.5f)",
                float(getattr(self.recorder, "last_audio_tail_rms", 0.0) or 0.0),
            )
            return ""

        emitted_at = float(getattr(preview_snapshot, "emitted_at", 0.0) or 0.0)
        if emitted_at and time.monotonic() - emitted_at > PREVIEW_REUSE_MAX_AGE_SECONDS:
            logger.info("Skipping preview transcript reuse: preview snapshot is stale")
            return ""

        logger.info(
            "Using streaming preview as final transcript (covered=%.3fs original=%.3fs tail_rms=%.5f)",
            covered_samples / sample_rate,
            original_samples / sample_rate,
            float(getattr(self.recorder, "last_audio_tail_rms", 0.0) or 0.0),
        )
        return text

    def _tail_asr_candidate(self, audio_input, preview_snapshot, hotword_context: str = "") -> str:
        if not PREVIEW_FINAL_ACCELERATION_ENABLED:
            return ""
        if preview_snapshot is None:
            return ""
        preview_text = (getattr(preview_snapshot, "text", "") or "").strip()
        if not preview_text:
            return ""
        if not self.config.get("streaming_preview", True) or self.config.get("plugins_enabled"):
            return ""
        if getattr(self.asr, "backend", "qwen") != "qwen":
            return ""

        try:
            import numpy as np

            audio_data = np.asarray(audio_input, dtype="float32").flatten()
        except Exception:
            return ""
        if len(audio_data) <= 0:
            return ""

        sample_rate = int(self.config.get("sample_rate", 16000) or 16000)
        original_samples = int(getattr(self.recorder, "last_audio_original_samples", 0) or 0)
        if original_samples <= 0:
            original_samples = len(audio_data)
        covered_samples = int(getattr(preview_snapshot, "covered_samples", 0) or 0)
        if original_samples <= 0 or covered_samples <= 0:
            return ""

        uncovered = original_samples - covered_samples
        min_uncovered = int(sample_rate * TAIL_ASR_MIN_UNCOVERED_SECONDS)
        max_uncovered = int(sample_rate * TAIL_ASR_MAX_UNCOVERED_SECONDS)
        if uncovered < min_uncovered or uncovered > max_uncovered:
            return ""

        pad_samples = int(sample_rate * TAIL_ASR_PADDING_SECONDS)
        tail_samples = min(len(audio_data), max(min_uncovered, uncovered + pad_samples))
        if tail_samples <= 0:
            return ""

        tail_audio = audio_data[-tail_samples:].copy()
        logger.info(
            "Running tail ASR merge (covered=%.3fs original=%.3fs tail=%.3fs)",
            covered_samples / sample_rate,
            original_samples / sample_rate,
            tail_samples / sample_rate,
        )
        tail_text = self._transcribe_with_hotwords(tail_audio, hotword_context)
        tail_text = (tail_text or "").strip()
        if not tail_text:
            logger.info("Tail ASR merge returned no text; falling back to full transcription")
            return ""
        return _merge_transcript_text(preview_text, tail_text)

    def _process_audio(self, audio_input, duration: float, preview_snapshot=None, *,
                       app_info=None, insert_result=True, operation_id=None, target_field=None):
        operation_id = self._new_operation() if operation_id is None else operation_id
        marks = {"start": time.perf_counter()}
        llm_fallback_used = False
        llm_fallback_error = ""
        polish_engine = self._new_polish_engine()
        entry = None
        recording_path = audio_input if isinstance(audio_input, (str, os.PathLike)) else None
        try:
            with self._operation_lock:
                if not self._operation_current(operation_id):
                    return
                self._is_processing = True
                self._update_main_state(phase="transcribing", busy=True,
                                        status=self._desktop_text("正在识别语音…", "Transcribing…"))
            app_info = dict(app_info) if app_info is not None else get_active_app()
            tone = get_tone_for_app(app_info) if self.config["context_aware_tone"] else "neutral"
            active_scene_id = get_scene_for_app(app_info)
            active_hotwords = self._hotword_context_for_app(app_info, active_scene_id)

            # Plugin: pre_transcribe
            if self.config.get("plugins_enabled"):
                audio_input = self._plugin_manager.run_hook("pre_transcribe", audio_input) or audio_input

            logger.info("Transcribing...")
            if hasattr(self.asr, "_loaded") and not getattr(self.asr, "_loaded", False):
                self._show_overlay_transcribing(t("overlay_asr_loading"))
            raw_text = self._preview_reuse_candidate(audio_input, preview_snapshot)
            if raw_text:
                logger.info("Transcribing skipped: reused streaming preview transcript")
            else:
                raw_text = self._tail_asr_candidate(audio_input, preview_snapshot, active_hotwords.context)
                if raw_text:
                    logger.info("Transcribing accelerated: merged streaming preview with tail ASR")
                else:
                    raw_text = self._transcribe_with_hotwords(audio_input, active_hotwords.context)
            marks["transcribed"] = time.perf_counter()
            with self._operation_lock:
                if not self._operation_current(operation_id):
                    return
                if not raw_text.strip():
                    logger.info("Empty transcription")
                    self._show_overlay_error(t("overlay_empty_transcription"), auto_hide_after=1.8)
                    self._update_main_state(phase="error", status=t("overlay_empty_transcription"))
                    return

            logger.info(f"Raw: {raw_text}")
            original_transcription = raw_text

            # Plugin: post_transcribe
            if self.config.get("plugins_enabled"):
                raw_text = self._plugin_manager.run_hook("post_transcribe", raw_text) or raw_text

            # Apply user-defined corrections (e.g. "PI thon" -> "Python")
            try:
                raw_text = self.corrections.apply(raw_text)
            except Exception as e:
                logger.debug(f"Correction store apply failed: {e}")

            # Local action commands (undo last dictation, etc.)
            if not self._operation_current(operation_id):
                return
            if self.config["voice_commands_enabled"] and insert_result:
                action = detect_action_command(raw_text)
                if action == "undo_last":
                    if not self._begin_delivery(operation_id, self._desktop_text("正在撤销听写…", "Undoing dictation…")):
                        return
                    undone = self._handle_undo_last()
                    if undone:
                        self._status_overlay.show_done("\u21b6")  # ↶ undo glyph
                    else:
                        self._status_overlay.hide(delay=0.4)
                    self._update_operation_state(operation_id, phase="done", status=self._desktop_text(
                        "已撤销最近听写。" if undone else "输入位置已经变化，当前文字已保留。",
                        "Last dictation undone." if undone else "The input position changed. Current text was preserved."))
                    return

            # Check for snippet triggers
            snippet_text = self.snippets.match(raw_text)
            if snippet_text:
                logger.info(f"Snippet matched: {raw_text} -> {snippet_text[:40]}")
                entry = self._retain_dictation(original_transcription, snippet_text, app_info, duration, operation_id=operation_id)
                if entry is None:
                    return
                if not insert_result:
                    self._commit_dictation_text(entry, snippet_text, operation_id, outcome="saved", show_done=True)
                    return
                if not self._begin_delivery(operation_id):
                    return
                if target_field is not None and not prepare_unchanged_target(target_field):
                    self._finish_dictation_delivery(entry, False, operation_id=operation_id)
                    self._update_operation_state(operation_id, status=self._desktop_text("原来的输入位置已经变化，文本已保留。请选择目标后再次插入。",
                                                                      "The original field changed. Text kept. Choose a target and insert again."))
                    return
                if not self._operation_current(operation_id):
                    return
                reset_last_insert_diagnostic()
                inserted_ok = insert_text(
                    snippet_text,
                    method=self.config["insert_method"],
                    app_name=app_info.get("name", ""),
                    bundle_id=app_info.get("bundle_id", ""),
                    target_pid=app_info.get("pid"),
                )
                self._finish_dictation_delivery(entry, inserted_ok, operation_id=operation_id)
                if not inserted_ok:
                    self._notify_insert_failed(app_info)
                    return
                self._show_successful_insert_feedback(app_info, snippet_text)
                self._remember_last_insertion(snippet_text, app_info)
                return

            # Check for edit commands
            if self.config["voice_commands_enabled"] and insert_result:
                is_edit, command = detect_edit_command(raw_text)
                if is_edit:
                    if target_field is not None and not prepare_unchanged_target(target_field):
                        self._update_operation_state(operation_id, phase="error", status=self._desktop_text("原来的输入位置已经变化，请重新选择后重试。", "The original input field changed. Select it and try again."))
                        return
                    with self._operation_lock:
                        if not self._operation_current(operation_id):
                            return
                        self._status_overlay.show_polishing(raw_text)
                    edited = self._handle_edit_command(command, tone, app_info, operation_id=operation_id, target_field=target_field)
                    with self._operation_lock:
                        if not self._operation_current(operation_id):
                            return
                        if edited:
                            self._status_overlay.show_done(command)
                        else:
                            self._status_overlay.hide(delay=0.4)
                        if self._main_state["phase"] not in {"done", "error"}:
                            self._update_main_state(phase="done", status=self._desktop_text("编辑处理已结束。", "Editing finished."))
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
            entry = self._retain_dictation(original_transcription, text, app_info, duration, operation_id=operation_id)
            if entry is None:
                return

            # Polish with LLM
            if combined_llm_path:
                with self._operation_lock:
                    if not self._update_operation_state(operation_id, phase="translating", status=self._desktop_text("正在润色并翻译…", "Polishing and translating…")):
                        return
                    self._status_overlay.show_polishing(text)
                target = self.config.get("translate_target", "en")
                logger.info("Polishing and translating to %s...", target)
                polish_scene_id = None
                scene_template = None
                if self.config.get("scene_prompts_enabled", True):
                    polish_scene_id = active_scene_id
                    overrides = self.config.get("scene_prompts") or {}
                    scene_template = overrides.get(polish_scene_id) if isinstance(overrides, dict) else None
                polished = polish_engine.polish_and_translate(
                    text,
                    tone=tone,
                    target_lang=target,
                    auto_punctuation=self.config.get("auto_punctuation", True),
                    filler_removal=self.config.get("filler_removal", True),
                    scene=polish_scene_id,
                    scene_template=scene_template,
                    hotwords=active_hotwords.terms,
                )
                with self._operation_lock:
                    if not self._operation_current(operation_id):
                        return
                    if self._observe_llm_status(polish_engine):
                        llm_fallback_used = True
                        llm_fallback_error = polish_engine.last_error
                marks["polished"] = time.perf_counter()
                marks["translated"] = marks["polished"]
            else:
                if self.config["polish_enabled"]:
                    with self._operation_lock:
                        if not self._update_operation_state(operation_id, phase="polishing", status=self._desktop_text("正在润色…", "Polishing…")):
                            return
                        self._status_overlay.show_polishing(text)
                    logger.info("Polishing text...")
                    polish_scene_id = None
                    scene_template = None
                    if self.config.get("scene_prompts_enabled", True):
                        polish_scene_id = active_scene_id
                        overrides = self.config.get("scene_prompts") or {}
                        scene_template = overrides.get(polish_scene_id) if isinstance(overrides, dict) else None
                    polished = polish_engine.polish(
                        text,
                        tone=tone,
                        language=self.config["language"],
                        auto_punctuation=self.config.get("auto_punctuation", True),
                        filler_removal=self.config.get("filler_removal", True),
                        scene=polish_scene_id,
                        scene_template=scene_template,
                        hotwords=active_hotwords.terms,
                    )
                    with self._operation_lock:
                        if not self._operation_current(operation_id):
                            return
                        if self._observe_llm_status(polish_engine):
                            llm_fallback_used = True
                            llm_fallback_error = polish_engine.last_error
                else:
                    polished = text
                marks["polished"] = time.perf_counter()

                # Plugin: post_polish
                if self.config.get("plugins_enabled"):
                    polished = self._plugin_manager.run_hook("post_polish", polished) or polished

                # Translate if enabled
                if self.config.get("translate_enabled", False):
                    if not self._update_operation_state(operation_id, phase="translating", status=self._desktop_text("正在翻译…", "Translating…")):
                        return
                    target = self.config.get("translate_target", "en")
                    with self._operation_lock:
                        if not self._operation_current(operation_id):
                            return
                        self._status_overlay.show_polishing(polished)
                    logger.info(f"Translating to {target}...")
                    polished = polish_engine.translate(
                        polished,
                        target_lang=target,
                        hotwords=active_hotwords.terms,
                    )
                    with self._operation_lock:
                        if not self._operation_current(operation_id):
                            return
                        if self._observe_llm_status(polish_engine):
                            llm_fallback_used = True
                            llm_fallback_error = polish_engine.last_error
                marks["translated"] = time.perf_counter()

            logger.info(f"Final: {polished}")
            if not self._operation_current(operation_id):
                return

            # Plugin: pre_insert
            if self.config.get("plugins_enabled"):
                before_plugin = polished
                polished = self._plugin_manager.run_hook("pre_insert", polished)
                if polished is None:
                    with self._operation_lock:
                        if self._commit_dictation_text(entry, before_plugin, operation_id, outcome="saved"):
                            self._status_overlay.hide(delay=0.4)
                    return

            # Show the final text in the overlay before inserting
            final_status = self._desktop_text("原始转写已保留。请在权限与模型准备中检查润色模型。",
                                              "Transcription kept. Review the polishing model in Permissions and Models.") if llm_fallback_used and not insert_result else None
            if not self._commit_dictation_text(entry, polished, operation_id,
                                               outcome="saved" if not insert_result else None,
                                               status=final_status, show_done=True):
                return
            if not insert_result:
                return

            # Insert text at cursor
            if not self._begin_delivery(operation_id):
                return
            if target_field is not None and not prepare_unchanged_target(target_field):
                self._finish_dictation_delivery(entry, False, operation_id=operation_id)
                self._update_operation_state(operation_id, status=self._desktop_text("原来的输入位置已经变化，文本已保留。请选择目标后再次插入。",
                                                                  "The original field changed. Text kept. Choose a target and insert again."))
                return
            if not self._operation_current(operation_id):
                return
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
                target_pid=app_info.get("pid"),
            )
            self._finish_dictation_delivery(entry, inserted_ok, operation_id=operation_id)
            if not inserted_ok:
                self._notify_insert_failed(app_info)
                return
            marks["inserted"] = time.perf_counter()
            self._show_successful_insert_feedback(app_info, polished, llm_fallback_used, llm_fallback_error)
            self._remember_last_insertion(polished, app_info)
            self._start_edit_observation(
                raw_text=raw_text,
                inserted_text=polished,
                app_info=app_info,
                scene_id=active_scene_id,
            )

            # Plugin: post_insert
            if self.config.get("plugins_enabled"):
                self._plugin_manager.run_hook("post_insert", polished)

            marks["history_saved"] = time.perf_counter()
        except Exception as e:
            with self._operation_lock:
                if not self._operation_current(operation_id):
                    return
                logger.error(f"Processing failed: {e}")
                if entry is not None and entry.get("outcome") == "pending":
                    self._commit_dictation_text(entry, entry["polished"], operation_id, outcome="saved")
                self._show_overlay_error(t("overlay_processing_failed"), auto_hide_after=3.0)
                rumps.notification("SpeakType", t("notif_error"), str(e))
                self._update_main_state(phase="error", status=str(e))
        finally:
            marks["end"] = time.perf_counter()
            self._log_pipeline_latency(marks)
            self._finish_operation(operation_id)
            if recording_path is not None:
                Path(recording_path).unlink(missing_ok=True)

    def _retain_dictation(self, raw_text, final_text, app_info, duration=0, *, operation_id=None):
        with self._operation_lock:
            if operation_id is not None and not self._operation_current(operation_id):
                return None
            entry = {"raw": raw_text, "polished": final_text, "outcome": "pending",
                     "operation_id": self._operation_id if operation_id is None else operation_id}
            with self._dictation_lock:
                self._latest_dictation = entry
            self._update_main_state(raw=raw_text, final=final_text)
            if self.config.get("history_enabled", True):
                entry["id"] = self.history.add(
                    raw_text=raw_text, polished_text=final_text,
                    app_name=app_info.get("name", ""), duration_sec=duration, outcome="pending")
            return entry

    def _commit_dictation_text(self, entry, text, operation_id, *, outcome=None, status=None, show_done=False):
        with self._operation_lock:
            if not self._operation_current(operation_id):
                return False
            entry["polished"] = text
            if entry.get("id"):
                self.history.update_text(entry["id"], text)
            with self._dictation_lock:
                latest = self._latest_dictation
                if latest is entry or (latest and (
                    (entry.get("id") and latest.get("id") == entry["id"])
                    or latest.get("operation_id") == operation_id
                )):
                    latest["polished"] = text
            if show_done:
                self._status_overlay.show_done(text)
            if outcome is None:
                self._update_main_state(final=text)
            else:
                self._finish_dictation_delivery(entry, False, outcome=outcome, operation_id=operation_id)
            if status is not None:
                self._update_main_state(status=status)
            return True

    def _finish_dictation_delivery(self, entry, inserted, outcome=None, *, operation_id=None):
        with self._operation_lock:
            if operation_id is not None and not self._operation_current(operation_id):
                return False
            return self._finish_dictation_delivery_locked(entry, inserted, outcome)

    def _finish_dictation_delivery_locked(self, entry, inserted, outcome=None):
        diagnostic = get_last_insert_diagnostic()
        if outcome is None:
            outcome = "failed"
            if inserted:
                outcome = "inserted" if diagnostic and diagnostic.verified else "sent"
        entry["outcome"] = outcome
        with self._dictation_lock:
            if self._latest_dictation and (
                self._latest_dictation is entry
                or (entry.get("id") and self._latest_dictation.get("id") == entry["id"])
                or (entry.get("operation_id") is not None and self._latest_dictation.get("operation_id") == entry["operation_id"])
            ):
                self._latest_dictation["outcome"] = outcome
        if entry.get("id"):
            self.history.set_outcome(entry["id"], outcome)
        messages = {
            "saved": self._desktop_text("文本已保存，可以编辑、复制或插入。", "Text saved. Edit, copy, or insert it."),
            "inserted": self._desktop_text("文字已插入目标应用。", "Text inserted into the target app."),
            "sent": self._desktop_text("已发送输入，请检查目标应用；结果仍可复制。", "Input sent. Check the target; text remains available to copy."),
            "failed": self._desktop_text("插入失败，文本已保留。可以复制，或重新选择输入框。", "Insertion failed. Text kept. Copy it or select another field."),
            "cancelled": self._desktop_text("已取消，现有文本已保留。", "Cancelled. Available text has been kept."),
        }
        self._update_main_state(phase="error" if outcome == "failed" else "cancelled" if outcome == "cancelled" else "done",
                                raw=entry.get("raw", ""), final=entry.get("polished", ""),
                                status=messages[outcome])
        return True

    def _copy_last_dictation(self, _):
        with self._dictation_lock:
            entry = dict(self._latest_dictation or {})
        text = entry.get("polished") or entry.get("raw", "")
        if not text:
            self._show_overlay_notice(t("notif_no_recent_dictation"))
            return
        pb = AppKit.NSPasteboard.generalPasteboard()
        pb.clearContents()
        if not pb.setString_forType_(text, AppKit.NSPasteboardTypeString):
            raise RuntimeError("Unable to copy dictation to the clipboard")
        self._show_overlay_notice(t("notif_text_copied"))

    def _insert_last_dictation(self, _):
        if self.recorder.is_recording or self._is_processing:
            return
        with self._dictation_lock:
            entry = dict(self._latest_dictation or {})
        text = entry.get("polished") or entry.get("raw", "")
        if not text:
            self._show_overlay_notice(t("notif_no_recent_dictation"))
            return
        self._remember_external_app()
        self._main_insert(text)

    def _remember_last_insertion(self, text: str, app_info: dict | None = None):
        snapshot = capture_verified_insertion(text)
        if snapshot is None:
            self._clear_last_insertion()
            return
        self._last_insertion_snapshot = snapshot
        self._last_insertion_text = text or None
        self._last_insertion_app = (app_info or {}).get("name", "") or None
        self._last_insertion_bundle_id = (app_info or {}).get("bundle_id", "") or None

    def _clear_last_insertion(self):
        self._last_insertion_text = None
        self._last_insertion_snapshot = None
        self._last_insertion_app = None
        self._last_insertion_bundle_id = None

    def _handle_undo_last(self) -> bool:
        """Voice "undo that" — delete the most recently inserted text."""
        self._cancel_edit_observation()
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

        if not undo_verified_insertion(self._last_insertion_snapshot):
            logger.info("Undo skipped because the focused text or cursor no longer matches the verified insertion")
            if self.config["sound_feedback"]:
                _play_sound("Basso")
            return False

        self._clear_last_insertion()
        return True

    def _handle_edit_command(self, command: str, tone: str, app_info: dict | None = None,
                             operation_id=None, target_field=None) -> bool:
        operation_id = self._new_operation() if operation_id is None else operation_id
        entry = None
        try:
            selected = get_selected_text()
            if not selected:
                logger.info("No text selected for edit command")
                if self.config["sound_feedback"]:
                    _play_sound("Basso")
                return False
            logger.info(f"Edit command: '{command}' on: '{selected[:50]}...'")
            target = app_info or get_active_app()
            entry = self._retain_dictation(selected, selected, target, operation_id=operation_id)
            if entry is None:
                return False
            polish_engine = self._new_polish_engine()
            result = polish_engine.edit_text(command, selected, tone)
            with self._operation_lock:
                if not self._operation_current(operation_id):
                    return False
                if self._observe_llm_status(polish_engine):
                    self._commit_dictation_text(entry, selected, operation_id, outcome="saved")
                    self._update_main_state(phase="error", status=polish_engine.last_error)
                    return False
                self._commit_dictation_text(entry, result, operation_id)
            if not self._begin_delivery(operation_id):
                return False
            if target_field is not None and not prepare_unchanged_target(target_field):
                self._finish_dictation_delivery(entry, False, operation_id=operation_id)
                return False
            inserted = insert_text(result, method=self.config["insert_method"],
                                   app_name=target.get("name", ""),
                                   bundle_id=target.get("bundle_id", ""), target_pid=target.get("pid"))
            if not self._finish_dictation_delivery(entry, inserted, operation_id=operation_id):
                return False
            if inserted:
                self._remember_last_insertion(result, target)
            else:
                self._notify_insert_failed(target)
            return inserted
        except Exception as e:
            logger.error(f"Edit command failed: {e}")
            with self._operation_lock:
                if self._operation_current(operation_id):
                    if entry is not None:
                        self._commit_dictation_text(entry, entry["polished"], operation_id, outcome="saved")
                    self._update_main_state(phase="error", status=str(e))
            return False
        finally:
            self._finish_operation(operation_id)

    def _open_settings(self, _):
        """Open the native Settings window."""
        from .settings_window import SettingsWindowController, is_auto_start_enabled

        self._settings_controller = _show_or_create_window_controller(
            getattr(self, "_settings_controller", None),
            lambda: SettingsWindowController(
                config={**self.config, "auto_start": is_auto_start_enabled()},
                on_save=self._apply_settings,
            ),
        )

    def _open_dict(self, _):
        """Open the dictionary, snippets & corrections editor."""
        from .dict_window import DictWindowController

        self._dict_controller = _show_or_create_window_controller(
            getattr(self, "_dict_controller", None),
            lambda: DictWindowController(self.snippets, self.corrections),
        )

    def _apply_settings(self, new_config: dict):
        """Apply new settings from the Settings window."""
        if self._quitting:
            return
        if self._main_controller and not self._is_processing and not self.recorder.is_recording:
            edited = self._main_controller.get_final_text()
            if edited:
                self._update_latest_final_text(edited)
        if self._is_processing or self.recorder.is_recording:
            self._main_cancel()
        old_hotkey = self.config.get("hotkey")
        old_asr = self.config.get("asr_model")
        old_mode = self.config.get("dictation_mode")
        old_ui_lang = self.config.get("ui_language", "zh")
        old_plugins_enabled = self.config.get("plugins_enabled", False)
        old_plugins_dir = self.config.get("plugins_dir", "")

        self.config.update(new_config)
        save_config(self.config)
        self.history.max_entries = self.config["history_max_entries"]

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
            with self._operation_lock:
                self.asr = ASREngine(
                    model_name=self.config["asr_model"],
                    backend="qwen",
                    whisper_model="base",
                )
                self._asr_engines.add(self.asr)
                self._engine_thread = None
                self._engine_error = ""
                self._update_main_state(phase="idle", ready=False, busy=False,
                                        status=self._desktop_text("语音模型已更改，正在检查准备状态。", "Speech model changed. Checking readiness."))

        # Update polish engine
        self.polish_engine = PolishEngine(
            model=self.config["llm_model"],
            ollama_url=self.config["ollama_url"],
        )
        self._polish_engines.add(self.polish_engine)
        if self.config.get("polish_enabled") or self.config.get("translate_enabled", False):
            self._llm_unavailable_notified = False
            self.polish_engine.prewarm_async()

        # Update recorder device
        self.recorder.device = validate_device(self.config.get("audio_device"))
        observer = getattr(self, "_edit_observer", None)
        if observer is not None and hasattr(observer, "configure"):
            observer.configure(
                observation_seconds=self.config.get("hotword_observation_seconds", 18),
                stable_seconds=self.config.get("hotword_observation_stable_seconds", 1.2),
            )

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
        self._update_hotword_menu_title()

        if new_ui_lang != old_ui_lang:
            if self._main_controller:
                self._main_controller.flush_edits()
                self._main_controller.dispose()
                self._main_controller = None
                self._show_main_window(None)
            help_controller = getattr(self, "_help_controller", None)
            if help_controller:
                help_controller.close()
                self._help_controller = None
        if self._setup_center:
            self._setup_center.apply_config(dict(self.config))
        self._refresh_main_readiness()

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
        self._stats_controller = _show_or_create_window_controller(
            getattr(self, "_stats_controller", None),
            lambda: StatsWindowController(self.history),
        )

    def _show_history(self, _):
        from .history_window import HistoryWindowController
        self._history_controller = _show_or_create_window_controller(
            self._history_controller,
            lambda: HistoryWindowController(self.history),
        )

    def _show_diagnostics(self, _):
        if self._quitting:
            return
        from .diagnostics_window import DiagnosticsWindowController
        self._diagnostics_controller = _show_or_create_window_controller(
            getattr(self, "_diagnostics_controller", None),
            lambda: DiagnosticsWindowController(
                config=self.config,
                asr_engine=self.asr,
            ),
        )

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
        self._start_model_worker(_do_test, name="SpeakTypeMicrophoneTest")

    def _reload_config(self, _):
        self.config = load_config()
        rumps.notification("SpeakType", t("notif_config_reloaded"), t("notif_config_reloaded_body"))

    def _open_config(self, _):
        subprocess.run(["open", str(CONFIG_DIR)])

    def _open_hotwords_window(self, _):
        from .hotwords_window import HotwordsWindowController

        self._hotwords_controller = _show_or_create_window_controller(
            getattr(self, "_hotwords_controller", None),
            lambda: HotwordsWindowController(self.hotwords),
        )

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

        self._start_model_worker(_do_check, name="SpeakTypeUpdateCheck")

    def _show_about(self, _):
        rumps.notification(
            t("menu_about"),
            t("notif_about_subtitle", version=APP_VERSION),
            about_notification_body(self.asr.get_backend_info()),
        )

    def _resume_after_quit(self, status):
        with self._operation_lock:
            self._quitting = False
            self._update_main_state(status=status)
        readiness_timer = getattr(self, "_readiness_timer", None)
        if readiness_timer:
            readiness_timer.start()
        self._start_permission_restart_watcher()
        if self._setup_center:
            self._setup_center.resume_after_shutdown()
        if self._diagnostics_controller:
            self._diagnostics_controller.resume_after_shutdown()
        self._refresh_main_readiness()

    def _prepare_to_quit(self, timeout=60.0):
        deadline = time.monotonic() + timeout
        self._flush_main_edits()
        with self._operation_lock:
            self._quitting = True
            self._pending_trial = False
            delivering = self._delivery_operation_id == self._operation_id or self._main_state.get("phase") == "delivering"
        readiness_timer = getattr(self, "_readiness_timer", None)
        if readiness_timer:
            readiness_timer.stop()
        self._permission_watch_stop.set()
        self._release_guard_stop.set()
        self._cancel_edit_observation()
        if self._setup_center:
            self._setup_center.shutdown()
        if self._diagnostics_controller:
            self._diagnostics_controller.shutdown()
        if delivering:
            worker = self._processing_thread
            while worker is not None and worker.is_alive() and time.monotonic() < deadline:
                NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.02))
                worker.join(timeout=0.02)
            if worker is not None and worker.is_alive():
                self._resume_after_quit(self._desktop_text(
                    "文字仍在插入，应用将保持运行。完成后可以再次退出。",
                    "Text insertion is still running. SpeakType will stay open. Quit again after it finishes."))
                return False
            with self._operation_lock:
                with self._dictation_lock:
                    entry = dict(self._latest_dictation or {})
                if entry.get("outcome") == "pending":
                    self._finish_dictation_delivery(entry, False)
        else:
            self._main_cancel()
        with self._operation_lock:
            self._operation_cancel.set()
        if not self._wait_for_model_workers(deadline):
            self._resume_after_quit(self._desktop_text(
                "模型任务仍在结束，应用将保持运行。完成后可以再次退出。",
                "Model tasks are still finishing. SpeakType will stay open. Quit again after they finish."))
            return False
        return True

    def _quit(self, _):
        if self._quitting:
            return
        if not self._prepare_to_quit():
            return
        self._finish_quit()

    def _finish_quit(self):
        if self.recorder.is_recording:
            self.recorder.set_stream_callback(None)
            self.recorder.stop_audio()
        readiness_timer = getattr(self, "_readiness_timer", None)
        if readiness_timer:
            readiness_timer.stop()
        if self._setup_center:
            self._setup_center.shutdown()
        self._cancel_edit_observation()
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


def _record_running_build(config: dict):
    fingerprint = get_bundle_fingerprint()
    changed = config.get("last_seen_version") != APP_VERSION or config.get("permission_restart_pending_after_refresh")
    changed = changed or fingerprint and config.get("last_seen_bundle_fingerprint") != fingerprint
    if changed:
        config["last_seen_version"] = APP_VERSION
        config[PERMISSION_RESTART_PENDING_KEY] = False
        if fingerprint:
            config["last_seen_bundle_fingerprint"] = fingerprint
        save_config(config)


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
    _record_running_build(config)

    logger.info("Starting SpeakType v%s...", APP_VERSION)
    app = SpeakTypeApp()
    app.run()
