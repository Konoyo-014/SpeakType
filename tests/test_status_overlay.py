"""Tests for the unified StatusOverlay state machine.

These tests do NOT touch the real AppKit window machinery. They patch the
main-thread dispatch and the setup helper so the StatusOverlay can run
its state-machine logic in isolation.
"""

import time

import pytest

from speaktype import status_overlay
from speaktype.status_overlay import StatusOverlay, _format_duration, _sanitize_display_text


@pytest.fixture
def overlay(monkeypatch):
    """Create a StatusOverlay with all main-thread side effects stubbed out."""
    inst = StatusOverlay()

    dispatched = []

    def fake_dispatch(self, selector):
        dispatched.append(selector)
        # For every selector, also run the corresponding main-thread method
        # synchronously so we can assert on the resulting state.
        mapping = {
            b"showMain:": self._show_main,
            b"hideMain:": self._hide_main,
            b"refreshMain:": lambda: self._refresh_main(),
            b"updateLevelMain:": self._update_level_main,
            b"resetAfterHide:": self._reset_after_hide_main,
        }
        fn = mapping.get(selector)
        if fn is not None:
            try:
                fn()
            except Exception:
                # Swallow AppKit-related errors so the state-machine logic
                # can still be inspected.
                pass

    # Replace the dispatcher
    monkeypatch.setattr(StatusOverlay, "_dispatch_main", fake_dispatch)

    # Block real window creation — pretend setup succeeded
    def fake_setup_main(self):
        self._setup_done = True

    monkeypatch.setattr(StatusOverlay, "_setup_main", fake_setup_main)

    # Stub out every main-thread helper to avoid touching NSWindow / NSTimer.
    monkeypatch.setattr(StatusOverlay, "_show_main", lambda self: None)
    monkeypatch.setattr(
        StatusOverlay,
        "_hide_main",
        lambda self: setattr(self, "_state", "idle"),
    )
    monkeypatch.setattr(
        StatusOverlay, "_refresh_main", lambda self, animate_resize=True: None
    )
    monkeypatch.setattr(StatusOverlay, "_update_level_main", lambda self: None)
    monkeypatch.setattr(
        StatusOverlay, "_reset_after_hide_main", lambda self: None
    )

    inst._dispatched = dispatched
    return inst


class TestStateTransitions:
    def test_initial_state_is_idle(self, overlay):
        assert overlay.state == "idle"
        assert overlay._text == ""
        assert overlay._level == 0.0

    def test_show_recording_sets_state_and_resets_text(self, overlay):
        overlay._text = "stale"
        overlay.show_recording()
        assert overlay.state == "recording"
        assert overlay._text == ""
        assert overlay._level == 0.0
        assert overlay._start_time > 0

    def test_show_transcribing_keeps_existing_text(self, overlay):
        overlay.show_recording()
        overlay.update_partial_text("hello world")
        overlay.show_transcribing()
        assert overlay.state == "transcribing"
        assert overlay._text == "hello world"

    def test_show_polishing_overrides_text(self, overlay):
        overlay.show_recording()
        overlay.show_polishing("polished candidate")
        assert overlay.state == "polishing"
        assert overlay._text == "polished candidate"

    def test_show_polishing_without_text_keeps_previous(self, overlay):
        overlay.show_recording()
        overlay.update_partial_text("partial")
        overlay.show_polishing()
        assert overlay.state == "polishing"
        assert overlay._text == "partial"

    def test_show_done_sets_text(self, overlay):
        overlay.show_recording()
        overlay.show_done("final text", auto_hide_after=0)
        assert overlay.state == "done"
        assert overlay._text == "final text"

    def test_show_error_sets_text(self, overlay):
        overlay.show_recording()
        overlay.show_error("insert failed", auto_hide_after=0)
        assert overlay.state == "error"
        assert overlay._text == "insert failed"

    def test_full_pipeline_state_sequence(self, overlay):
        overlay.show_recording()
        assert overlay.state == "recording"
        overlay.update_partial_text("partial 1")
        overlay.update_partial_text("partial 1 and 2")
        overlay.show_transcribing()
        assert overlay.state == "transcribing"
        overlay.show_polishing("polished")
        assert overlay.state == "polishing"
        overlay.show_done("polished final", auto_hide_after=0)
        assert overlay.state == "done"


class TestPartialTextUpdates:
    def test_update_partial_text_replaces(self, overlay):
        overlay.update_partial_text("first")
        overlay.update_partial_text("second")
        assert overlay._text == "second"

    def test_update_partial_text_ignores_none(self, overlay):
        overlay.update_partial_text("real")
        overlay.update_partial_text(None)
        assert overlay._text == "real"

    def test_update_partial_text_accepts_empty_string(self, overlay):
        overlay.update_partial_text("real")
        overlay.update_partial_text("")
        assert overlay._text == ""

    def test_update_partial_text_sanitizes_display_only_artifacts(self, overlay):
        overlay.update_partial_text("hello<|zh|>\x00世\u754c\r\nnext\tline")
        assert overlay._text == "hello世界\nnext line"


class TestDisplaySanitization:
    def test_sanitize_display_text_removes_special_tokens_and_controls(self):
        assert _sanitize_display_text("<|startoftranscript|>hi\x00\r\nthere") == "hi\nthere"


class TestAudioLevel:
    def test_update_audio_level_clamps_high(self, overlay):
        overlay.update_audio_level(2.5)
        assert overlay._level == 1.0

    def test_update_audio_level_clamps_low(self, overlay):
        overlay.update_audio_level(-0.4)
        assert overlay._level == 0.0

    def test_update_audio_level_passthrough(self, overlay):
        overlay.update_audio_level(0.42)
        assert overlay._level == pytest.approx(0.42)


class TestAutoHide:
    def test_hide_immediate_dispatches_hide(self, overlay):
        overlay.show_recording()
        overlay.hide()
        # After running the dispatched hide, state should reset to idle.
        assert overlay.state == "idle"

    def test_hide_with_delay_schedules_timer(self, overlay):
        overlay.show_recording()
        overlay.hide(delay=0.05)
        assert overlay._auto_hide_timer is not None
        # Wait for the timer to fire
        time.sleep(0.15)
        assert overlay.state == "idle"

    def test_show_recording_cancels_pending_auto_hide(self, overlay):
        overlay.show_recording()
        overlay.hide(delay=5.0)  # would fire much later
        assert overlay._auto_hide_timer is not None
        overlay.show_recording()
        assert overlay._auto_hide_timer is None
        assert overlay.state == "recording"


def test_reset_after_hide_is_ignored_for_visible_overlay():
    overlay = StatusOverlay()
    overlay._state = "recording"
    overlay._is_visible = True
    overlay._text = "keep me"

    overlay._reset_after_hide_main()

    assert overlay._text == "keep me"


class TestFormatDuration:
    @pytest.mark.parametrize(
        "seconds,expected",
        [
            (0, "0:00"),
            (5, "0:05"),
            (59, "0:59"),
            (60, "1:00"),
            (61, "1:01"),
            (125, "2:05"),
            (3599, "59:59"),
            (3600, "60:00"),
            (-3, "0:00"),
        ],
    )
    def test_format(self, seconds, expected):
        assert _format_duration(seconds) == expected
