"""Insert text at the cursor position in any application using CGEvent."""

import logging
import threading
import time
import AppKit
import Quartz
from .applescript import run_osascript
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
PASTE_VERIFY_INTERVAL = 0.05
PASTE_VERIFY_ATTEMPTS = 7
CLIPBOARD_RESTORE_DELAY = 0.75
KEYCODE_V = 9
KEYCODE_COMMAND = 55
TARGET_ACTIVATION_DELAY = 0.3

_clipboard_restore_lock = threading.Lock()
_clipboard_restore_token = 0
_clipboard_restore_data = None


def insert_text(text: str, method: str = "paste", app_name: str = "", bundle_id: str = "") -> bool:
    """Insert text at the current cursor position."""
    if not text:
        return True
    _prepare_target_app(bundle_id=bundle_id, app_name=app_name)
    logger.info(
        "Insert text via %s (%d chars) into %s [%s]",
        method,
        len(text),
        app_name or "Unknown",
        bundle_id or "",
    )
    if method == "paste":
        return _insert_via_paste(text, app_name=app_name)
    return _insert_via_keystroke(text)


def _insert_via_paste(text: str, app_name: str = "") -> bool:
    """Insert text by setting pasteboard and simulating Cmd+V via CGEvent."""
    if _insert_via_accessibility(text):
        return True
    if not _can_post_synthetic_input():
        logger.error(
            "Cannot use paste/keystroke insertion because PostEvent access is not granted (app=%s)",
            app_name or "Unknown",
        )
        return False

    pb = None
    old_data = {}
    try:
        element = _get_focused_element()
        value_before = _copy_ax_attribute(element, "AXValue") if element is not None else None
        pb = _get_pasteboard()
        old_data = _snapshot_restore_data(pb)

        # Set our text
        pb.clearContents()
        pb.setString_forType_(text, AppKit.NSPasteboardTypeString)
        expected_change_count = _get_pasteboard_change_count(pb)

        time.sleep(PASTEBOARD_SETTLE_DELAY)

        # Some desktop shells handle UI scripting paste more reliably than raw
        # CGEvents, especially when the editor is embedded inside Chromium.
        _press_cmd_v(app_name=app_name)
        verification = _verify_paste_result(element, value_before, text)
        if verification is True or verification is None:
            _schedule_pasteboard_restore(
                old_data,
                temporary_text=text,
                expected_change_count=expected_change_count,
            )
            logger.info("Clipboard paste path completed (app=%s)", app_name or "Unknown")
            return True

        logger.info(
            "Quartz paste did not change the focused text field; retrying via System Events (app=%s)",
            app_name or "Unknown",
        )
        if _press_cmd_v_with_osascript(app_name=app_name):
            verification = _verify_paste_result(element, value_before, text)
            if verification is True or verification is None:
                _schedule_pasteboard_restore(
                    old_data,
                    temporary_text=text,
                    expected_change_count=expected_change_count,
                )
                logger.info("Clipboard paste path completed via System Events (app=%s)", app_name or "Unknown")
                return True

        if _insert_via_keystroke(text):
            _schedule_pasteboard_restore(
                old_data,
                temporary_text=text,
                expected_change_count=expected_change_count,
            )
            logger.info(
                "Clipboard paste failed verification; direct keystroke fallback succeeded (%d chars, app=%s)",
                len(text),
                app_name or "Unknown",
            )
            return True

        _restore_pasteboard(pb, _cancel_pending_pasteboard_restore(old_data))
        logger.error("Clipboard paste failed verification (app=%s)", app_name or "Unknown")
        return False

    except Exception as e:
        logger.error(f"Paste insertion failed: {e}")
        if pb is not None:
            _restore_pasteboard(pb, _cancel_pending_pasteboard_restore(old_data))
        if _insert_via_keystroke(text):
            logger.info(
                "Clipboard paste failed; direct keystroke fallback succeeded (%d chars, app=%s)",
                len(text),
                app_name or "Unknown",
            )
            return True
        return False


def _press_cmd_v(app_name: str = ""):
    """Simulate Cmd+V keypress using Quartz CGEvent."""
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    tap = Quartz.kCGAnnotatedSessionEventTap
    _post_key_event(src, tap, KEYCODE_COMMAND, True, Quartz.kCGEventFlagMaskCommand)
    _post_key_event(src, tap, KEYCODE_V, True, Quartz.kCGEventFlagMaskCommand)
    _post_key_event(src, tap, KEYCODE_V, False, Quartz.kCGEventFlagMaskCommand)
    _post_key_event(src, tap, KEYCODE_COMMAND, False, 0)
    logger.info("Paste shortcut sent via Quartz CGEvent (app=%s)", app_name or "Unknown")


def _can_post_synthetic_input() -> bool:
    checker = getattr(Quartz, "CGPreflightPostEventAccess", None)
    if not callable(checker):
        return True
    try:
        return bool(checker())
    except Exception:
        return True


def _press_cmd_v_with_osascript(app_name: str = "") -> bool:
    """Retry paste through System Events for apps that ignore raw CGEvents."""
    script = 'tell application "System Events" to keystroke "v" using command down'
    try:
        result = run_osascript(script, timeout=2)
    except Exception as e:
        logger.info("System Events paste failed to run (app=%s): %s", app_name or "Unknown", e)
        return False
    if result.returncode == 0:
        logger.info("Paste shortcut sent via System Events (app=%s)", app_name or "Unknown")
        return True
    logger.info(
        "System Events paste returned %s (app=%s): %s",
        result.returncode,
        app_name or "Unknown",
        result.stderr.strip(),
    )
    return False


def _verify_paste_result(element, value_before, inserted_text: str):
    """Return True/False when AXValue can prove paste success/failure, else None."""
    if element is None or not isinstance(value_before, str):
        return None
    value_after = value_before
    for _ in range(PASTE_VERIFY_ATTEMPTS):
        time.sleep(PASTE_VERIFY_INTERVAL)
        value_after = _copy_ax_attribute(element, "AXValue")
        if not isinstance(value_after, str):
            return None
        if value_after != value_before:
            if inserted_text and inserted_text in value_after:
                return True
            logger.info(
                "Paste verification found AXValue changed without exact inserted text (value_before=%r, value_after=%r)",
                value_before,
                value_after,
            )
            return False
    if not isinstance(value_after, str):
        return None
    logger.info(
        "Paste verification found unchanged AXValue (value_before=%r, value_after=%r)",
        value_before,
        value_after,
    )
    return False


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
        if (
            isinstance(value_after, str)
            and value_after != value_before
            and text in value_after
        ):
            logger.info("Inserted text via Accessibility API (role=%s)", role)
            return True

        logger.info(
            "Accessibility API reported success without verified text insertion (role=%s, value_before=%r, value_after=%r, selected_before=%r, selected_after=%r)",
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


def _snapshot_restore_data(pb):
    with _clipboard_restore_lock:
        if _clipboard_restore_data is not None:
            return dict(_clipboard_restore_data)
    return _snapshot_pasteboard(pb)


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


def _get_pasteboard_change_count(pb):
    getter = getattr(pb, "changeCount", None)
    if callable(getter):
        try:
            return getter()
        except Exception:
            return None
    return None


def _pasteboard_still_has_temporary_text(pb, temporary_text: str, expected_change_count=None) -> bool:
    current_change_count = _get_pasteboard_change_count(pb)
    if expected_change_count is not None and current_change_count is not None:
        return current_change_count == expected_change_count

    getter = getattr(pb, "stringForType_", None)
    if callable(getter):
        try:
            return getter(AppKit.NSPasteboardTypeString) == temporary_text
        except Exception:
            return False
    return False


def _cancel_pending_pasteboard_restore(fallback_old_data):
    global _clipboard_restore_data, _clipboard_restore_token
    with _clipboard_restore_lock:
        _clipboard_restore_token += 1
        old_data = _clipboard_restore_data
        _clipboard_restore_data = None
    return old_data if old_data is not None else fallback_old_data


def _schedule_pasteboard_restore(old_data, temporary_text: str, expected_change_count=None, delay: float = CLIPBOARD_RESTORE_DELAY):
    global _clipboard_restore_data, _clipboard_restore_token
    with _clipboard_restore_lock:
        _clipboard_restore_token += 1
        token = _clipboard_restore_token
        if _clipboard_restore_data is None:
            _clipboard_restore_data = old_data
        restore_data = dict(_clipboard_restore_data)

    thread = threading.Thread(
        target=_restore_pasteboard_after_delay,
        args=(token, restore_data, temporary_text, expected_change_count, delay),
        daemon=True,
    )
    thread.start()


def _restore_pasteboard_after_delay(token: int, old_data, temporary_text: str, expected_change_count=None, delay: float = CLIPBOARD_RESTORE_DELAY):
    global _clipboard_restore_data
    time.sleep(delay)
    pb = _get_pasteboard()
    should_restore = _pasteboard_still_has_temporary_text(
        pb,
        temporary_text=temporary_text,
        expected_change_count=expected_change_count,
    )
    with _clipboard_restore_lock:
        if token != _clipboard_restore_token:
            return
        _clipboard_restore_data = None

    if should_restore:
        _restore_pasteboard(pb, old_data)
    else:
        logger.debug("Skipped clipboard restore because pasteboard changed after paste")


def replace_selection(text: str) -> bool:
    """Replace the currently selected text with new text."""
    pb = _get_pasteboard()
    old_data = _snapshot_restore_data(pb)
    try:
        pb.clearContents()
        pb.setString_forType_(text, AppKit.NSPasteboardTypeString)
        expected_change_count = _get_pasteboard_change_count(pb)
        time.sleep(PASTEBOARD_SETTLE_DELAY)
        _press_cmd_v()
        _schedule_pasteboard_restore(
            old_data,
            temporary_text=text,
            expected_change_count=expected_change_count,
        )
        return True
    except Exception:
        _restore_pasteboard(pb, _cancel_pending_pasteboard_restore(old_data))
        raise


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
