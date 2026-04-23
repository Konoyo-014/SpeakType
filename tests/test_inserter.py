"""Tests for text insertion fallbacks."""

from types import SimpleNamespace

import pytest

from speaktype import inserter


class _Pasteboard:
    def __init__(self, initial=None):
        self._store = dict(initial or {})
        self._change_count = 0

    def types(self):
        return list(self._store.keys())

    def dataForType_(self, paste_type):
        return self._store.get(paste_type)

    def stringForType_(self, paste_type):
        value = self._store.get(paste_type)
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return value

    def clearContents(self):
        self._store = {}
        self._change_count += 1

    def setString_forType_(self, text, paste_type):
        self._store[paste_type] = text.encode("utf-8")
        self._change_count += 1

    def setData_forType_(self, data, paste_type):
        self._store[paste_type] = data
        self._change_count += 1

    def changeCount(self):
        return self._change_count


@pytest.fixture(autouse=True)
def _reset_clipboard_restore_state(monkeypatch):
    inserter._clipboard_restore_token = 0
    inserter._clipboard_restore_data = None
    inserter._manual_accessibility_enabled_pids.clear()
    monkeypatch.setattr(inserter, "_can_post_synthetic_input", lambda: True)
    yield
    inserter._clipboard_restore_token = 0
    inserter._clipboard_restore_data = None
    inserter._manual_accessibility_enabled_pids.clear()


def test_insert_via_accessibility_sets_selected_text(monkeypatch):
    element = object()
    calls = []
    values = {
        (element, inserter.kAXRoleAttribute): ["AXTextArea"],
        (element, "AXValue"): ["before", "beforehello"],
        (element, inserter.kAXSelectedTextAttribute): ["", ""],
    }

    monkeypatch.setattr(inserter, "_get_focused_element", lambda: element)
    monkeypatch.setattr(
        inserter,
        "_copy_ax_attribute",
        lambda elem, attr: values[(elem, attr)].pop(0),
    )
    monkeypatch.setattr(inserter.time, "sleep", lambda seconds: None)

    def fake_set(elem, attr, value):
        calls.append((elem, attr, value))
        return 0

    monkeypatch.setattr(inserter, "_set_ax_attribute", fake_set)

    assert inserter._insert_via_accessibility("hello") is True
    assert calls == [(element, inserter.kAXSelectedTextAttribute, "hello")]
    diagnostic = inserter.get_last_insert_diagnostic()
    assert diagnostic.success is True
    assert diagnostic.verified is True
    assert diagnostic.method == "accessibility"


def test_insert_via_accessibility_rejects_false_success(monkeypatch):
    element = object()
    calls = []
    values = {
        (element, inserter.kAXRoleAttribute): ["AXTextArea"],
        (element, "AXValue"): ["same", "same", "same", "same", "same"],
        (element, inserter.kAXSelectedTextAttribute): ["", "", "", "", ""],
    }

    monkeypatch.setattr(inserter, "_get_focused_element", lambda: element)
    monkeypatch.setattr(
        inserter,
        "_copy_ax_attribute",
        lambda elem, attr: values[(elem, attr)].pop(0),
    )
    monkeypatch.setattr(inserter.time, "sleep", lambda seconds: None)

    def fake_set(elem, attr, value):
        calls.append((elem, attr, value))
        return 0

    monkeypatch.setattr(inserter, "_set_ax_attribute", fake_set)

    assert inserter._insert_via_accessibility("hello") is False
    assert calls == [(element, inserter.kAXSelectedTextAttribute, "hello")]
    diagnostic = inserter.get_last_insert_diagnostic()
    assert diagnostic.success is False
    assert diagnostic.reason == "accessibility_false_success"


def test_insert_via_accessibility_rejects_selection_echo(monkeypatch):
    element = object()
    values = {
        (element, inserter.kAXRoleAttribute): ["AXTextArea"],
        (element, "AXValue"): ["same", "same"],
        (element, inserter.kAXSelectedTextAttribute): ["", "hello"],
    }

    monkeypatch.setattr(inserter, "_get_focused_element", lambda: element)
    monkeypatch.setattr(
        inserter,
        "_copy_ax_attribute",
        lambda elem, attr: values[(elem, attr)].pop(0),
    )
    monkeypatch.setattr(inserter.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(inserter, "_set_ax_attribute", lambda elem, attr, value: 0)

    assert inserter._insert_via_accessibility("hello") is False


def test_insert_via_paste_skips_clipboard_when_accessibility_succeeds(monkeypatch):
    monkeypatch.setattr(inserter, "_insert_via_accessibility", lambda text: True)

    class _PasteboardAccessed(Exception):
        pass

    def fail_get_pasteboard():
        raise _PasteboardAccessed()

    monkeypatch.setattr(inserter, "_get_pasteboard", fail_get_pasteboard)

    assert inserter._insert_via_paste("hello") is True


def test_insert_via_paste_fails_fast_without_post_event_permission(monkeypatch):
    monkeypatch.setattr(inserter, "_insert_via_accessibility", lambda text: False)
    monkeypatch.setattr(inserter, "_can_post_synthetic_input", lambda: False)
    monkeypatch.setattr(
        inserter,
        "_get_pasteboard",
        lambda: (_ for _ in ()).throw(AssertionError("pasteboard should not be touched")),
    )

    assert inserter._insert_via_paste("hello", app_name="Codex") is False
    diagnostic = inserter.get_last_insert_diagnostic()
    assert diagnostic.success is False
    assert diagnostic.reason == "post_event_denied"


def test_insert_via_paste_prefers_clipboard_before_direct_keystrokes(monkeypatch):
    monkeypatch.setattr(inserter, "_insert_via_accessibility", lambda text: False)
    monkeypatch.setattr(inserter, "_get_focused_element", lambda: None)
    pb = _Pasteboard({"public.utf8-plain-text": b"before"})
    presses = []

    monkeypatch.setattr(inserter, "_insert_via_keystroke", lambda text: (_ for _ in ()).throw(AssertionError("keystroke should not be used")))
    monkeypatch.setattr(inserter, "_get_pasteboard", lambda: pb)
    monkeypatch.setattr(inserter.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(inserter, "_press_cmd_v", lambda app_name="": presses.append(app_name))
    monkeypatch.setattr(inserter, "_schedule_pasteboard_restore", lambda *args, **kwargs: None)

    assert inserter._insert_via_paste("hello", app_name="Codex") is True

    assert presses == ["Codex"]
    assert pb.stringForType_(inserter.AppKit.NSPasteboardTypeString) == "hello"
    diagnostic = inserter.get_last_insert_diagnostic()
    assert diagnostic.success is True
    assert diagnostic.verified is False
    assert diagnostic.reason == "unverifiable_target"


def test_insert_via_paste_skips_accessibility_for_paste_first_apps(monkeypatch):
    monkeypatch.setattr(
        inserter,
        "_insert_via_accessibility",
        lambda text: (_ for _ in ()).throw(AssertionError("accessibility should be skipped")),
    )
    monkeypatch.setattr(inserter, "_get_focused_element", lambda: None)
    pb = _Pasteboard({"public.utf8-plain-text": b"before"})
    presses = []

    monkeypatch.setattr(inserter, "_insert_via_keystroke", lambda text: False)
    monkeypatch.setattr(inserter, "_get_pasteboard", lambda: pb)
    monkeypatch.setattr(inserter.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(inserter, "_press_cmd_v", lambda app_name="": presses.append(app_name))
    monkeypatch.setattr(inserter, "_schedule_pasteboard_restore", lambda *args, **kwargs: None)

    assert inserter._insert_via_paste(
        "hello",
        app_name="Codex",
        bundle_id="com.openai.codex",
    ) is True

    assert presses == ["Codex"]


def test_insert_via_paste_retries_system_events_when_observable_paste_does_not_change_target(monkeypatch):
    monkeypatch.setattr(inserter, "_insert_via_accessibility", lambda text: False)
    element = object()
    pb = _Pasteboard({"public.utf8-plain-text": b"before"})
    quartz_presses = []
    osascript_presses = []
    scheduled = []
    verifications = [False, True]

    monkeypatch.setattr(inserter, "_get_focused_element", lambda: element)
    monkeypatch.setattr(inserter, "_copy_ax_attribute", lambda elem, attr: "before")
    monkeypatch.setattr(inserter, "_insert_via_keystroke", lambda text: False)
    monkeypatch.setattr(inserter, "_get_pasteboard", lambda: pb)
    monkeypatch.setattr(inserter.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(inserter, "_press_cmd_v", lambda app_name="": quartz_presses.append(app_name))
    monkeypatch.setattr(inserter, "_press_cmd_v_with_osascript", lambda app_name="": osascript_presses.append(app_name) or True)
    monkeypatch.setattr(inserter, "_verify_paste_result", lambda element, value_before, text: verifications.pop(0))
    monkeypatch.setattr(
        inserter,
        "_schedule_pasteboard_restore",
        lambda old_data, temporary_text, expected_change_count=None, delay=inserter.CLIPBOARD_RESTORE_DELAY: scheduled.append(
            (old_data, temporary_text, expected_change_count, delay)
        ),
    )

    assert inserter._insert_via_paste("hello", app_name="Codex") is True

    assert quartz_presses == ["Codex"]
    assert osascript_presses == ["Codex"]
    diagnostic = inserter.get_last_insert_diagnostic()
    assert diagnostic.success is True
    assert diagnostic.verified is True
    assert diagnostic.method == "paste_system_events"
    assert scheduled == [
        (
            {"public.utf8-plain-text": b"before"},
            "hello",
            pb.changeCount(),
            inserter.CLIPBOARD_RESTORE_DELAY,
        )
    ]


def test_insert_via_paste_returns_false_when_observable_paste_and_fallbacks_fail(monkeypatch):
    monkeypatch.setattr(inserter, "_insert_via_accessibility", lambda text: False)
    element = object()
    pb = _Pasteboard({"public.utf8-plain-text": b"before"})
    restored = []

    monkeypatch.setattr(inserter, "_get_focused_element", lambda: element)
    monkeypatch.setattr(inserter, "_copy_ax_attribute", lambda elem, attr: "before")
    monkeypatch.setattr(inserter, "_insert_via_keystroke", lambda text: False)
    monkeypatch.setattr(inserter, "_get_pasteboard", lambda: pb)
    monkeypatch.setattr(inserter.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(inserter, "_press_cmd_v", lambda app_name="": None)
    monkeypatch.setattr(inserter, "_press_cmd_v_with_osascript", lambda app_name="": False)
    monkeypatch.setattr(inserter, "_verify_paste_result", lambda element, value_before, text: False)
    monkeypatch.setattr(inserter, "_restore_pasteboard", lambda pasteboard, old_data: restored.append(old_data))

    assert inserter._insert_via_paste("hello", app_name="Codex") is False

    assert restored == [{"public.utf8-plain-text": b"before"}]


def test_verify_paste_result_detects_unchanged_ax_value(monkeypatch):
    element = object()

    monkeypatch.setattr(inserter.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(inserter, "_copy_ax_attribute", lambda elem, attr: "before")

    assert inserter._verify_paste_result(element, "before", "hello") is False


def test_verify_paste_result_detects_changed_ax_value(monkeypatch):
    element = object()

    monkeypatch.setattr(inserter.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(inserter, "_copy_ax_attribute", lambda elem, attr: "beforehello")

    assert inserter._verify_paste_result(element, "before", "hello") is True


def test_verify_paste_result_checks_before_sleep(monkeypatch):
    element = object()
    sleeps = []

    monkeypatch.setattr(inserter.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(inserter, "_copy_ax_attribute", lambda elem, attr: "beforehello")

    assert inserter._verify_paste_result(element, "before", "hello") is True
    assert sleeps == []


def test_verify_paste_result_rejects_unrelated_ax_change(monkeypatch):
    element = object()

    monkeypatch.setattr(inserter.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(inserter, "_copy_ax_attribute", lambda elem, attr: "different")

    assert inserter._verify_paste_result(element, "before", "hello") is False


def test_verify_paste_result_is_inconclusive_without_ax_value():
    assert inserter._verify_paste_result(None, None, "hello") is None


def test_wait_for_accessibility_insert_result_checks_before_sleep(monkeypatch):
    element = object()
    sleeps = []
    values = {
        (element, "AXValue"): ["beforehello"],
        (element, inserter.kAXSelectedTextAttribute): [""],
    }

    monkeypatch.setattr(inserter.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(
        inserter,
        "_copy_ax_attribute",
        lambda elem, attr: values[(elem, attr)].pop(0),
    )

    value_after, selected_after = inserter._wait_for_accessibility_insert_result(
        element,
        "before",
        "hello",
    )

    assert value_after == "beforehello"
    assert selected_after == ""
    assert sleeps == []


def test_inspect_focused_input_reports_ready_text_field(monkeypatch):
    element = object()
    values = {
        (element, inserter.kAXRoleAttribute): "AXTextArea",
        (element, "AXValue"): "hello",
        (element, inserter.kAXSelectedTextAttribute): "",
    }

    monkeypatch.setattr(inserter, "_can_post_synthetic_input", lambda: True)
    monkeypatch.setattr(inserter, "_get_focused_element", lambda: element)
    monkeypatch.setattr(inserter, "_copy_ax_attribute", lambda elem, attr: values[(elem, attr)])

    diagnostic = inserter.inspect_focused_input(app_name="Codex", bundle_id="com.openai.codex")

    assert diagnostic.has_focused_element is True
    assert diagnostic.post_event_allowed is True
    assert diagnostic.likely_writable is True
    assert diagnostic.reason == "ready"


def test_inspect_focused_input_reports_post_event_denied(monkeypatch):
    element = object()
    values = {
        (element, inserter.kAXRoleAttribute): "AXTextArea",
        (element, "AXValue"): "hello",
        (element, inserter.kAXSelectedTextAttribute): "",
    }

    monkeypatch.setattr(inserter, "_can_post_synthetic_input", lambda: False)
    monkeypatch.setattr(inserter, "_get_focused_element", lambda: element)
    monkeypatch.setattr(inserter, "_copy_ax_attribute", lambda elem, attr: values[(elem, attr)])

    diagnostic = inserter.inspect_focused_input(app_name="Codex")

    assert diagnostic.has_focused_element is True
    assert diagnostic.post_event_allowed is False
    assert diagnostic.likely_writable is False
    assert diagnostic.reason == "post_event_denied"


def test_press_cmd_v_posts_annotated_session_events(monkeypatch):
    posted = []

    monkeypatch.setattr(inserter.Quartz, "CGEventSourceCreate", lambda state: object())
    monkeypatch.setattr(
        inserter,
        "_post_key_event",
        lambda source, tap, keycode, is_down, flags=0: posted.append((tap, keycode, is_down, flags)),
    )

    inserter._press_cmd_v("Codex")

    assert posted == [
        (inserter.Quartz.kCGAnnotatedSessionEventTap, inserter.KEYCODE_COMMAND, True, inserter.Quartz.kCGEventFlagMaskCommand),
        (inserter.Quartz.kCGAnnotatedSessionEventTap, inserter.KEYCODE_V, True, inserter.Quartz.kCGEventFlagMaskCommand),
        (inserter.Quartz.kCGAnnotatedSessionEventTap, inserter.KEYCODE_V, False, inserter.Quartz.kCGEventFlagMaskCommand),
        (inserter.Quartz.kCGAnnotatedSessionEventTap, inserter.KEYCODE_COMMAND, False, 0),
    ]


def test_prepare_target_app_activates_and_enables_accessibility(monkeypatch):
    app = SimpleNamespace()
    activations = []
    enabled = []

    app.isActive = lambda: False
    app.activateWithOptions_ = lambda options: activations.append(options)
    app.processIdentifier = lambda: 4242

    monkeypatch.setattr(inserter, "_find_running_app", lambda bundle_id="", app_name="": app)
    monkeypatch.setattr(inserter, "_enable_manual_accessibility", lambda pid: enabled.append(pid))
    monkeypatch.setattr(inserter.time, "sleep", lambda seconds: None)

    inserter._prepare_target_app(bundle_id="com.openai.codex", app_name="Codex")

    assert activations == [inserter.AppKit.NSApplicationActivateIgnoringOtherApps]
    assert enabled == [4242]


def test_prepare_target_app_enables_manual_accessibility_once_per_pid(monkeypatch):
    app = SimpleNamespace()
    enabled = []

    app.isActive = lambda: True
    app.processIdentifier = lambda: 4242

    monkeypatch.setattr(inserter, "_find_running_app", lambda bundle_id="", app_name="": app)
    monkeypatch.setattr(inserter, "_enable_manual_accessibility", lambda pid: enabled.append(pid))

    inserter._prepare_target_app(bundle_id="com.openai.codex", app_name="Codex")
    inserter._prepare_target_app(bundle_id="com.openai.codex", app_name="Codex")

    assert enabled == [4242]


def test_insert_text_prepares_target_app(monkeypatch):
    prepared = []
    inserted = []

    monkeypatch.setattr(
        inserter,
        "_prepare_target_app",
        lambda bundle_id="", app_name="": prepared.append((bundle_id, app_name)),
    )
    monkeypatch.setattr(
        inserter,
        "_insert_via_paste",
        lambda text, app_name="", bundle_id="": inserted.append((text, app_name, bundle_id)) or True,
    )

    assert inserter.insert_text("hello", method="paste", app_name="Codex", bundle_id="com.openai.codex") is True

    assert prepared == [("com.openai.codex", "Codex")]
    assert inserted == [("hello", "Codex", "com.openai.codex")]


def test_insert_text_returns_false_when_fallbacks_fail(monkeypatch):
    monkeypatch.setattr(inserter, "_prepare_target_app", lambda bundle_id="", app_name="": None)
    monkeypatch.setattr(inserter, "_insert_via_paste", lambda text, app_name="", bundle_id="": False)

    assert inserter.insert_text("hello", method="paste", app_name="Codex") is False


def test_insert_via_keystroke_rejects_unchanged_ax_value(monkeypatch):
    element = object()
    values = {
        (element, "AXValue"): ["same", "same"],
    }
    posted = []

    monkeypatch.setattr(inserter, "_get_focused_element", lambda: element)
    monkeypatch.setattr(
        inserter,
        "_copy_ax_attribute",
        lambda elem, attr: values[(elem, attr)].pop(0),
    )
    monkeypatch.setattr(inserter.Quartz, "CGEventSourceCreate", lambda state: object())
    monkeypatch.setattr(inserter.Quartz, "CGEventCreateKeyboardEvent", lambda source, keycode, is_down: object())
    monkeypatch.setattr(inserter.Quartz, "CGEventKeyboardSetUnicodeString", lambda event, length, char: None)
    monkeypatch.setattr(inserter.Quartz, "CGEventPost", lambda tap, event: posted.append((tap, event)))
    monkeypatch.setattr(inserter.time, "sleep", lambda seconds: None)

    assert inserter._insert_via_keystroke("hi") is False
    assert len(posted) == 4


def test_replace_selection_restores_clipboard_on_failure(monkeypatch):
    pb = _Pasteboard({"public.utf8-plain-text": b"before"})
    monkeypatch.setattr(inserter, "_get_pasteboard", lambda: pb)
    monkeypatch.setattr(inserter.time, "sleep", lambda seconds: None)

    def fail_paste(app_name=""):
        raise RuntimeError("paste failed")

    monkeypatch.setattr(inserter, "_press_cmd_v", fail_paste)

    with pytest.raises(RuntimeError):
        inserter.replace_selection("after")

    assert pb.dataForType_("public.utf8-plain-text") == b"before"


def test_insert_via_paste_schedules_clipboard_restore_without_blocking(monkeypatch):
    pb = _Pasteboard({"public.utf8-plain-text": b"before"})
    sleeps = []
    scheduled = []
    presses = []

    monkeypatch.setattr(inserter, "_insert_via_accessibility", lambda text: False)
    monkeypatch.setattr(inserter, "_get_focused_element", lambda: None)
    monkeypatch.setattr(inserter, "_insert_via_keystroke", lambda text: False)
    monkeypatch.setattr(inserter, "_get_pasteboard", lambda: pb)
    monkeypatch.setattr(inserter.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(inserter, "_press_cmd_v", lambda app_name="": presses.append(app_name))
    monkeypatch.setattr(
        inserter,
        "_schedule_pasteboard_restore",
        lambda old_data, temporary_text, expected_change_count=None, delay=inserter.CLIPBOARD_RESTORE_DELAY: scheduled.append(
            (old_data, temporary_text, expected_change_count, delay)
        ),
    )

    assert inserter._insert_via_paste("hello", app_name="Codex") is True

    assert sleeps == [inserter.PASTEBOARD_SETTLE_DELAY]
    assert presses == ["Codex"]
    assert pb.stringForType_(inserter.AppKit.NSPasteboardTypeString) == "hello"
    assert scheduled == [
        (
            {"public.utf8-plain-text": b"before"},
            "hello",
            pb.changeCount(),
            inserter.CLIPBOARD_RESTORE_DELAY,
        )
    ]


def test_replace_selection_schedules_clipboard_restore_without_blocking(monkeypatch):
    pb = _Pasteboard({"public.utf8-plain-text": b"before"})
    sleeps = []
    scheduled = []

    monkeypatch.setattr(inserter, "_get_pasteboard", lambda: pb)
    monkeypatch.setattr(inserter.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(inserter, "_press_cmd_v", lambda app_name="": None)
    monkeypatch.setattr(
        inserter,
        "_schedule_pasteboard_restore",
        lambda old_data, temporary_text, expected_change_count=None, delay=inserter.CLIPBOARD_RESTORE_DELAY: scheduled.append(
            (old_data, temporary_text, expected_change_count, delay)
        ),
    )

    assert inserter.replace_selection("after") is True

    assert sleeps == [inserter.PASTEBOARD_SETTLE_DELAY]
    assert pb.stringForType_(inserter.AppKit.NSPasteboardTypeString) == "after"
    assert scheduled == [
        (
            {"public.utf8-plain-text": b"before"},
            "after",
            pb.changeCount(),
            inserter.CLIPBOARD_RESTORE_DELAY,
        )
    ]


def test_snapshot_restore_data_reuses_original_clipboard_during_overlapping_pastes(monkeypatch):
    pb = _Pasteboard({"public.utf8-plain-text": b"before"})
    scheduled_threads = []

    class _Thread:
        def __init__(self, target, args, daemon):
            scheduled_threads.append((target, args, daemon))

        def start(self):
            return None

    monkeypatch.setattr(inserter.threading, "Thread", _Thread)

    first_old_data = inserter._snapshot_restore_data(pb)
    pb.clearContents()
    pb.setString_forType_("first", inserter.AppKit.NSPasteboardTypeString)
    inserter._schedule_pasteboard_restore(
        first_old_data,
        temporary_text="first",
        expected_change_count=pb.changeCount(),
    )

    second_old_data = inserter._snapshot_restore_data(pb)

    assert second_old_data == {"public.utf8-plain-text": b"before"}
    assert len(scheduled_threads) == 1


def test_restore_after_delay_skips_when_user_changed_clipboard(monkeypatch):
    pb = _Pasteboard({"public.utf8-plain-text": b"user-new"})
    old_data = {"public.utf8-plain-text": b"before"}

    inserter._clipboard_restore_token = 3
    inserter._clipboard_restore_data = dict(old_data)

    monkeypatch.setattr(inserter, "_get_pasteboard", lambda: pb)
    monkeypatch.setattr(inserter.time, "sleep", lambda seconds: None)

    inserter._restore_pasteboard_after_delay(
        3,
        old_data,
        temporary_text="hello",
        expected_change_count=1,
        delay=0,
    )

    assert pb.dataForType_("public.utf8-plain-text") == b"user-new"
    assert inserter._clipboard_restore_data is None
