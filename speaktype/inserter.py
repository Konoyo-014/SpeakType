"""Insert text at the cursor position in any application using CGEvent."""

import time
import logging
import AppKit
import Quartz
from ApplicationServices import (
    AXUIElementCopyAttributeValue,
    AXUIElementCreateSystemWide,
    AXUIElementCreateApplication,
    AXUIElementSetAttributeValue,
    kAXFocusedUIElementAttribute,
    kAXRoleAttribute,
    kAXSelectedTextAttribute,
)

logger = logging.getLogger("speaktype.inserter")

PASTEBOARD_SETTLE_DELAY = 0.08
CLIPBOARD_RESTORE_DELAY = 0.75
KEYCODE_V = 9
KEYCODE_COMMAND = 55
TARGET_ACTIVATION_DELAY = 0.3


def insert_text(text: str, method: str = "paste", app_name: str = "", bundle_id: str = ""):
    """Insert text at the current cursor position."""
    if not text:
        return
    _prepare_target_app(bundle_id=bundle_id, app_name=app_name)
    logger.info(
        "Insert text via %s (%d chars) into %s [%s]",
        method,
        len(text),
        app_name or "Unknown",
        bundle_id or "",
    )
    if method == "paste":
        _insert_via_paste(text, app_name=app_name)
    else:
        _insert_via_keystroke(text)


def _insert_via_paste(text: str, app_name: str = ""):
    """Insert text by setting pasteboard and simulating Cmd+V via CGEvent."""
    if _insert_via_accessibility(text):
        return

    if _insert_via_keystroke(text):
        logger.info(
            "Accessibility insertion unavailable; direct keystroke fallback succeeded (%d chars, app=%s)",
            len(text),
            app_name or "Unknown",
        )
        return

    try:
        # Save current pasteboard
        pb = _get_pasteboard()
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
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    tap = Quartz.kCGAnnotatedSessionEventTap
    _post_key_event(src, tap, KEYCODE_COMMAND, True, Quartz.kCGEventFlagMaskCommand)
    _post_key_event(src, tap, KEYCODE_V, True, Quartz.kCGEventFlagMaskCommand)
    _post_key_event(src, tap, KEYCODE_V, False, Quartz.kCGEventFlagMaskCommand)
    _post_key_event(src, tap, KEYCODE_COMMAND, False, 0)
    logger.info("Paste shortcut sent via Quartz CGEvent (app=%s)", app_name or "Unknown")


def _post_key_event(source, tap, keycode: int, is_down: bool, flags: int = 0):
    event = Quartz.CGEventCreateKeyboardEvent(source, keycode, is_down)
    if flags:
        Quartz.CGEventSetFlags(event, flags)
    Quartz.CGEventPost(tap, event)


def _prepare_target_app(bundle_id: str = "", app_name: str = ""):
    """Bring the target app back to front before synthetic input."""
    app = _find_running_app(bundle_id=bundle_id, app_name=app_name)
    if app is None:
        return

    try:
        if not app.isActive():
            app.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
            time.sleep(TARGET_ACTIVATION_DELAY)
        _enable_manual_accessibility(app.processIdentifier())
    except Exception as e:
        logger.debug(f"Failed to prepare target app {bundle_id or app_name}: {e}")


def _find_running_app(bundle_id: str = "", app_name: str = ""):
    if bundle_id:
        matches = AppKit.NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle_id)
        if matches:
            return matches[0]

    if app_name:
        for app in AppKit.NSWorkspace.sharedWorkspace().runningApplications():
            try:
                if app.localizedName() == app_name:
                    return app
            except Exception:
                pass

    return None


def _enable_manual_accessibility(pid: int):
    try:
        ax_app = AXUIElementCreateApplication(pid)
        AXUIElementSetAttributeValue(ax_app, "AXManualAccessibility", True)
    except Exception as e:
        logger.debug(f"Failed to enable manual accessibility for pid {pid}: {e}")


def _insert_via_accessibility(text: str) -> bool:
    """Insert text into the focused accessibility element when supported."""
    element = _get_focused_element()
    if element is None:
        return False

    role = _copy_ax_attribute(element, kAXRoleAttribute) or "Unknown"
    value_before = _copy_ax_attribute(element, "AXValue")
    selected_before = _copy_ax_attribute(element, kAXSelectedTextAttribute)
    err = _set_ax_attribute(element, kAXSelectedTextAttribute, text)
    if err == 0:
        time.sleep(0.05)
        value_after = _copy_ax_attribute(element, "AXValue")
        selected_after = _copy_ax_attribute(element, kAXSelectedTextAttribute)
        if value_after != value_before or selected_after == text:
            logger.info("Inserted text via Accessibility API (role=%s)", role)
            return True

        logger.info(
            "Accessibility API reported success without text change (role=%s, value_before=%r, value_after=%r, selected_before=%r, selected_after=%r)",
            role,
            value_before,
            value_after,
            selected_before,
            selected_after,
        )
        return False

    logger.info("Accessibility insertion unavailable (role=%s, error=%s); falling back to keystrokes", role, err)
    return False


def _get_focused_element():
    try:
        system = AXUIElementCreateSystemWide()
        err, element = AXUIElementCopyAttributeValue(system, kAXFocusedUIElementAttribute, None)
        if err == 0:
            return element
    except Exception as e:
        logger.debug(f"Failed to access focused element: {e}")
    return None


def _copy_ax_attribute(element, attribute: str):
    try:
        err, value = AXUIElementCopyAttributeValue(element, attribute, None)
        if err == 0:
            return value
    except Exception as e:
        logger.debug(f"Failed to read AX attribute {attribute}: {e}")
    return None


def _set_ax_attribute(element, attribute: str, value) -> int:
    try:
        return AXUIElementSetAttributeValue(element, attribute, value)
    except Exception as e:
        logger.debug(f"Failed to set AX attribute {attribute}: {e}")
        return -1


def _get_pasteboard():
    return AppKit.NSPasteboard.generalPasteboard()


def _snapshot_pasteboard(pb):
    old_types = pb.types()
    old_data = {}
    if old_types:
        for t in old_types:
            try:
                d = pb.dataForType_(t)
            except Exception:
                d = None
            if d:
                old_data[t] = d
    return old_data


def _restore_pasteboard(pb, old_data):
    pb.clearContents()
    if old_data:
        for t, d in old_data.items():
            try:
                pb.setData_forType_(d, t)
            except Exception:
                pass


def replace_selection(text: str):
    """Replace the currently selected text with new text."""
    pb = _get_pasteboard()
    old_data = _snapshot_pasteboard(pb)
    try:
        pb.clearContents()
        pb.setString_forType_(text, AppKit.NSPasteboardTypeString)
        time.sleep(PASTEBOARD_SETTLE_DELAY)
        _press_cmd_v()
        time.sleep(CLIPBOARD_RESTORE_DELAY)
    finally:
        _restore_pasteboard(pb, old_data)


def delete_chars(count: int):
    """Send `count` backspace events to remove the previous `count` characters.

    Used by the "undo last dictation" voice command. Falls back silently
    if the CGEvent post fails.
    """
    if count <= 0:
        return
    try:
        src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        delete_keycode = 51  # macOS keycode for the Delete (backspace) key
        for _ in range(count):
            down = Quartz.CGEventCreateKeyboardEvent(src, delete_keycode, True)
            Quartz.CGEventPost(Quartz.kCGAnnotatedSessionEventTap, down)
            up = Quartz.CGEventCreateKeyboardEvent(src, delete_keycode, False)
            Quartz.CGEventPost(Quartz.kCGAnnotatedSessionEventTap, up)
            time.sleep(0.005)
    except Exception as e:
        logger.error(f"delete_chars failed: {e}")


def _insert_via_keystroke(text: str):
    """Insert text character by character via CGEvent (slower fallback)."""
    try:
        element = _get_focused_element()
        value_before = _copy_ax_attribute(element, "AXValue") if element is not None else None
        src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        for char in text:
            event = Quartz.CGEventCreateKeyboardEvent(src, 0, True)
            Quartz.CGEventKeyboardSetUnicodeString(event, len(char), char)
            Quartz.CGEventPost(Quartz.kCGAnnotatedSessionEventTap, event)

            event_up = Quartz.CGEventCreateKeyboardEvent(src, 0, False)
            Quartz.CGEventPost(Quartz.kCGAnnotatedSessionEventTap, event_up)
            time.sleep(0.01)
        time.sleep(0.05)
        if element is not None and isinstance(value_before, str):
            value_after = _copy_ax_attribute(element, "AXValue")
            if isinstance(value_after, str) and value_after != value_before:
                return True
            logger.info(
                "Keystroke fallback sent without AXValue change (value_before=%r, value_after=%r)",
                value_before,
                value_after,
            )
            return False
        return True
    except Exception as e:
        logger.error(f"Keystroke insertion failed: {e}")
        return False
