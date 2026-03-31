"""Main SpeakType application - menubar app with push-to-talk voice input."""

import os
import sys
import time
import threading
import logging
import subprocess
import rumps

from .config import load_config, save_config, load_custom_dictionary
from .audio import AudioRecorder
from .asr import ASREngine
from .polish import PolishEngine
from .inserter import insert_text, replace_selection
from .hotkey import HotkeyListener
from .history import DictationHistory
from .context import get_active_app, get_tone_for_app, get_selected_text
from .commands import process_punctuation_commands, detect_edit_command

logger = logging.getLogger("speaktype")

# Status icons (using emoji as menubar title)
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
        self.hotkey_listener = None
        self._recording_start_time = 0
        self._is_processing = False
        self._setup_done = False
        self._status_item = rumps.MenuItem("Status: Initializing...")

        polish_item = rumps.MenuItem("Polish Text", callback=self._toggle_polish)
        polish_item.state = self.config["polish_enabled"]
        voice_cmd_item = rumps.MenuItem("Voice Commands", callback=self._toggle_voice_commands)
        voice_cmd_item.state = self.config["voice_commands_enabled"]
        tone_item = rumps.MenuItem("Context-Aware Tone", callback=self._toggle_context_tone)
        tone_item.state = self.config["context_aware_tone"]

        self.menu = [
            rumps.MenuItem("SpeakType v1.0"),
            None,
            rumps.MenuItem(f"Hotkey: {self._hotkey_display()}"),
            self._status_item,
            None,
            polish_item,
            voice_cmd_item,
            tone_item,
            None,
            rumps.MenuItem("History & Stats", callback=self._show_stats),
            rumps.MenuItem("Test Microphone", callback=self._test_mic),
            rumps.MenuItem("Reload Config", callback=self._reload_config),
            None,
            rumps.MenuItem("Open Config Folder", callback=self._open_config),
            rumps.MenuItem("Quit SpeakType", callback=self._quit),
        ]

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
        def init_engines():
            logger.info("Loading ASR engine...")
            self._status_item.title = "Status: Loading ASR model..."
            try:
                self.asr.load()
                logger.info("ASR engine loaded")
            except Exception as e:
                logger.error(f"ASR load failed: {e}")
                self._status_item.title = f"Status: ASR Error"
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

    def _on_hotkey_release(self):
        if not self.recorder.is_recording:
            return
        duration = time.time() - self._recording_start_time
        logger.info(f"Recording stopped after {duration:.1f}s")
        if self.config["sound_feedback"]:
            _play_sound("Pop")
        self.title = ICON_PROCESSING
        self._is_processing = True
        audio_path = self.recorder.stop()
        if not audio_path:
            logger.info("No audio captured")
            self.title = ICON_IDLE
            self._is_processing = False
            return
        threading.Thread(
            target=self._process_audio,
            args=(audio_path, duration),
            daemon=True,
        ).start()

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
                import os
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
        from .config import CONFIG_DIR
        subprocess.run(["open", str(CONFIG_DIR)])

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
    """Check and prompt for required macOS permissions."""
    issues = []

    # Check microphone - try to open an audio stream briefly
    try:
        import sounddevice as sd
        with sd.InputStream(samplerate=16000, channels=1, dtype="float32", blocksize=1600):
            pass
    except Exception:
        issues.append("Microphone")

    # Check accessibility - try to detect if pynput will work
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
        print(f"\n⚠️  Missing permissions: {missing}")
        print(f"   Go to: System Settings → Privacy & Security → {missing}")
        print(f"   Add your terminal app to the allowed list, then restart SpeakType.\n")
        # Also show a system notification
        subprocess.run([
            "osascript", "-e",
            f'display notification "Grant {missing} access in System Settings → Privacy & Security" with title "SpeakType Permissions Needed"'
        ], capture_output=True)
        # Open System Settings
        subprocess.run(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy"], capture_output=True)


def run():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    _check_permissions()

    logger.info("Starting SpeakType...")
    app = SpeakTypeApp()
    app.run()
