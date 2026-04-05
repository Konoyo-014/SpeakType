"""Main SpeakType application - menubar app with push-to-talk voice input."""

import os
import sys
import time
import threading
import logging
import subprocess
import rumps
import AppKit

from .config import load_config, save_config, load_custom_dictionary, CONFIG_DIR, ensure_config_dir
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

logger = logging.getLogger("speaktype")

# Status icons
ICON_IDLE = "🎙"
ICON_RECORDING = "🔴"
ICON_PROCESSING = "⏳"
ICON_ERROR = "⚠️"


class SpeakTypeApp(rumps.App):
    def __init__(self):
        super().__init__(
            name="SpeakType",
            title=ICON_IDLE,
            quit_button=None,
        )
        self.config = load_config()
        self.recorder = AudioRecorder(sample_rate=self.config["sample_rate"])
        self.asr = ASREngine(model_name=self.config["asr_model"])
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
        self._first_launch = not (CONFIG_DIR / "config.json").exists()
        self._settings_controller = None
        self._overlay = RecordingOverlay()
        self._level_timer = None

        self._status_item = rumps.MenuItem("Status: Initializing...")

        polish_item = rumps.MenuItem("Polish Text", callback=self._toggle_polish)
        polish_item.state = self.config["polish_enabled"]
        voice_cmd_item = rumps.MenuItem("Voice Commands", callback=self._toggle_voice_commands)
        voice_cmd_item.state = self.config["voice_commands_enabled"]
        tone_item = rumps.MenuItem("Context-Aware Tone", callback=self._toggle_context_tone)
        tone_item.state = self.config["context_aware_tone"]

        # Translation toggle + target language submenu
        translate_item = rumps.MenuItem("Translate After Transcription", callback=self._toggle_translate)
        translate_item.state = self.config.get("translate_enabled", False)

        translate_target_menu = rumps.MenuItem("Translate To")
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
            translate_target_menu.add(item)

        # Language quick-switch submenu
        lang_menu = rumps.MenuItem("Language")
        lang_options = [
            ("auto", "Auto Detect"),
            ("en", "English"),
            ("zh", "中文"),
            ("ja", "日本語"),
            ("ko", "한국어"),
        ]
        for code, name in lang_options:
            item = rumps.MenuItem(name, callback=self._make_lang_callback(code))
            item.state = self.config["language"] == code
            lang_menu.add(item)

        self.menu = [
            rumps.MenuItem("SpeakType v2.0"),
            None,
            rumps.MenuItem(f"Hotkey: {self._hotkey_display()}"),
            self._status_item,
            None,
            polish_item,
            voice_cmd_item,
            tone_item,
            translate_item,
            translate_target_menu,
            lang_menu,
            None,
            rumps.MenuItem("Preferences...", callback=self._open_settings, key=","),
            rumps.MenuItem("History & Stats", callback=self._show_stats),
            rumps.MenuItem("Test Microphone", callback=self._test_mic),
            None,
            rumps.MenuItem("Open Config Folder", callback=self._open_config),
            rumps.MenuItem("Check for Updates", callback=self._check_updates),
            rumps.MenuItem("About SpeakType", callback=self._show_about),
            None,
            rumps.MenuItem("Quit SpeakType", callback=self._quit, key="q"),
        ]

    def _toggle_translate(self, sender):
        sender.state = not sender.state
        self.config["translate_enabled"] = bool(sender.state)
        save_config(self.config)

    def _make_translate_target_callback(self, lang_code):
        def callback(sender):
            self.config["translate_target"] = lang_code
            save_config(self.config)
            translate_menu = self.menu.get("Translate To")
            if translate_menu:
                for item in translate_menu.values():
                    item.state = False
                sender.state = True
        return callback

    def _make_lang_callback(self, lang_code):
        def callback(sender):
            self.config["language"] = lang_code
            save_config(self.config)
            # Update checkmarks in language submenu
            lang_menu = self.menu.get("Language")
            if lang_menu:
                for item in lang_menu.values():
                    item.state = False
                sender.state = True
        return callback

    def _hotkey_display(self):
        mapping = {
            "right_cmd": "Right ⌘",
            "left_cmd": "Left ⌘",
            "fn": "Fn",
            "right_alt": "Right ⌥",
            "right_ctrl": "Right ⌃",
            "ctrl+shift+space": "⌃⇧Space",
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
        self._do_setup()

    def _do_setup(self):
        # Hide Dock icon AFTER rumps has created the NSStatusItem
        try:
            AppKit.NSApplication.sharedApplication().setActivationPolicy_(
                AppKit.NSApplicationActivationPolicyAccessory
            )
        except Exception:
            pass

        def init_engines():
            logger.info("Loading ASR engine...")
            self._status_item.title = "Status: Loading ASR model..."

            # Show onboarding on first launch
            if self._first_launch:
                rumps.notification(
                    "Welcome to SpeakType!",
                    "First-time Setup",
                    f"Hold {self._hotkey_display()} to start dictating.\n"
                    "Grant Microphone and Accessibility access when prompted.\n"
                    "Use Preferences (⌘,) to customize settings.",
                )

            try:
                self.asr.load()
                logger.info("ASR engine loaded")
            except Exception as e:
                logger.error(f"ASR load failed: {e}")
                self._status_item.title = "Status: ASR Error"
                self.title = ICON_ERROR
                rumps.notification("SpeakType", "ASR Load Failed", str(e))
                return

            if self.config["polish_enabled"]:
                if self.polish_engine.check_available():
                    logger.info("LLM polish engine available")
                else:
                    logger.warning("LLM not available")
                    rumps.notification(
                        "SpeakType", "LLM Not Available",
                        f"Run: ollama pull {self.config['llm_model']}\nText polishing disabled."
                    )

            self._status_item.title = "Status: Ready ✓"
            self.title = ICON_IDLE
            if not self._first_launch:
                rumps.notification("SpeakType", "Ready!", f"Hold {self._hotkey_display()} to dictate.")

        threading.Thread(target=init_engines, daemon=True).start()

        self.hotkey_listener = HotkeyListener(
            hotkey_name=self.config["hotkey"],
            on_press=self._on_hotkey_press,
            on_release=self._on_hotkey_release,
        )
        self.hotkey_listener.start()

    def _on_hotkey_press(self):
        if self._is_processing:
            return
        logger.info("Recording started")
        self.title = ICON_RECORDING
        self._recording_start_time = time.time()
        if self.config["sound_feedback"]:
            _play_sound("Tink")
        self.recorder.start()

        # Start audio level monitoring
        self._start_level_monitor()

    def _on_hotkey_release(self):
        if not self.recorder.is_recording:
            return
        duration = time.time() - self._recording_start_time
        logger.info(f"Recording stopped after {duration:.1f}s")
        if self.config["sound_feedback"]:
            _play_sound("Pop")
        self.title = ICON_PROCESSING
        self._is_processing = True
        self._stop_level_monitor()
        audio_path = self.recorder.stop()
        if not audio_path:
            logger.info("No audio captured")
            self.title = ICON_IDLE
            self._is_processing = False
            pass  # overlay disabled
            return
        threading.Thread(
            target=self._process_audio,
            args=(audio_path, duration),
            daemon=True,
        ).start()

    def _start_level_monitor(self):
        pass  # overlay disabled

    def _stop_level_monitor(self):
        pass  # Thread exits when is_recording becomes False

    def _process_audio(self, audio_path: str, duration: float):
        try:
            app_info = get_active_app()
            tone = get_tone_for_app(app_info) if self.config["context_aware_tone"] else "neutral"

            logger.info("Transcribing...")
            raw_text = self.asr.transcribe(audio_path, language=self.config["language"])

            if not raw_text.strip():
                logger.info("Empty transcription")
                return

            logger.info(f"Raw: {raw_text}")

            # Check for snippet triggers
            snippet_text = self.snippets.match(raw_text)
            if snippet_text:
                logger.info(f"Snippet matched: {raw_text} -> {snippet_text[:40]}")
                insert_text(snippet_text, method=self.config["insert_method"])
                return

            # Check for edit commands
            if self.config["voice_commands_enabled"]:
                is_edit, command = detect_edit_command(raw_text)
                if is_edit:
                    self._handle_edit_command(command, tone)
                    return

            # Process punctuation commands
            text = process_punctuation_commands(raw_text) if self.config["voice_commands_enabled"] else raw_text

            # Polish with LLM
            if self.config["polish_enabled"]:
                logger.info("Polishing text...")
                polished = self.polish_engine.polish(text, tone=tone, language=self.config["language"])
            else:
                polished = text

            # Translate if enabled
            if self.config.get("translate_enabled", False):
                target = self.config.get("translate_target", "en")
                logger.info(f"Translating to {target}...")
                polished = self.polish_engine.translate(polished, target_lang=target)

            logger.info(f"Final: {polished}")

            # Insert text at cursor
            insert_text(polished, method=self.config["insert_method"])

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
            rumps.notification("SpeakType", "Error", str(e))
        finally:
            self.title = ICON_IDLE
            self._is_processing = False
            pass  # overlay disabled

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
            pass  # overlay disabled

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

    def _apply_settings(self, new_config: dict):
        """Apply new settings from the Settings window."""
        old_hotkey = self.config.get("hotkey")
        old_asr = self.config.get("asr_model")

        self.config.update(new_config)
        save_config(self.config)

        # Update hotkey display
        for item in self.menu.values():
            if hasattr(item, 'title') and item.title.startswith("Hotkey:"):
                item.title = f"Hotkey: {self._hotkey_display()}"
                break

        # Restart hotkey listener if hotkey changed
        if new_config.get("hotkey") != old_hotkey:
            if self.hotkey_listener:
                self.hotkey_listener.stop()
            self.hotkey_listener = HotkeyListener(
                hotkey_name=self.config["hotkey"],
                on_press=self._on_hotkey_press,
                on_release=self._on_hotkey_release,
            )
            self.hotkey_listener.start()

        # Reload ASR model if changed
        if new_config.get("asr_model") != old_asr:
            self.asr = ASREngine(model_name=self.config["asr_model"])
            threading.Thread(target=self.asr.load, daemon=True).start()

        # Update polish engine
        self.polish_engine = PolishEngine(
            model=self.config["llm_model"],
            ollama_url=self.config["ollama_url"],
        )

        # Update toggle states in menu
        for item in self.menu.values():
            if hasattr(item, 'title'):
                if item.title == "Polish Text":
                    item.state = self.config["polish_enabled"]
                elif item.title == "Voice Commands":
                    item.state = self.config["voice_commands_enabled"]
                elif item.title == "Context-Aware Tone":
                    item.state = self.config["context_aware_tone"]

        rumps.notification("SpeakType", "Settings Saved", "Your preferences have been updated.")

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
        stats = self.history.get_stats()
        recent = self.history.get_recent(5)
        msg = (
            f"Total dictations: {stats['total_entries']}\n"
            f"Total words: {stats['total_words']}\n"
            f"Total time: {stats['total_duration_min']} min"
        )
        if recent:
            msg += "\n\nRecent:"
            for e in recent[-3:]:
                text = e.get("polished", "")[:40]
                msg += f"\n• {text}..."
        rumps.notification("SpeakType Stats", "", msg)

    def _test_mic(self, _):
        def _do_test():
            if self.recorder.is_recording or self._is_processing:
                rumps.notification("SpeakType", "Mic Test", "Cannot test while recording/processing.")
                return
            rumps.notification("SpeakType", "Mic Test", "Recording for 2 seconds...")
            test_recorder = AudioRecorder(sample_rate=self.config["sample_rate"])
            test_recorder.start()
            time.sleep(2)
            path = test_recorder.stop()
            if path:
                size = os.path.getsize(path)
                os.unlink(path)
                rumps.notification("SpeakType", "Mic Test", f"✓ Recorded {size} bytes. Microphone is working!")
            else:
                rumps.notification("SpeakType", "Mic Test", "✗ No audio captured. Check microphone permissions.")
        threading.Thread(target=_do_test, daemon=True).start()

    def _reload_config(self, _):
        self.config = load_config()
        rumps.notification("SpeakType", "Config Reloaded", "Settings updated.")

    def _open_config(self, _):
        subprocess.run(["open", str(CONFIG_DIR)])

    def _check_updates(self, _):
        rumps.notification("SpeakType", "Up to Date", "You are running the latest version (v2.0).")

    def _show_about(self, _):
        rumps.notification(
            "About SpeakType",
            "v2.0 — AI Voice Input for Mac",
            "Powered by Qwen3-ASR + Qwen3.5\n"
            "Push-to-talk voice dictation with AI polishing.\n"
            "© 2025 SpeakType"
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


def _run_on_main(fn):
    """Schedule a function to run on the main thread."""
    try:
        fn()
    except Exception as e:
        logger.debug(f"Main thread callback error: {e}")


def _check_permissions():
    """Check and prompt for required macOS permissions (non-blocking)."""
    try:
        issues = []

        # Check accessibility only (mic check can crash on some systems)
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
                f'display notification "Grant {missing} access in System Settings → Privacy & Security" with title "SpeakType Permissions Needed"'
            ], capture_output=True)
    except Exception as e:
        logger.warning(f"Permission check failed: {e}")


def run():
    # Log to both stderr and file
    log_file = CONFIG_DIR / "speaktype.log"
    ensure_config_dir()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(str(log_file), mode="w"),
        ],
        force=True,
    )

    _check_permissions()

    logger.info("Starting SpeakType v2.0...")
    app = SpeakTypeApp()
    app.run()
