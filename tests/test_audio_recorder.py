"""Tests for AudioRecorder's whisper integration and watchdog wiring.

These tests bypass PortAudio entirely — they only exercise the pure-Python
parts of the recorder by feeding numpy chunks straight into ``_callback``.
"""

import time

import numpy as np
import pytest

from speaktype import audio as audio_mod
from speaktype.audio import AudioRecorder
from speaktype.whisper_detect import (
    WHISPER_ENTER_FRAMES,
    WHISPER_GAIN,
)


@pytest.fixture
def recorder():
    rec = AudioRecorder(sample_rate=16000)
    rec.is_recording = True
    rec._frames = []
    yield rec
    rec.is_recording = False


def _quiet_chunk(samples=1600, level=0.01):
    return (np.ones(samples, dtype=np.float32) * level).reshape(-1, 1)


def _loud_chunk(samples=1600, level=0.2):
    return (np.ones(samples, dtype=np.float32) * level).reshape(-1, 1)


class TestWhisperIntegration:
    def test_whisper_state_starts_normal(self, recorder):
        assert recorder.whisper_state == "normal"
        assert recorder.whisper_active is False
        assert recorder.whisper_was_active is False

    def test_quiet_chunks_trigger_whisper_state(self, recorder):
        for _ in range(WHISPER_ENTER_FRAMES + 1):
            recorder._callback(_quiet_chunk(), 1600, None, None)
        assert recorder.whisper_active
        assert recorder.whisper_was_active

    def test_quiet_chunks_get_gain_boost(self, recorder):
        for _ in range(WHISPER_ENTER_FRAMES + 1):
            recorder._callback(_quiet_chunk(), 1600, None, None)
        # Latest stored frame should have been multiplied by the gain.
        last = recorder._frames[-1]
        # Original level was 0.01; expected ~0.05 after 5x gain.
        assert float(np.max(last)) >= 0.04
        assert float(np.max(last)) <= 1.0

    def test_loud_chunks_are_not_boosted(self, recorder):
        recorder._callback(_loud_chunk(), 1600, None, None)
        # 0.2 * 1.0 = 0.2 — unchanged
        last = recorder._frames[-1]
        assert float(np.max(last)) == pytest.approx(0.2, abs=1e-6)

    def test_whisper_state_callback_fires(self, recorder):
        events = []
        recorder.set_whisper_state_callback(events.append)
        for _ in range(WHISPER_ENTER_FRAMES + 1):
            recorder._callback(_quiet_chunk(), 1600, None, None)
        assert "whisper" in events

    def test_disabled_whisper_mode_skips_boost(self):
        rec = AudioRecorder(sample_rate=16000, whisper_mode_enabled=False)
        rec.is_recording = True
        rec._frames = []
        for _ in range(WHISPER_ENTER_FRAMES + 1):
            rec._callback(_quiet_chunk(), 1600, None, None)
        # No state change, no boost — last frame still at 0.01.
        last = rec._frames[-1]
        assert float(np.max(last)) == pytest.approx(0.01, abs=1e-6)


class TestStreamCallback:
    def test_stream_callback_receives_chunks(self, recorder):
        received = []
        recorder.set_stream_callback(received.append)
        recorder._callback(_loud_chunk(), 1600, None, None)
        recorder._callback(_loud_chunk(), 1600, None, None)
        assert len(received) == 2

    def test_stream_callback_errors_are_swallowed(self, recorder):
        def boom(_chunk):
            raise RuntimeError("oops")

        recorder.set_stream_callback(boom)
        # Should NOT propagate
        recorder._callback(_loud_chunk(), 1600, None, None)


class TestMaxDurationWatchdog:
    def test_watchdog_fires_callback_after_deadline(self, recorder):
        triggered = []
        recorder._max_recording_seconds = 0.05
        recorder._on_max_duration_reached = lambda: triggered.append(True)
        recorder._start_monotonic = time.monotonic()
        time.sleep(0.06)
        recorder._callback(_loud_chunk(), 1600, None, None)
        assert triggered == [True]

    def test_watchdog_disarms_after_firing(self, recorder):
        count = 0

        def cb():
            nonlocal count
            count += 1

        recorder._max_recording_seconds = 0.01
        recorder._on_max_duration_reached = cb
        recorder._start_monotonic = time.monotonic() - 1  # already overdue
        for _ in range(5):
            recorder._callback(_loud_chunk(), 1600, None, None)
        # Should fire exactly once even though we processed 5 chunks
        assert count == 1


def test_start_returns_false_and_preserves_last_error(monkeypatch):
    monkeypatch.setattr(audio_mod.sd, "InputStream", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(audio_mod.sd, "_terminate", lambda: None)
    monkeypatch.setattr(audio_mod.sd, "_initialize", lambda: None)
    monkeypatch.setattr(audio_mod.time, "sleep", lambda seconds: None)

    recorder = AudioRecorder(sample_rate=16000)

    assert recorder.start() is False
    assert recorder.is_recording is False
    assert isinstance(recorder.last_start_error, RuntimeError)
