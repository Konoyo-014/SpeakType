"""Insert text at the cursor position in any application using CGEvent."""

import time
import logging
import subprocess
import AppKit
import Quartz

logger = logging.getLogger("speaktype.inserter")

PASTEBOARD_SETTLE_DELAY = 0.08
CLIPBOARD_RESTORE_DELAY = 0.75
KEYCODE_V = 9
KEYCODE_COMMAND = 55


def insert_text(text: str, method: str = "paste", app_name: str = ""):
    """Insert text at the current cursor position."""
    if not text:
        return
    logger.info("Insert text via %s (%d chars) into %s", method, len(text), app_name or "Unknown")
    if method == "paste":
        _insert_via_paste(text, app_name=app_name)
    else:
        _insert_via_keystroke(text)


def _insert_via_paste(text: str, app_name: str = ""):
    """Insert text by setting pasteboard and simulating Cmd+V via CGEvent."""
    try:
        # Save current pasteboard
        pb = AppKit.NSPasteboard.generalPasteboard()
        old_types = pb.types()
        old_data = {}
        if old_types:
            for t in old_types:
                d = pb.dataForType_(t)
                if d:
                    old_data[t] = d

        # Set our text
        pb.clearContents()
        pb.setString_forType_(text, AppKit.NSPasteboardTypeString)

        time.sleep(PASTEBOARD_SETTLE_DELAY)

        # Some desktop shells handle UI scripting paste more reliably than raw
        # CGEvents, especially when the editor is embedded inside Chromium.
        _press_cmd_v(app_name=app_name)

        # Give the target app enough time to read the pasteboard before restoring
        # the user's clipboard. Electron-based apps often paste asynchronously.
        time.sleep(CLIPBOARD_RESTORE_DELAY)
        if old_data:
            pb.clearContents()
            for t, d in old_data.items():
                try:
                    pb.setData_forType_(d, t)
                except Exception:
                    pass
        else:
            pb.clearContents()

    except Exception as e:
        logger.error(f"Paste insertion failed: {e}")
        _insert_via_keystroke(text)


def _press_cmd_v(app_name: str = ""):
    """Simulate Cmd+V keypress using Quartz CGEvent."""
    if _press_cmd_v_via_osascript():
        logger.info("Paste shortcut sent via System Events")
        return

    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    _post_key_event(src, KEYCODE_COMMAND, True, Quartz.kCGEventFlagMaskCommand)
    _post_key_event(src, KEYCODE_V, True, Quartz.kCGEventFlagMaskCommand)
    _post_key_event(src, KEYCODE_V, False, Quartz.kCGEventFlagMaskCommand)
    _post_key_event(src, KEYCODE_COMMAND, False, 0)
    logger.info("Paste shortcut sent via Quartz CGEvent")


def _press_cmd_v_via_osascript() -> bool:
    script = 'tell application "System Events" to keystroke "v" using command down'
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception as e:
        logger.warning(f"System Events paste failed to launch: {e}")
        return False

    if result.returncode != 0:
        logger.warning(f"System Events paste failed: {result.stderr.strip()}")
        return False
    return True


def _post_key_event(source, keycode: int, is_down: bool, flags: int = 0):
    event = Quartz.CGEventCreateKeyboardEvent(source, keycode, is_down)
    if flags:
        Quartz.CGEventSetFlags(event, flags)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def replace_selection(text: str):
    """Replace the currently selected text with new text."""
    pb = AppKit.NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, AppKit.NSPasteboardTypeString)
    time.sleep(PASTEBOARD_SETTLE_DELAY)
    _press_cmd_v()


def _insert_via_keystroke(text: str):
    """Insert text character by character via CGEvent (slower fallback)."""
    try:
        src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        for char in text:
            event = Quartz.CGEventCreateKeyboardEvent(src, 0, True)
            Quartz.CGEventKeyboardSetUnicodeString(event, len(char), char)
            Quartz.CGEventPost(Quartz.kCGAnnotatedSessionEventTap, event)

            event_up = Quartz.CGEventCreateKeyboardEvent(src, 0, False)
            Quartz.CGEventPost(Quartz.kCGAnnotatedSessionEventTap, event_up)
            time.sleep(0.01)
    except Exception as e:
        logger.error(f"Keystroke insertion failed: {e}")
