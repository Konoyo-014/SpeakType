"""Insert text at the cursor position in any application using CGEvent."""

import time
import logging
import subprocess
import AppKit
import Quartz

logger = logging.getLogger("speaktype.inserter")


def insert_text(text: str, method: str = "paste"):
    """Insert text at the current cursor position."""
    if not text:
        return
    if method == "paste":
        _insert_via_paste(text)
    else:
        _insert_via_keystroke(text)


def _insert_via_paste(text: str):
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

        time.sleep(0.03)

        # Simulate Cmd+V via CGEvent (no osascript needed)
        _press_cmd_v()

        # Restore old clipboard after a delay
        time.sleep(0.2)
        if old_data:
            pb.clearContents()
            for t, d in old_data.items():
                try:
                    pb.setData_forType_(d, t)
                except Exception:
                    pass

    except Exception as e:
        logger.error(f"Paste insertion failed: {e}")
        _insert_via_keystroke(text)


def _press_cmd_v():
    """Simulate Cmd+V keypress using Quartz CGEvent."""
    # V key = keycode 9
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)

    # Cmd down + V down
    cmd_v_down = Quartz.CGEventCreateKeyboardEvent(src, 9, True)
    Quartz.CGEventSetFlags(cmd_v_down, Quartz.kCGEventFlagMaskCommand)
    Quartz.CGEventPost(Quartz.kCGAnnotatedSessionEventTap, cmd_v_down)

    # Cmd up + V up
    cmd_v_up = Quartz.CGEventCreateKeyboardEvent(src, 9, False)
    Quartz.CGEventSetFlags(cmd_v_up, Quartz.kCGEventFlagMaskCommand)
    Quartz.CGEventPost(Quartz.kCGAnnotatedSessionEventTap, cmd_v_up)


def replace_selection(text: str):
    """Replace the currently selected text with new text."""
    pb = AppKit.NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, AppKit.NSPasteboardTypeString)
    time.sleep(0.03)
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
