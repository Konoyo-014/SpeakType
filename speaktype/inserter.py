"""Insert text at the cursor position in any application using CGEvent."""

from dataclasses import dataclass
import logging
import threading
import time
import AppKit
import Quartz
from CoreFoundation import CFEqual, CFRangeMake, CFStringCreateWithSubstring, CFStringGetLength
from .applescript import run_osascript
from ApplicationServices import (
    AXUIElementCopyAttributeValue,
    AXUIElementCreateSystemWide,
    AXUIElementCreateApplication,
    AXUIElementSetAttributeValue,
    AXValueCreate,
    AXValueRef,
    AXValueGetType,
    AXValueGetValue,
    kAXValueCFRangeType,
    kAXFocusedUIElementAttribute,
    kAXRoleAttribute,
    kAXSelectedTextAttribute,
    kAXSelectedTextRangeAttribute,
)

logger = logging.getLogger("speaktype.inserter")

PASTEBOARD_SETTLE_DELAY = 0.005
PASTE_VERIFY_INTERVAL = 0.03
PASTE_VERIFY_ATTEMPTS = 7
AX_VERIFY_INTERVAL = 0.01
AX_VERIFY_ATTEMPTS = 2
CLIPBOARD_RESTORE_DELAY = 0.75
KEYCODE_V = 9
KEYCODE_COMMAND = 55
TARGET_ACTIVATION_TIMEOUT = 1.0
PASTE_FIRST_BUNDLE_MARKERS = (
    "com.openai.codex",
    "com.anthropic.claudefordesktop",
    "com.google.chrome",
    "com.microsoft.edgemac",
    "com.brave.browser",
    "company.thebrowser.browser",
    "com.openai.chat",
    "com.todesktop",
)
PASTE_FIRST_APP_MARKERS = (
    "codex",
    "claude",
    "chrome",
    "chatgpt",
    "gemini",
    "edge",
    "brave",
    "arc",
    "cursor",
)

_clipboard_restore_lock = threading.Lock()
_clipboard_restore_token = 0
_clipboard_restore_data = None
_clipboard_restore_text = None
_clipboard_restore_change_count = None
_last_insert_diagnostic = None
_manual_accessibility_enabled_pids = set()


@dataclass(frozen=True)
class InsertionDiagnostic:
    """Best-effort diagnostic for the most recent insertion attempt."""

    success: bool
    verified: bool
    method: str
    reason: str
    detail: str = ""


@dataclass(frozen=True)
class FocusedInputDiagnostic:
    """Read-only snapshot of the currently focused Accessibility element."""

    app_name: str = ""
    bundle_id: str = ""
    has_focused_element: bool = False
    role: str = ""
    has_value: bool = False
    selected_text_readable: bool = False
    post_event_allowed: bool = True
    likely_writable: bool = False
    reason: str = ""


@dataclass(frozen=True)
class FocusedTextSnapshot:
    """Read-only text snapshot for short post-insert observation."""

    has_focused_element: bool = False
    role: str = ""
    value: str | None = None
    selected_text: str | None = None


@dataclass(frozen=True)
class VerifiedInsertionSnapshot:
    element: object
    value: str
    selected_range: tuple[int, int]
    inserted_text: str


def _selected_utf16_range(element) -> tuple[int, int] | None:
    value = _copy_ax_attribute(element, kAXSelectedTextRangeAttribute)
    if not isinstance(value, AXValueRef) or AXValueGetType(value) != kAXValueCFRangeType:
        return None
    valid, selected_range = AXValueGetValue(value, kAXValueCFRangeType, None)
    if not valid:
        return None
    location, length = selected_range
    if location < 0 or length < 0:
        return None
    return int(location), int(length)


def _text_before_caret_matches(value: str, selected_range: tuple[int, int], text: str) -> bool:
    location, length = selected_range
    text_length = CFStringGetLength(text)
    if length != 0 or not text_length or location < text_length or location > CFStringGetLength(value):
        return False
    return CFStringCreateWithSubstring(None, value, CFRangeMake(location - text_length, text_length)) == text


def capture_verified_insertion(text: str) -> VerifiedInsertionSnapshot | None:
    diagnostic = get_last_insert_diagnostic()
    if not text or diagnostic is None or not diagnostic.success or not diagnostic.verified:
        return None
    element = _get_focused_element()
    if element is None:
        return None
    value = _copy_ax_attribute(element, "AXValue")
    selected_range = _selected_utf16_range(element)
    if not isinstance(value, str) or selected_range is None:
        return None
    if not _text_before_caret_matches(value, selected_range, text):
        return None
    return VerifiedInsertionSnapshot(element, value, selected_range, text)


def _snapshot_is_current(snapshot: VerifiedInsertionSnapshot, selected_range=None) -> bool:
    element = _get_focused_element()
    if element is None or not CFEqual(element, snapshot.element):
        return False
    return (
        _copy_ax_attribute(element, "AXValue") == snapshot.value
        and _selected_utf16_range(element) == (selected_range or snapshot.selected_range)
    )


def undo_verified_insertion(snapshot: VerifiedInsertionSnapshot | None) -> bool:
    if snapshot is None or not _snapshot_is_current(snapshot):
        return False
    if not _text_before_caret_matches(snapshot.value, snapshot.selected_range, snapshot.inserted_text):
        return False
    location = snapshot.selected_range[0]
    text_length = CFStringGetLength(snapshot.inserted_text)
    start = location - text_length
    deletion_range = (start, text_length)
    prefix = CFStringCreateWithSubstring(None, snapshot.value, CFRangeMake(0, start))
    suffix_length = CFStringGetLength(snapshot.value) - location
    suffix = CFStringCreateWithSubstring(None, snapshot.value, CFRangeMake(location, suffix_length))
    expected = prefix + suffix

    # 通过 AX 选中确切的听写范围，随后再次检查焦点、正文和选区。
    selected = AXValueCreate(kAXValueCFRangeType, CFRangeMake(*deletion_range))
    if _set_ax_attribute(snapshot.element, kAXSelectedTextRangeAttribute, selected) != 0:
        return False
    if not _snapshot_is_current(snapshot, deletion_range):
        return False
    if _set_ax_attribute(snapshot.element, kAXSelectedTextAttribute, "") != 0:
        return False
    for attempt in range(PASTE_VERIFY_ATTEMPTS):
        if _copy_ax_attribute(snapshot.element, "AXValue") == expected:
            return True
        if attempt < PASTE_VERIFY_ATTEMPTS - 1:
            time.sleep(PASTE_VERIFY_INTERVAL)
    return False


def reset_last_insert_diagnostic():
    global _last_insert_diagnostic
    _last_insert_diagnostic = None


def get_last_insert_diagnostic() -> InsertionDiagnostic | None:
    return _last_insert_diagnostic


def _set_insert_diagnostic(
    success: bool,
    verified: bool,
    method: str,
    reason: str,
    detail: str = "",
):
    global _last_insert_diagnostic
    _last_insert_diagnostic = InsertionDiagnostic(
        success=success,
        verified=verified,
        method=method,
        reason=reason,
        detail=str(detail or ""),
    )


def insert_text(text: str, method: str = "paste", app_name: str = "", bundle_id: str = "", target_pid: int | None = None) -> bool:
    """Insert text at the current cursor position."""
    reset_last_insert_diagnostic()
    if not text:
        _set_insert_diagnostic(True, True, method, "empty_text")
        return True
    target_pid = _prepare_target_app(bundle_id=bundle_id, app_name=app_name, method=method, target_pid=target_pid)
    if target_pid is None:
        return False
    logger.info(
        "Insert text via %s (%d chars) into %s [%s]",
        method,
        len(text),
        app_name or "Unknown",
        bundle_id or "",
    )
    if method == "paste":
        return _insert_via_paste(text, app_name=app_name, bundle_id=bundle_id, target_pid=target_pid)
    return _insert_via_keystroke(text, target_pid=target_pid)


def _insert_via_paste(text: str, app_name: str = "", bundle_id: str = "", target_pid: int = 0) -> bool:
    """Insert text by setting pasteboard and simulating Cmd+V via CGEvent."""
    if not _target_is_frontmost(target_pid, "paste"):
        return False
    if _should_try_accessibility_first(app_name=app_name, bundle_id=bundle_id) and _insert_via_accessibility(text):
        return True
    if not _can_post_synthetic_input():
        logger.error(
            "Cannot use paste/keystroke insertion because PostEvent access is not granted (app=%s)",
            app_name or "Unknown",
        )
        _set_insert_diagnostic(False, False, "paste", "post_event_denied")
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

        if PASTEBOARD_SETTLE_DELAY > 0:
            time.sleep(PASTEBOARD_SETTLE_DELAY)
        if not _target_is_frontmost(target_pid, "paste"):
            _restore_pasteboard(pb, _cancel_pending_pasteboard_restore(old_data))
            return False

        _press_cmd_v(app_name=app_name, target_pid=target_pid)
        verification = _verify_paste_result(element, value_before, text)
        if verification is True:
            _schedule_pasteboard_restore(
                old_data,
                temporary_text=text,
                expected_change_count=expected_change_count,
            )
            _set_insert_diagnostic(True, True, "paste", "verified_ax_value")
            logger.info("Clipboard paste path completed with verified text insertion (app=%s)", app_name or "Unknown")
            return True
        if verification is None:
            _schedule_pasteboard_restore(
                old_data,
                temporary_text=text,
                expected_change_count=expected_change_count,
            )
            _set_insert_diagnostic(True, False, "paste", "unverifiable_target")
            logger.info("Clipboard paste path completed without AX verification (app=%s)", app_name or "Unknown")
            return True

        logger.info(
            "Quartz paste did not change the focused text field (app=%s)",
            app_name or "Unknown",
        )
        if not _target_is_frontmost(target_pid, "paste"):
            _restore_pasteboard(pb, _cancel_pending_pasteboard_restore(old_data))
            return False
        if not target_pid and _press_cmd_v_with_osascript(app_name=app_name):
            verification = _verify_paste_result(element, value_before, text)
            if verification is True:
                _schedule_pasteboard_restore(
                    old_data,
                    temporary_text=text,
                    expected_change_count=expected_change_count,
                )
                _set_insert_diagnostic(True, True, "paste_system_events", "verified_ax_value")
                logger.info("Clipboard paste path completed via System Events with verified text insertion (app=%s)", app_name or "Unknown")
                return True
            if verification is None:
                _schedule_pasteboard_restore(
                    old_data,
                    temporary_text=text,
                    expected_change_count=expected_change_count,
                )
                _set_insert_diagnostic(True, False, "paste_system_events", "unverifiable_target")
                logger.info("Clipboard paste path completed via System Events without AX verification (app=%s)", app_name or "Unknown")
                return True

        if _insert_via_keystroke(text, target_pid=target_pid):
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
        if not _target_is_frontmost(target_pid, "paste"):
            return False
        _set_insert_diagnostic(False, False, "paste", "paste_verification_failed")
        logger.error("Clipboard paste failed verification (app=%s)", app_name or "Unknown")
        return False

    except Exception as e:
        logger.error(f"Paste insertion failed: {e}")
        if pb is not None:
            _restore_pasteboard(pb, _cancel_pending_pasteboard_restore(old_data))
        if not _target_is_frontmost(target_pid, "paste"):
            return False
        if _insert_via_keystroke(text, target_pid=target_pid):
            logger.info(
                "Clipboard paste failed; direct keystroke fallback succeeded (%d chars, app=%s)",
                len(text),
                app_name or "Unknown",
            )
            return True
        _set_insert_diagnostic(False, False, "paste", "paste_exception", str(e))
        return False


def _press_cmd_v(app_name: str = "", target_pid: int = 0):
    """Simulate Cmd+V keypress using Quartz CGEvent."""
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    tap = Quartz.kCGAnnotatedSessionEventTap
    _post_key_event(src, tap, KEYCODE_COMMAND, True, Quartz.kCGEventFlagMaskCommand, target_pid)
    _post_key_event(src, tap, KEYCODE_V, True, Quartz.kCGEventFlagMaskCommand, target_pid)
    _post_key_event(src, tap, KEYCODE_V, False, Quartz.kCGEventFlagMaskCommand, target_pid)
    _post_key_event(src, tap, KEYCODE_COMMAND, False, 0, target_pid)
    logger.info("Paste shortcut sent via Quartz CGEvent (app=%s)", app_name or "Unknown")


def _can_post_synthetic_input() -> bool:
    checker = getattr(Quartz, "CGPreflightPostEventAccess", None)
    if not callable(checker):
        return True
    try:
        return bool(checker())
    except Exception:
        return True


def _should_try_accessibility_first(app_name: str = "", bundle_id: str = "") -> bool:
    app_text = (app_name or "").lower()
    bundle_text = (bundle_id or "").lower()
    if any(marker in bundle_text for marker in PASTE_FIRST_BUNDLE_MARKERS):
        return False
    if any(marker in app_text for marker in PASTE_FIRST_APP_MARKERS):
        return False
    return True


def inspect_focused_input(app_name: str = "", bundle_id: str = "") -> FocusedInputDiagnostic:
    """Inspect whether the current focus looks usable for text insertion.

    This is intentionally read-only. It does not set AX attributes, mutate the
    pasteboard, or send keyboard events.
    """
    post_event_allowed = _can_post_synthetic_input()
    element = _get_focused_element()
    if element is None:
        return FocusedInputDiagnostic(
            app_name=app_name,
            bundle_id=bundle_id,
            has_focused_element=False,
            post_event_allowed=post_event_allowed,
            reason="no_focused_element",
        )

    role = _copy_ax_attribute(element, kAXRoleAttribute) or "Unknown"
    value = _copy_ax_attribute(element, "AXValue")
    selected_text = _copy_ax_attribute(element, kAXSelectedTextAttribute)
    has_value = isinstance(value, str)
    selected_text_readable = isinstance(selected_text, str)
    likely_writable = post_event_allowed and (has_value or selected_text_readable)
    reason = "ready" if likely_writable else "not_writable"
    if not post_event_allowed:
        reason = "post_event_denied"

    return FocusedInputDiagnostic(
        app_name=app_name,
        bundle_id=bundle_id,
        has_focused_element=True,
        role=str(role),
        has_value=has_value,
        selected_text_readable=selected_text_readable,
        post_event_allowed=post_event_allowed,
        likely_writable=likely_writable,
        reason=reason,
    )


def capture_focused_text_snapshot() -> FocusedTextSnapshot:
    """Return the current focused element text without mutating anything."""
    element = _get_focused_element()
    if element is None:
        return FocusedTextSnapshot(has_focused_element=False)
    role = _copy_ax_attribute(element, kAXRoleAttribute) or "Unknown"
    value = _copy_ax_attribute(element, "AXValue")
    selected_text = _copy_ax_attribute(element, kAXSelectedTextAttribute)
    return FocusedTextSnapshot(
        has_focused_element=True,
        role=str(role),
        value=value if isinstance(value, str) else None,
        selected_text=selected_text if isinstance(selected_text, str) else None,
    )


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
    for attempt in range(PASTE_VERIFY_ATTEMPTS):
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
        if attempt < PASTE_VERIFY_ATTEMPTS - 1:
            time.sleep(PASTE_VERIFY_INTERVAL)
    if not isinstance(value_after, str):
        return None
    logger.info(
        "Paste verification found unchanged AXValue (value_before=%r, value_after=%r)",
        value_before,
        value_after,
    )
    return False


def _post_event(event, tap, target_pid: int = 0):
    if target_pid:
        Quartz.CGEventPostToPid(target_pid, event)
    else:
        Quartz.CGEventPost(tap, event)


def _post_key_event(source, tap, keycode: int, is_down: bool, flags: int = 0, target_pid: int = 0):
    event = Quartz.CGEventCreateKeyboardEvent(source, keycode, is_down)
    if flags:
        Quartz.CGEventSetFlags(event, flags)
    _post_event(event, tap, target_pid)


def _prepare_target_app(bundle_id: str = "", app_name: str = "", method: str = "paste", target_pid: int | None = None) -> int | None:
    """Bring the target app back to front before synthetic input."""
    if not bundle_id and not app_name and target_pid is None:
        return 0
    try:
        if target_pid is not None:
            app = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(target_pid)
            if app is not None and (
                (bundle_id and app.bundleIdentifier() != bundle_id)
                or (not bundle_id and app_name and app.localizedName() != app_name)
            ):
                _set_insert_diagnostic(False, False, method, "target_process_changed", f"expected_pid={target_pid}, bundle_id={bundle_id}")
                return None
        else:
            app = _find_running_app(bundle_id=bundle_id, app_name=app_name)
        if app is None or app.isTerminated():
            _set_insert_diagnostic(False, False, method, "target_not_running", bundle_id or app_name)
            return None
        target_pid = int(app.processIdentifier())
        workspace = AppKit.NSWorkspace.sharedWorkspace()
        frontmost = workspace.frontmostApplication()
        if frontmost is None or frontmost.processIdentifier() != target_pid:
            if not app.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps):
                _set_insert_diagnostic(False, False, method, "target_activation_failed", bundle_id or app_name)
                return None
        deadline = time.monotonic() + TARGET_ACTIVATION_TIMEOUT
        while True:
            if app.isTerminated():
                _set_insert_diagnostic(False, False, method, "target_not_running", bundle_id or app_name)
                return None
            frontmost = workspace.frontmostApplication()
            if frontmost is not None and frontmost.processIdentifier() == target_pid:
                _enable_manual_accessibility_once(target_pid)
                return target_pid
            if time.monotonic() >= deadline:
                _set_insert_diagnostic(False, False, method, "target_not_frontmost", bundle_id or app_name)
                return None
            time.sleep(0.02)
    except Exception as e:
        logger.error("Failed to prepare target app %s: %s", bundle_id or app_name, e)
        _set_insert_diagnostic(False, False, method, "target_preparation_failed", str(e))
        return None


def _target_is_frontmost(target_pid: int, method: str) -> bool:
    if not target_pid:
        return True
    try:
        frontmost = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        if frontmost is not None and frontmost.processIdentifier() == target_pid:
            return True
        current_pid = frontmost.processIdentifier() if frontmost is not None else None
        _set_insert_diagnostic(False, False, method, "target_focus_changed", f"expected_pid={target_pid}, current_pid={current_pid}")
    except Exception as e:
        _set_insert_diagnostic(False, False, method, "target_focus_check_failed", str(e))
    return False


def _find_running_app(bundle_id: str = "", app_name: str = ""):
    if bundle_id:
        matches = AppKit.NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle_id)
        return next((app for app in matches if not app.isTerminated()), None)

    if app_name:
        for app in AppKit.NSWorkspace.sharedWorkspace().runningApplications():
            try:
                if app.localizedName() == app_name:
                    return app
            except Exception:
                pass

    return None


def _enable_manual_accessibility_once(pid: int):
    if pid in _manual_accessibility_enabled_pids:
        return
    _enable_manual_accessibility(pid)
    _manual_accessibility_enabled_pids.add(pid)


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
        _set_insert_diagnostic(False, False, "accessibility", "no_focused_element")
        return False

    role = _copy_ax_attribute(element, kAXRoleAttribute) or "Unknown"
    value_before = _copy_ax_attribute(element, "AXValue")
    selected_before = _copy_ax_attribute(element, kAXSelectedTextAttribute)
    err = _set_ax_attribute(element, kAXSelectedTextAttribute, text)
    if err == 0:
        value_after, selected_after = _wait_for_accessibility_insert_result(
            element,
            value_before,
            text,
        )
        if (
            isinstance(value_after, str)
            and value_after != value_before
            and text in value_after
        ):
            _set_insert_diagnostic(True, True, "accessibility", "verified_ax_value")
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
        _set_insert_diagnostic(False, False, "accessibility", "accessibility_false_success", f"role={role}")
        return False

    logger.info("Accessibility insertion unavailable (role=%s, error=%s); falling back to keystrokes", role, err)
    _set_insert_diagnostic(False, False, "accessibility", "accessibility_unavailable", f"role={role} error={err}")
    return False


def _wait_for_accessibility_insert_result(element, value_before, inserted_text: str):
    value_after = value_before
    selected_after = None
    for attempt in range(AX_VERIFY_ATTEMPTS):
        value_after = _copy_ax_attribute(element, "AXValue")
        selected_after = _copy_ax_attribute(element, kAXSelectedTextAttribute)
        if (
            isinstance(value_after, str)
            and value_after != value_before
            and inserted_text in value_after
        ):
            return value_after, selected_after
        if (
            isinstance(value_after, str)
            and value_after == value_before
            and isinstance(selected_after, str)
            and selected_after == inserted_text
        ):
            return value_after, selected_after
        if attempt < AX_VERIFY_ATTEMPTS - 1:
            time.sleep(AX_VERIFY_INTERVAL)
    return value_after, selected_after


def _get_focused_element():
    element = _copy_focused_element(AXUIElementCreateSystemWide())
    if element is not None:
        return element

    try:
        app = _frontmost_application()
        if app is None:
            return None
        return _copy_focused_element(AXUIElementCreateApplication(app.processIdentifier()))
    except Exception as e:
        logger.debug(f"Failed to access frontmost application focused element: {e}")
    return None


def _copy_focused_element(owner):
    try:
        err, element = AXUIElementCopyAttributeValue(owner, kAXFocusedUIElementAttribute, None)
        if err == 0:
            return element
    except Exception as e:
        logger.debug(f"Failed to access focused element: {e}")
    return None


def _frontmost_application():
    return AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()


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
    global _clipboard_restore_data, _clipboard_restore_token
    with _clipboard_restore_lock:
        if _clipboard_restore_data is not None:
            if _pasteboard_still_has_temporary_text(
                pb, _clipboard_restore_text, _clipboard_restore_change_count
            ):
                return dict(_clipboard_restore_data)
            _clipboard_restore_token += 1
            _clipboard_restore_data = None
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
    global _clipboard_restore_text, _clipboard_restore_change_count
    with _clipboard_restore_lock:
        _clipboard_restore_token += 1
        token = _clipboard_restore_token
        if _clipboard_restore_data is None:
            _clipboard_restore_data = old_data
        _clipboard_restore_text = temporary_text
        _clipboard_restore_change_count = expected_change_count
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


def _insert_via_keystroke(text: str, target_pid: int = 0):
    """Insert text character by character via CGEvent (slower fallback)."""
    if not _target_is_frontmost(target_pid, "keystroke"):
        return False
    if not _can_post_synthetic_input():
        _set_insert_diagnostic(False, False, "keystroke", "post_event_denied")
        logger.error("Cannot use keystroke insertion because PostEvent access is not granted")
        return False

    try:
        element = _get_focused_element()
        value_before = _copy_ax_attribute(element, "AXValue") if element is not None else None
        src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        for char in text:
            if not _target_is_frontmost(target_pid, "keystroke"):
                return False
            event = Quartz.CGEventCreateKeyboardEvent(src, 0, True)
            Quartz.CGEventKeyboardSetUnicodeString(event, CFStringGetLength(char), char)
            _post_event(event, Quartz.kCGAnnotatedSessionEventTap, target_pid)

            event_up = Quartz.CGEventCreateKeyboardEvent(src, 0, False)
            _post_event(event_up, Quartz.kCGAnnotatedSessionEventTap, target_pid)
            time.sleep(0.01)
        time.sleep(0.05)
        if element is not None and isinstance(value_before, str):
            value_after = _copy_ax_attribute(element, "AXValue")
            if isinstance(value_after, str) and value_after != value_before:
                _set_insert_diagnostic(True, True, "keystroke", "verified_ax_value")
                return True
            logger.info(
                "Keystroke fallback sent without AXValue change (value_before=%r, value_after=%r)",
                value_before,
                value_after,
            )
            _set_insert_diagnostic(False, False, "keystroke", "keystroke_no_ax_change")
            return False
        _set_insert_diagnostic(True, False, "keystroke", "unverifiable_target")
        return True
    except Exception as e:
        logger.error(f"Keystroke insertion failed: {e}")
        _set_insert_diagnostic(False, False, "keystroke", "keystroke_exception", str(e))
        return False
