"""Global hotkey listener for push-to-talk and toggle-to-talk modes."""

import threading
import logging
from pynput import keyboard

logger = logging.getLogger("speaktype.hotkey")

# Key mapping for configuration
KEY_MAP = {
    "right_cmd": keyboard.Key.cmd_r,
    "left_cmd": keyboard.Key.cmd_l,
    "right_alt": keyboard.Key.alt_r,
    "right_ctrl": keyboard.Key.ctrl_r,
    "fn": keyboard.Key.f13,  # Fn key often maps to F13 on macOS
    "ctrl+shift+space": None,  # Combination handled separately
    "f5": keyboard.Key.f5,
    "f6": keyboard.Key.f6,
}


class HotkeyListener:
    def __init__(self, hotkey_name="right_cmd", on_press=None, on_release=None,
                 mode="push_to_talk", on_toggle=None):
        """
        Args:
            hotkey_name: Key identifier from KEY_MAP or a combo like "ctrl+shift+space"
            on_press: Callback when key is pressed (push_to_talk mode)
            on_release: Callback when key is released (push_to_talk mode)
            mode: "push_to_talk" or "toggle"
            on_toggle: Callback for toggle mode — called with is_active: bool
        """
        self.hotkey_name = hotkey_name
        self.on_press_callback = on_press
        self.on_release_callback = on_release
        self.on_toggle_callback = on_toggle
        self.mode = mode
        self._listener = None
        self._is_pressed = False
        self._toggle_active = False
        self._running = False
        self._combo_keys = set()

    def start(self):
        if self._running:
            return
        self._running = True
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()
        logger.info(f"Hotkey listener started: {self.hotkey_name} (mode={self.mode})")

    def stop(self):
        self._running = False
        if self._listener:
            self._listener.stop()
            self._listener = None

    @property
    def is_active(self) -> bool:
        """Whether recording is active (works for both modes)."""
        if self.mode == "toggle":
            return self._toggle_active
        return self._is_pressed

    def _get_target_key(self):
        return KEY_MAP.get(self.hotkey_name)

    def _is_combo_hotkey(self):
        return "+" in self.hotkey_name

    def _on_press(self, key):
        if not self._running:
            return

        if self._is_combo_hotkey():
            self._combo_keys.add(self._normalize_key(key))
            if self._check_combo() and not self._is_pressed:
                self._is_pressed = True
                self._handle_press()
        else:
            target = self._get_target_key()
            if target and key == target and not self._is_pressed:
                self._is_pressed = True
                self._handle_press()

    def _on_release(self, key):
        if not self._running:
            return

        if self._is_combo_hotkey():
            normalized = self._normalize_key(key)
            self._combo_keys.discard(normalized)
            if self._is_pressed and not self._check_combo():
                self._is_pressed = False
                self._handle_release()
        else:
            target = self._get_target_key()
            if target and key == target and self._is_pressed:
                self._is_pressed = False
                self._handle_release()

    def _handle_press(self):
        """Handle key press based on mode."""
        if self.mode == "toggle":
            # In toggle mode, press toggles the state
            self._toggle_active = not self._toggle_active
            if self.on_toggle_callback:
                threading.Thread(
                    target=self.on_toggle_callback,
                    args=(self._toggle_active,),
                    daemon=True,
                ).start()
        else:
            # Push-to-talk: start on press
            if self.on_press_callback:
                threading.Thread(target=self.on_press_callback, daemon=True).start()

    def _handle_release(self):
        """Handle key release based on mode."""
        if self.mode == "toggle":
            pass  # Toggle mode ignores release
        else:
            # Push-to-talk: stop on release
            if self.on_release_callback:
                threading.Thread(target=self.on_release_callback, daemon=True).start()

    def _normalize_key(self, key):
        if hasattr(key, "name"):
            return key.name
        return str(key)

    def _check_combo(self):
        parts = self.hotkey_name.split("+")
        parts_lower = [p.strip().lower() for p in parts]
        for part in parts_lower:
            if part == "ctrl" and not any(k in self._combo_keys for k in ("ctrl", "ctrl_l", "ctrl_r")):
                return False
            elif part == "shift" and not any(k in self._combo_keys for k in ("shift", "shift_l", "shift_r")):
                return False
            elif part == "space" and "space" not in self._combo_keys:
                return False
            elif part == "alt" and not any(k in self._combo_keys for k in ("alt", "alt_l", "alt_r")):
                return False
        return True
