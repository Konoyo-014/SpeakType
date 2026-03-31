"""Global hotkey listener for push-to-talk."""

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
    "ctrl+shift+space": None,  # Combination handled separately
    "f5": keyboard.Key.f5,
    "f6": keyboard.Key.f6,
}


class HotkeyListener:
    def __init__(self, hotkey_name="right_cmd", on_press=None, on_release=None):
        self.hotkey_name = hotkey_name
        self.on_press_callback = on_press
        self.on_release_callback = on_release
        self._listener = None
        self._thread = None
        self._is_pressed = False
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
        logger.info(f"Hotkey listener started: {self.hotkey_name}")

    def stop(self):
        self._running = False
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _get_target_key(self):
        return KEY_MAP.get(self.hotkey_name)

    def _is_combo_hotkey(self):
        return "+" in self.hotkey_name

    def _on_press(self, key):
        if not self._running:
            return

        if self._is_combo_hotkey():
            self._combo_keys.add(self._normalize_key(key))
            if self._check_combo():
                if not self._is_pressed:
                    self._is_pressed = True
                    if self.on_press_callback:
                        threading.Thread(target=self.on_press_callback, daemon=True).start()
        else:
            target = self._get_target_key()
            if target and key == target:
                if not self._is_pressed:
                    self._is_pressed = True
                    if self.on_press_callback:
                        threading.Thread(target=self.on_press_callback, daemon=True).start()

    def _on_release(self, key):
        if not self._running:
            return

        if self._is_combo_hotkey():
            normalized = self._normalize_key(key)
            self._combo_keys.discard(normalized)
            if self._is_pressed and not self._check_combo():
                self._is_pressed = False
                if self.on_release_callback:
                    threading.Thread(target=self.on_release_callback, daemon=True).start()
        else:
            target = self._get_target_key()
            if target and key == target:
                if self._is_pressed:
                    self._is_pressed = False
                    if self.on_release_callback:
                        threading.Thread(target=self.on_release_callback, daemon=True).start()

    def _normalize_key(self, key):
        if hasattr(key, "name"):
            return key.name
        return str(key)

    def _check_combo(self):
        parts = self.hotkey_name.split("+")
        required = set()
        for p in parts:
            p = p.strip().lower()
            if p == "ctrl":
                required.add("ctrl_l")
                required.add("ctrl_r")
            elif p == "shift":
                required.add("shift")
                required.add("shift_l")
                required.add("shift_r")
            elif p == "space":
                required.add("space")
            elif p == "alt":
                required.add("alt_l")
                required.add("alt_r")
        # Check if at least one variant of each modifier is pressed
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
