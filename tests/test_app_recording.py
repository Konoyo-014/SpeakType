"""Tests for recording lifecycle regressions in SpeakTypeApp."""

import threading
import time
from types import SimpleNamespace

from speaktype import app as app_mod


def _make_app():
    app = object.__new__(app_mod.SpeakTypeApp)
    app.config = {
        "sound_feedback": False,
        "streaming_preview": False,
        "sample_rate": 16000,
        "language": "auto",
        "plugins_enabled": False,
        "max_recording_seconds": None,
        "insert_method": "paste",
    }
    app._recording_start_time = time.time()
    app._is_processing = False
    app._recording_stop_lock = threading.Lock()
    app._recording_stop_requested = False
    app._last_insertion_text = None
    app._last_insertion_app = None
    app._last_insertion_bundle_id = None
    app._level_timer = None
    app._streaming_transcriber = None
    app._processing_thread = None
    app.hotkey_listener = None
    app._plugin_manager = SimpleNamespace(run_hook=lambda *args, **kwargs: None)
    app._status_overlay = SimpleNamespace(
        show_recording=lambda: None,
        show_transcribing=lambda: None,
        hide=lambda delay=0.0: None,
        update_audio_level=lambda level: None,
        update_partial_text=lambda text: None,
    )
    app.asr = SimpleNamespace(_loaded=False)
    return app


def test_start_recording_does_not_show_overlay_when_recorder_fails(monkeypatch):
    app = _make_app()
    notifications = []
    shown = []

    app._status_overlay = SimpleNamespace(
        show_recording=lambda: shown.append(True),
        show_transcribing=lambda: None,
        hide=lambda delay=0.0: None,
        update_audio_level=lambda level: None,
        update_partial_text=lambda text: None,
    )
    app.recorder = SimpleNamespace(
        set_whisper_state_callback=lambda callback: None,
        set_stream_callback=lambda callback: None,
        start=lambda **kwargs: False,
        last_start_error=RuntimeError("mic unavailable"),
    )
    monkeypatch.setattr(app_mod.rumps, "notification", lambda title, subtitle, body: notifications.append((title, subtitle, body)))

    app_mod.SpeakTypeApp._start_recording(app)

    assert shown == []
    assert notifications == [("SpeakType", app_mod.t("notif_error"), "mic unavailable")]


def test_handle_undo_last_refuses_cross_app_delete(monkeypatch):
    app = _make_app()
    deleted = []
    app._last_insertion_text = "hello"
    app._last_insertion_app = "Mail"
    app._last_insertion_bundle_id = "com.apple.mail"

    monkeypatch.setattr(app_mod, "get_active_app", lambda: {"name": "Notes", "bundle_id": "com.apple.Notes"})
    monkeypatch.setattr(app_mod, "delete_chars", lambda count: deleted.append(count))

    assert app_mod.SpeakTypeApp._handle_undo_last(app) is False
    assert deleted == []
    assert app._last_insertion_text == "hello"


def test_handle_edit_command_remembers_inserted_text(monkeypatch):
    app = _make_app()
    replaced = []
    app.polish_engine = SimpleNamespace(edit_text=lambda command, selected, tone: "rewritten")

    monkeypatch.setattr(app_mod, "get_selected_text", lambda: "original")
    monkeypatch.setattr(app_mod, "replace_selection", lambda text: replaced.append(text))

    result = app_mod.SpeakTypeApp._handle_edit_command(
        app,
        "rewrite this",
        "neutral",
        {"name": "Code", "bundle_id": "com.microsoft.VSCode"},
    )

    assert result is True
    assert replaced == ["rewritten"]
    assert app._last_insertion_text == "rewritten"
    assert app._last_insertion_bundle_id == "com.microsoft.VSCode"


def test_on_max_duration_reached_dispatches_to_main_thread():
    app = _make_app()
    dispatched = []
    app._bridge = SimpleNamespace(
        performSelectorOnMainThread_withObject_waitUntilDone_=lambda selector, obj, wait: dispatched.append((selector, wait))
    )

    app_mod.SpeakTypeApp._on_max_duration_reached(app)

    assert dispatched == [(b"handleMaxDurationReached:", False)]


def test_start_level_monitor_dispatches_to_main_thread():
    app = _make_app()
    dispatched = []
    app._bridge = SimpleNamespace(
        performSelectorOnMainThread_withObject_waitUntilDone_=lambda selector, obj, wait: dispatched.append((selector, wait))
    )

    app_mod.SpeakTypeApp._start_level_monitor(app)

    assert dispatched == [(b"startLevelMonitor:", True)]


def test_stop_recording_is_idempotent():
    app = _make_app()
    stop_calls = []
    app.recorder = SimpleNamespace(
        is_recording=True,
        stop=lambda: stop_calls.append(True) or None,
        set_stream_callback=lambda callback: None,
    )

    app_mod.SpeakTypeApp._stop_recording(app)
    app_mod.SpeakTypeApp._stop_recording(app)

    assert stop_calls == [True]
