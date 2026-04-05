"""Global hotkey listener for push-to-talk and toggle-to-talk modes."""

import logging
import os
import sys
import threading

try:
    import AppKit
except Exception:  # pragma: no cover - AppKit is only available on macOS
    AppKit = None

from pynput import keyboard

logger = logging.getLogger("speaktype.hotkey")

HOTKEY_NAME_MAP = {
    "right_cmd": "cmd_r",
    "left_cmd": "cmd_l",
    "right_alt": "alt_r",
    "right_ctrl": "ctrl_r",
    "fn": "fn",
    "ctrl+shift+space": None,  # Combination handled separately
    "f5": "f5",
    "f6": "f6",
}

MODIFIER_GROUPS = {
    "ctrl": {"ctrl", "ctrl_l", "ctrl_r"},
    "shift": {"shift", "shift_l", "shift_r"},
    "alt": {"alt", "alt_l", "alt_r"},
    "cmd": {"cmd", "cmd_l", "cmd_r"},
}

NATIVE_KEYCODE_MAP = {
    49: "space",
    96: "f5",
    97: "f6",
}

if AppKit is not None:
    NATIVE_MODIFIER_MAP = {
        54: ("cmd_r", AppKit.NSEventModifierFlagCommand),
        55: ("cmd_l", AppKit.NSEventModifierFlagCommand),
        58: ("alt_l", AppKit.NSEventModifierFlagOption),
        59: ("ctrl_l", AppKit.NSEventModifierFlagControl),
        60: ("shift_r", AppKit.NSEventModifierFlagShift),
        61: ("alt_r", AppKit.NSEventModifierFlagOption),
        62: ("ctrl_r", AppKit.NSEventModifierFlagControl),
        63: ("fn", AppKit.NSEventModifierFlagFunction),
        56: ("shift_l", AppKit.NSEventModifierFlagShift),
    }
else:  # pragma: no cover - kept for import-time safety outside macOS
    NATIVE_MODIFIER_MAP = {}


class _NativeMacOSHotkeyBackend:
    """Use AppKit NSEvent monitors so the app bundle stays on the NSApplication runloop."""

    name = "nsevent"

    def __init__(self, dispatch_event):
        self._dispatch_event = dispatch_event
        self._global_monitor = None
        self._local_monitor = None

    @property
    def is_running(self) -> bool:
        return self._global_monitor is not None or self._local_monitor is not None

    def start(self):
        if AppKit is None:
            raise RuntimeError("AppKit is unavailable")

        mask = (
            AppKit.NSEventMaskKeyDown
            | AppKit.NSEventMaskKeyUp
            | AppKit.NSEventMaskFlagsChanged
        )
        self._global_monitor = AppKit.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            mask, self._handle_global_event
        )
        self._local_monitor = AppKit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            mask, self._handle_local_event
        )
        if not self.is_running:
            raise RuntimeError("AppKit monitor registration returned no monitor handles")

    def stop(self):
        if self._global_monitor is not None:
            AppKit.NSEvent.removeMonitor_(self._global_monitor)
            self._global_monitor = None
        if self._local_monitor is not None:
            AppKit.NSEvent.removeMonitor_(self._local_monitor)
            self._local_monitor = None

    def _handle_global_event(self, event):
        normalized = self._normalize_event(event)
        if normalized is not None:
            self._dispatch_event(*normalized)

    def _handle_local_event(self, event):
        self._handle_global_event(event)
        return event

    def _normalize_event(self, event):
        event_type = event.type()
        if event_type == AppKit.NSEventTypeFlagsChanged:
            return self._normalize_flags_changed(event)

        key_name = self._normalize_key_code(event.keyCode(), event.charactersIgnoringModifiers())
        if key_name is None:
            return None

        if event_type == AppKit.NSEventTypeKeyDown:
            return "down", key_name
        if event_type == AppKit.NSEventTypeKeyUp:
            return "up", key_name
        return None

    def _normalize_flags_changed(self, event):
        entry = NATIVE_MODIFIER_MAP.get(event.keyCode())
        if entry is None:
            return None
        key_name, modifier_flag = entry
        is_pressed = bool(event.modifierFlags() & modifier_flag)
        return ("down" if is_pressed else "up"), key_name

    @staticmethod
    def _normalize_key_code(key_code, chars):
        key_name = NATIVE_KEYCODE_MAP.get(key_code)
        if key_name is not None:
            return key_name
        if chars == " ":
            return "space"
        if chars:
            return chars.lower()
        return None


class _PynputHotkeyBackend:
    """Fallback backend for environments where AppKit monitors are unavailable."""

    name = "pynput"

    def __init__(self, dispatch_event):
        self._dispatch_event = dispatch_event
        self._listener = None

    @property
    def is_running(self) -> bool:
        return bool(self._listener and self._listener.running)

    def start(self):
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _on_press(self, key):
        key_name = self._normalize_key(key)
        if key_name is not None:
            self._dispatch_event("down", key_name)

    def _on_release(self, key):
        key_name = self._normalize_key(key)
        if key_name is not None:
            self._dispatch_event("up", key_name)

    @staticmethod
    def _normalize_key(key):
        name = getattr(key, "name", None)
        if name is not None:
            return name
        char = getattr(key, "char", None)
        if char == " ":
            return "space"
        if char:
            return char.lower()
        return str(key)


class HotkeyListener:
    def __init__(
        self,
        hotkey_name="right_cmd",
        on_press=None,
        on_release=None,
        mode="push_to_talk",
        on_toggle=None,
        backend_factory=None,
    ):
        """
        Args:
            hotkey_name: Key identifier from HOTKEY_NAME_MAP or a combo like "ctrl+shift+space"
            on_press: Callback when key is pressed (push_to_talk mode)
            on_release: Callback when key is released (push_to_talk mode)
            mode: "push_to_talk" or "toggle"
            on_toggle: Callback for toggle mode, called with is_active: bool
            backend_factory: Test hook for injecting a fake backend
        """
        self.hotkey_name = hotkey_name
        self.on_press_callback = on_press
        self.on_release_callback = on_release
        self.on_toggle_callback = on_toggle
        self.mode = mode
        self._backend_factory = backend_factory
        self._backend = None
        self._is_pressed = False
        self._toggle_active = False
        self._running = False
        self._combo_keys = set()

    def start(self):
        if self._running:
            return

        self._backend = self._start_backend()
        self._running = True
        logger.info(
            "Hotkey listener started: %s (mode=%s, backend=%s)",
            self.hotkey_name,
            self.mode,
            self.backend_name,
        )

    def stop(self):
        self._running = False
        self._is_pressed = False
        self._toggle_active = False
        self._combo_keys.clear()
        if self._backend:
            self._backend.stop()
            self._backend = None

    @property
    def backend_name(self) -> str:
        return getattr(self._backend, "name", "stopped")

    @property
    def is_running(self) -> bool:
        return bool(self._running and self._backend and self._backend.is_running)

    @property
    def is_active(self) -> bool:
        """Whether recording is active (works for both modes)."""
        if self.mode == "toggle":
            return self._toggle_active
        return self._is_pressed

    def _start_backend(self):
        if self._backend_factory is not None:
            backend = self._backend_factory(self._handle_backend_event)
            backend.start()
            return backend

        requested = os.environ.get("SPEAKTYPE_HOTKEY_BACKEND", "auto").strip().lower()
        backends = []

        if requested == "auto":
            if sys.platform == "darwin" and AppKit is not None:
                backends.append(_NativeMacOSHotkeyBackend)
            backends.append(_PynputHotkeyBackend)
        elif requested == "nsevent":
            backends.append(_NativeMacOSHotkeyBackend)
        elif requested == "pynput":
            backends.append(_PynputHotkeyBackend)
        else:
            logger.warning("Unknown SPEAKTYPE_HOTKEY_BACKEND=%s, falling back to auto", requested)
            if sys.platform == "darwin" and AppKit is not None:
                backends.append(_NativeMacOSHotkeyBackend)
            backends.append(_PynputHotkeyBackend)

        errors = []
        for backend_cls in backends:
            backend = backend_cls(self._handle_backend_event)
            try:
                backend.start()
                return backend
            except Exception as exc:  # pragma: no cover - fallback path depends on host environment
                errors.append(f"{backend_cls.name}: {exc}")
                logger.warning("Hotkey backend %s failed to start: %s", backend_cls.name, exc)

        raise RuntimeError("Unable to start any hotkey backend: " + "; ".join(errors))

    def _handle_backend_event(self, event_type, key_name):
        if not self._running or not key_name:
            return

        if self._is_combo_hotkey():
            if event_type == "down":
                self._combo_keys.add(key_name)
                if self._check_combo() and not self._is_pressed:
                    self._is_pressed = True
                    self._handle_press()
            elif event_type == "up":
                self._combo_keys.discard(key_name)
                if self._is_pressed and not self._check_combo():
                    self._is_pressed = False
                    self._handle_release()
            return

        target = self._get_target_key_name()
        if target is None or key_name != target:
            return

        if event_type == "down" and not self._is_pressed:
            self._is_pressed = True
            self._handle_press()
        elif event_type == "up" and self._is_pressed:
            self._is_pressed = False
            self._handle_release()

    def _get_target_key_name(self):
        return HOTKEY_NAME_MAP.get(self.hotkey_name)

    def _is_combo_hotkey(self):
        return "+" in self.hotkey_name

    def _handle_press(self):
        """Handle key press based on mode."""
        if self.mode == "toggle":
            self._toggle_active = not self._toggle_active
            self._dispatch_callback(self.on_toggle_callback, self._toggle_active)
        else:
            self._dispatch_callback(self.on_press_callback)

    def _handle_release(self):
        """Handle key release based on mode."""
        if self.mode != "toggle":
            self._dispatch_callback(self.on_release_callback)

    @staticmethod
    def _dispatch_callback(callback, *args):
        if callback:
            threading.Thread(target=callback, args=args, daemon=True).start()

    def _check_combo(self):
        parts = self.hotkey_name.split("+")
        for part in (p.strip().lower() for p in parts):
            if part == "space":
                if "space" not in self._combo_keys:
                    return False
                continue

            aliases = MODIFIER_GROUPS.get(part, {part})
            if not any(alias in self._combo_keys for alias in aliases):
                return False
        return True
