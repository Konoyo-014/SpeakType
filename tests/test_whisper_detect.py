"""Tests for the adaptive whisper detector."""

import pytest

from speaktype.whisper_detect import (
    NOISE_FLOOR,
    STATE_NORMAL,
    STATE_WHISPER,
    WHISPER_ENTER_FRAMES,
    WHISPER_EXIT_FRAMES,
    WHISPER_GAIN,
    WhisperDetector,
)


class TestInitialState:
    def test_starts_normal(self):
        d = WhisperDetector()
        assert d.state == STATE_NORMAL
        assert d.is_whisper is False
        assert d.was_active is False

    def test_default_gain_in_normal_state(self):
        d = WhisperDetector()
        assert d.gain_factor() == 1.0


class TestEnterWhisper:
    def test_enters_whisper_after_sustained_quiet(self):
        d = WhisperDetector()
        states = [d.feed_chunk(0.01) for _ in range(WHISPER_ENTER_FRAMES)]
        assert states[-1] == STATE_WHISPER
        assert d.is_whisper
        assert d.was_active

    def test_does_not_enter_below_noise_floor(self):
        d = WhisperDetector()
        # Pure silence — should never trip the detector.
        for _ in range(WHISPER_ENTER_FRAMES * 3):
            assert d.feed_chunk(0.0001) == STATE_NORMAL
        assert not d.is_whisper

    def test_does_not_enter_with_loud_audio(self):
        d = WhisperDetector()
        for _ in range(WHISPER_ENTER_FRAMES * 3):
            assert d.feed_chunk(0.2) == STATE_NORMAL

    def test_one_loud_frame_resets_quiet_counter(self):
        d = WhisperDetector()
        # Almost trip the detector...
        for _ in range(WHISPER_ENTER_FRAMES - 1):
            d.feed_chunk(0.015)
        assert d.state == STATE_NORMAL
        # ...one loud frame should reset the run.
        d.feed_chunk(0.2)
        assert d.state == STATE_NORMAL
        # Need a fresh full run to enter whisper now.
        for _ in range(WHISPER_ENTER_FRAMES - 1):
            d.feed_chunk(0.015)
        assert d.state == STATE_NORMAL


class TestExitWhisper:
    def test_exits_whisper_after_sustained_loud(self):
        d = WhisperDetector()
        for _ in range(WHISPER_ENTER_FRAMES):
            d.feed_chunk(0.01)
        assert d.is_whisper

        for _ in range(WHISPER_EXIT_FRAMES):
            d.feed_chunk(0.2)
        assert d.state == STATE_NORMAL

    def test_does_not_exit_on_borderline_audio(self):
        d = WhisperDetector()
        for _ in range(WHISPER_ENTER_FRAMES):
            d.feed_chunk(0.01)
        assert d.is_whisper
        # Slightly above the enter threshold but below the exit threshold —
        # detector should stay in whisper mode.
        for _ in range(WHISPER_EXIT_FRAMES * 4):
            d.feed_chunk(0.04)
        assert d.is_whisper

    def test_one_quiet_frame_resets_loud_counter(self):
        d = WhisperDetector()
        for _ in range(WHISPER_ENTER_FRAMES):
            d.feed_chunk(0.01)
        assert d.is_whisper
        for _ in range(WHISPER_EXIT_FRAMES - 1):
            d.feed_chunk(0.2)
        d.feed_chunk(0.01)
        assert d.is_whisper


class TestGainFactor:
    def test_gain_during_whisper(self):
        d = WhisperDetector()
        for _ in range(WHISPER_ENTER_FRAMES):
            d.feed_chunk(0.01)
        assert d.gain_factor() == WHISPER_GAIN

    def test_gain_returns_to_one_after_exit(self):
        d = WhisperDetector()
        for _ in range(WHISPER_ENTER_FRAMES):
            d.feed_chunk(0.01)
        for _ in range(WHISPER_EXIT_FRAMES):
            d.feed_chunk(0.2)
        assert d.gain_factor() == 1.0


class TestStateCallback:
    def test_callback_fires_on_enter(self):
        events = []
        d = WhisperDetector(on_state_change=events.append)
        for _ in range(WHISPER_ENTER_FRAMES):
            d.feed_chunk(0.01)
        assert events == [STATE_WHISPER]

    def test_callback_fires_on_exit(self):
        events = []
        d = WhisperDetector(on_state_change=events.append)
        for _ in range(WHISPER_ENTER_FRAMES):
            d.feed_chunk(0.01)
        for _ in range(WHISPER_EXIT_FRAMES):
            d.feed_chunk(0.2)
        assert events == [STATE_WHISPER, STATE_NORMAL]

    def test_callback_errors_do_not_break_state_machine(self):
        def boom(_state):
            raise RuntimeError("nope")

        d = WhisperDetector(on_state_change=boom)
        for _ in range(WHISPER_ENTER_FRAMES):
            d.feed_chunk(0.01)
        assert d.is_whisper

    def test_set_state_callback_replaces(self):
        events1 = []
        events2 = []
        d = WhisperDetector(on_state_change=events1.append)
        d.set_state_callback(events2.append)
        for _ in range(WHISPER_ENTER_FRAMES):
            d.feed_chunk(0.01)
        assert events1 == []
        assert events2 == [STATE_WHISPER]


class TestReset:
    def test_reset_clears_state_and_was_active(self):
        d = WhisperDetector()
        for _ in range(WHISPER_ENTER_FRAMES):
            d.feed_chunk(0.01)
        assert d.was_active
        d.reset()
        assert d.state == STATE_NORMAL
        assert d.was_active is False
        assert d.gain_factor() == 1.0

    def test_reset_clears_internal_counters(self):
        d = WhisperDetector()
        for _ in range(WHISPER_ENTER_FRAMES - 1):
            d.feed_chunk(0.01)
        d.reset()
        # Counter should be back at zero — one more quiet frame should NOT trip.
        d.feed_chunk(0.01)
        assert d.state == STATE_NORMAL


class TestNoiseFloor:
    def test_silence_resets_quiet_counter(self):
        d = WhisperDetector()
        for _ in range(WHISPER_ENTER_FRAMES - 1):
            d.feed_chunk(0.01)
        for _ in range(20):
            d.feed_chunk(0.0001)
        assert d.state == STATE_NORMAL
        d.feed_chunk(0.01)
        assert d.state == STATE_NORMAL


class TestCustomThresholds:
    def test_custom_thresholds_allow_quicker_entry(self):
        d = WhisperDetector(enter_frames=2)
        d.feed_chunk(0.01)
        assert d.state == STATE_NORMAL
        d.feed_chunk(0.01)
        assert d.state == STATE_WHISPER

    def test_custom_gain_value(self):
        d = WhisperDetector(gain=10.0, enter_frames=1)
        d.feed_chunk(0.01)
        assert d.gain_factor() == 10.0
