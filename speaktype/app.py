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

from .config import load_config, save_config, load_custom_dictionary, CONFIG_DIR, ensure_config_dir
from .i18n import t, set_language, get_language
from .audio import AudioRecorder
from .asr import ASREngine
from .polish import PolishEngine
from .inserter import insert_text, replace_selection
from .hotkey import HotkeyListener
from .history import DictationHistory
from .context import get_active_app, get_tone_for_app, get_selected_text
from .commands import process_punctuation_commands, detect_edit_command
from .overlay import RecordingOverlay
from .snippets import SnippetLibrary
from .devices import list_input_devices, validate_device
from .plugins import PluginManager
from .streaming import StreamingPreviewWindow, StreamingTranscriber

logger = logging.getLogger("speaktype")

# Status icons
ICON_IDLE = "\U0001f399"      # 🎙
ICON_RECORDING = "\U0001f534"  # 🔴
ICON_PROCESSING = "\u231b"     # ⏳
ICON_ERROR = "\u26a0\ufe0f"    # ⚠️


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
        )
        self.asr = ASREngine(
            model_name=self.config["asr_model"],
            backend=self.config.get("asr_backend", "qwen"),
            whisper_model=self.config.get("whisper_model", "base"),
        )
        self.polish_engine = PolishEngine(
            model=self.config["llm_model"],
            ollama_url=self.config["ollama_url"],
        )
        self.history = DictationHistory(max_entries=self.config["history_max_entries"])
        self.snippets = SnippetLibrary()
        self.hotkey_listener = None
        self._recording_start_time = 0
        self._is_processing = False
        self._setup_done = False
        self._first_launch = not self.config.get("setup_completed", False)
        self._settings_controller = None
        self._stats_controller = None
        self._dict_controller = None
        self._overlay = RecordingOverlay()
        self._level_timer = None

        # Streaming preview
        self._streaming_preview = StreamingPreviewWindow()
        self._streaming_transcriber = None

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
            rumps.MenuItem("SpeakType v2.0"),
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

            if self.config["polish_enabled"]:
                if self.polish_engine.check_available():
                    logger.info("LLM polish engine available")
                else:
                    logger.warning("LLM not available")
                    rumps.notification(
                        "SpeakType", t("notif_llm_unavail_title"),
                        t("notif_llm_unavail_body", model=self.config['llm_model']),
                    )

            # Load plugins
            if self.config.get("plugins_enabled", False):
                try:
                    self._plugin_manager.load_all()
                except Exception as e:
                    logger.warning(f"Plugin loading failed: {e}")

            self._set_status(t("status_ready"))
            self._set_title(ICON_IDLE)
            mode_str = t("notif_ready_mode_toggle") if self.config.get("dictation_mode") == "toggle" else t("notif_ready_mode_hold")
            rumps.notification("SpeakType", t("notif_ready_title"), t("notif_ready_body", mode_str=mode_str, hotkey=self._hotkey_display()))

        threading.Thread(target=init_engines, daemon=True).start()
        self._restart_hotkey_listener()

        # Delayed accessibility check — warn if pynput can't listen
        def _delayed_perm_check():
            import time
            time.sleep(5)
            if self.hotkey_listener and self.hotkey_listener._listener:
                if not self.hotkey_listener._listener.running:
                    logger.warning("Hotkey listener not running — accessibility may be missing")
                    rumps.notification(
                        "SpeakType",
                        t("notif_perm_missing_title"),
                        t("notif_perm_missing_body", missing=t("wizard_access_label")),
                    )
        threading.Thread(target=_delayed_perm_check, daemon=True).start()

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
        logger.info("Recording started")
        self.title = ICON_RECORDING
        self._recording_start_time = time.time()
        if self.config["sound_feedback"]:
            _play_sound("Tink")

        # Notify plugins
        if self.config.get("plugins_enabled"):
            self._plugin_manager.run_hook("on_recording_start")

        # Start streaming preview if enabled
        if self.config.get("streaming_preview", False) and self.asr._loaded:
            self._streaming_preview.show()
            self._streaming_transcriber = StreamingTranscriber(
                self.asr, self._streaming_preview
            )
            self.recorder.set_stream_callback(self._streaming_transcriber.feed_audio)
            self._streaming_transcriber.start(language=self.config["language"])
        else:
            self.recorder.set_stream_callback(None)

        self.recorder.start()

    def _stop_recording(self):
        duration = time.time() - self._recording_start_time
        logger.info(f"Recording stopped after {duration:.1f}s")
        if self.config["sound_feedback"]:
            _play_sound("Pop")
        self.title = ICON_PROCESSING
        self._is_processing = True

        # Notify plugins
        if self.config.get("plugins_enabled"):
            self._plugin_manager.run_hook("on_recording_stop")

        # Stop streaming preview
        streaming_text = ""
        if self._streaming_transcriber:
            streaming_text = self._streaming_transcriber.stop()
            self._streaming_transcriber = None
        self.recorder.set_stream_callback(None)

        audio_path = self.recorder.stop()
        if not audio_path:
            logger.info("No audio captured")
            self.title = ICON_IDLE
            self._is_processing = False
            self._streaming_preview.hide()
            return

        threading.Thread(
            target=self._process_audio,
            args=(audio_path, duration),
            daemon=True,
        ).start()

    def _start_level_monitor(self):
        pass  # overlay disabled

    def _stop_level_monitor(self):
        pass

    def _process_audio(self, audio_path: str, duration: float):
        try:
            app_info = get_active_app()
            tone = get_tone_for_app(app_info) if self.config["context_aware_tone"] else "neutral"

            # Plugin: pre_transcribe
            if self.config.get("plugins_enabled"):
                audio_path = self._plugin_manager.run_hook("pre_transcribe", audio_path) or audio_path

            logger.info("Transcribing...")

            # Update streaming preview
            if self._streaming_preview._visible:
                self._streaming_preview.update_text("Processing...")

            raw_text = self.asr.transcribe(audio_path, language=self.config["language"])

            if not raw_text.strip():
                logger.info("Empty transcription")
                self._streaming_preview.hide(delay=0.5)
                return

            logger.info(f"Raw: {raw_text}")

            # Plugin: post_transcribe
            if self.config.get("plugins_enabled"):
                raw_text = self._plugin_manager.run_hook("post_transcribe", raw_text) or raw_text

            # Check for snippet triggers
            snippet_text = self.snippets.match(raw_text)
            if snippet_text:
                logger.info(f"Snippet matched: {raw_text} -> {snippet_text[:40]}")
                insert_text(snippet_text, method=self.config["insert_method"])
                self._streaming_preview.hide(delay=0.3)
                return

            # Check for edit commands
            if self.config["voice_commands_enabled"]:
                is_edit, command = detect_edit_command(raw_text)
                if is_edit:
                    self._handle_edit_command(command, tone)
                    self._streaming_preview.hide(delay=0.3)
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

            # Polish with LLM
            if self.config["polish_enabled"]:
                logger.info("Polishing text...")
                polished = self.polish_engine.polish(text, tone=tone, language=self.config["language"])
            else:
                polished = text

            # Plugin: post_polish
            if self.config.get("plugins_enabled"):
                polished = self._plugin_manager.run_hook("post_polish", polished) or polished

            # Translate if enabled
            if self.config.get("translate_enabled", False):
                target = self.config.get("translate_target", "en")
                logger.info(f"Translating to {target}...")
                polished = self.polish_engine.translate(polished, target_lang=target)

            logger.info(f"Final: {polished}")

            # Update streaming preview with final text before hiding
            if self._streaming_preview._visible:
                self._streaming_preview.update_text(polished)

            # Plugin: pre_insert
            if self.config.get("plugins_enabled"):
                polished = self._plugin_manager.run_hook("pre_insert", polished)
                if polished is None:
                    self._streaming_preview.hide(delay=0.5)
                    return

            # Insert text at cursor
            insert_text(polished, method=self.config["insert_method"])

            # Plugin: post_insert
            if self.config.get("plugins_enabled"):
                self._plugin_manager.run_hook("post_insert", polished)

            # Hide streaming preview
            self._streaming_preview.hide(delay=0.8)

            # Save history
            if self.config["history_enabled"]:
                self.history.add(
                    raw_text=raw_text,
                    polished_text=polished,
                    app_name=app_info.get("name", ""),
                    duration_sec=duration,
                )
        except Exception as e:
            logger.error(f"Processing failed: {e}")
            rumps.notification("SpeakType", t("notif_error"), str(e))
        finally:
            self.title = ICON_IDLE
            self._is_processing = False

    def _handle_edit_command(self, command: str, tone: str):
        try:
            selected = get_selected_text()
            if not selected:
                logger.info("No text selected for edit command")
                if self.config["sound_feedback"]:
                    _play_sound("Basso")
                return
            logger.info(f"Edit command: '{command}' on: '{selected[:50]}...'")
            result = self.polish_engine.edit_text(command, selected, tone)
            replace_selection(result)
        except Exception as e:
            logger.error(f"Edit command failed: {e}")
        finally:
            self.title = ICON_IDLE
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
        """Open the dictionary & snippets editor."""
        from .dict_window import DictWindowController
        self._dict_controller = DictWindowController(self.snippets)
        self._dict_controller.show()

    def _apply_settings(self, new_config: dict):
        """Apply new settings from the Settings window."""
        old_hotkey = self.config.get("hotkey")
        old_asr = self.config.get("asr_model")
        old_backend = self.config.get("asr_backend")
        old_whisper = self.config.get("whisper_model")
        old_mode = self.config.get("dictation_mode")
        old_ui_lang = self.config.get("ui_language", "zh")

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
        if (new_config.get("asr_model") != old_asr or
                new_config.get("asr_backend") != old_backend or
                new_config.get("whisper_model") != old_whisper):
            self.asr = ASREngine(
                model_name=self.config["asr_model"],
                backend=self.config.get("asr_backend", "qwen"),
                whisper_model=self.config.get("whisper_model", "base"),
            )
            threading.Thread(target=self.asr.load, daemon=True).start()

        # Update polish engine
        self.polish_engine = PolishEngine(
            model=self.config["llm_model"],
            ollama_url=self.config["ollama_url"],
        )

        # Update recorder device
        self.recorder.device = validate_device(self.config.get("audio_device"))

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
        rumps.notification("SpeakType", t("notif_up_to_date_title"), t("notif_up_to_date_body"))

    def _show_about(self, _):
        rumps.notification(
            t("menu_about"),
            t("notif_about_subtitle"),
            f"Backend: {self.asr.get_backend_info()}\n"
            "\u00a9 2025 SpeakType"
        )

    def _quit(self, _):
        if self.hotkey_listener:
            self.hotkey_listener.stop()
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
        issues = []
        try:
            result = subprocess.run(
                ["osascript", "-e", 'tell application "System Events" to return name of first process whose frontmost is true'],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode != 0:
                issues.append("Accessibility")
        except Exception:
            issues.append("Accessibility")

        if issues:
            missing = " and ".join(issues)
            logger.warning(f"Missing permissions: {missing}")
            subprocess.run([
                "osascript", "-e",
                f'display notification "Grant {missing} access in System Settings \u2192 Privacy & Security" with title "SpeakType Permissions Needed"'
            ], capture_output=True)
    except Exception as e:
        logger.warning(f"Permission check failed: {e}")


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
            logging.FileHandler(str(log_file), mode="w", encoding="utf-8"),
        ],
        force=True,
    )

    _check_permissions()

    logger.info("Starting SpeakType v2.0...")
    app = SpeakTypeApp()
    app.run()
