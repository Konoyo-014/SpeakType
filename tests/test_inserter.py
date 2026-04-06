"""Tests for text insertion fallbacks."""

from types import SimpleNamespace

from speaktype import inserter


def test_insert_via_accessibility_sets_selected_text(monkeypatch):
    element = object()
    calls = []
    values = {
        (element, inserter.kAXRoleAttribute): ["AXTextArea"],
        (element, "AXValue"): ["before", "after"],
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


def test_insert_via_accessibility_rejects_false_success(monkeypatch):
    element = object()
    calls = []
    values = {
        (element, inserter.kAXRoleAttribute): ["AXTextArea"],
        (element, "AXValue"): ["same", "same"],
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

    assert inserter._insert_via_accessibility("hello") is False
    assert calls == [(element, inserter.kAXSelectedTextAttribute, "hello")]


def test_insert_via_paste_skips_clipboard_when_accessibility_succeeds(monkeypatch):
    monkeypatch.setattr(inserter, "_insert_via_accessibility", lambda text: True)

    class _PasteboardAccessed(Exception):
        pass

    def fail_get_pasteboard():
        raise _PasteboardAccessed()

    monkeypatch.setattr(inserter, "_get_pasteboard", fail_get_pasteboard)

    inserter._insert_via_paste("hello")


def test_insert_via_paste_prefers_direct_keystrokes_before_clipboard(monkeypatch):
    monkeypatch.setattr(inserter, "_insert_via_accessibility", lambda text: False)
    calls = []

    monkeypatch.setattr(inserter, "_insert_via_keystroke", lambda text: calls.append(text) or True)
    monkeypatch.setattr(inserter, "_get_pasteboard", lambda: (_ for _ in ()).throw(AssertionError("clipboard should not be used")))

    inserter._insert_via_paste("hello", app_name="Codex")

    assert calls == ["hello"]


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
        lambda text, app_name="": inserted.append((text, app_name)),
    )

    inserter.insert_text("hello", method="paste", app_name="Codex", bundle_id="com.openai.codex")

    assert prepared == [("com.openai.codex", "Codex")]
    assert inserted == [("hello", "Codex")]


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
