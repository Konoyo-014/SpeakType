"""Tests for the StreamingTranscriber callback plumbing."""

import builtins
import threading
import time
from types import SimpleNamespace

import pytest

from speaktype.streaming import StreamingTranscriber, _extract_text


class _FakeASR:
    """Minimal ASR engine stub used by StreamingTranscriber."""

    def __init__(self, model=None, loaded=True, backend="qwen"):
        self.model = model
        self._loaded = loaded
        self.backend = backend


class _FakeStreamingModel:
    """Model with a native stream_transcribe API that yields several frames."""

    def __init__(self, frames):
        self._frames = frames
        self.calls = []

    def stream_transcribe(self, **kwargs):
        self.calls.append(kwargs)
        for frame in self._frames:
            yield frame


def test_extract_text_from_object():
    obj = SimpleNamespace(text="hello")
    assert _extract_text(obj) == "hello"


def test_extract_text_from_dict():
    assert _extract_text({"text": "hi"}) == "hi"


def test_extract_text_from_str():
    assert _extract_text("plain") == "plain"


def test_extract_text_handles_none():
    assert _extract_text(None) == ""


def test_extract_text_handles_unknown():
    assert _extract_text(42) == ""


def test_emit_partial_invokes_callback():
    received = []
    asr = _FakeASR(loaded=False)  # loaded=False means stream loop won't run
    transcriber = StreamingTranscriber(asr, on_partial_text=received.append)
    transcriber._emit_partial("  hello ")
    assert received == ["hello"]
    assert transcriber.accumulated_text == "hello"


def test_emit_partial_skips_empty():
    received = []
    asr = _FakeASR(loaded=False)
    transcriber = StreamingTranscriber(asr, on_partial_text=received.append)
    transcriber._emit_partial("")
    transcriber._emit_partial("   ")
    assert received == []


def test_stop_returns_accumulated_text():
    asr = _FakeASR(loaded=False)
    transcriber = StreamingTranscriber(asr, on_partial_text=lambda _: None)
    transcriber._accumulated_text = "captured"
    assert transcriber.stop() == "captured"


def test_stream_loop_aborts_when_asr_not_loaded():
    asr = _FakeASR(loaded=False)
    received = []
    transcriber = StreamingTranscriber(asr, on_partial_text=received.append)
    # Run the loop directly — it should bail immediately.
    transcriber._running = True
    transcriber._stream_loop("auto")
    assert received == []


def test_run_native_stream_accumulates_token_deltas():
    """mlx-audio yields one token at a time as a delta. The transcriber
    must accumulate them locally and emit a growing string."""
    received = []
    model = _FakeStreamingModel(frames=[
        SimpleNamespace(text="hello"),
        SimpleNamespace(text=" "),
        SimpleNamespace(text="world"),
    ])
    asr = _FakeASR(model=model, loaded=True)
    transcriber = StreamingTranscriber(asr, on_partial_text=received.append)
    transcriber._running = True

    transcriber._run_native_stream(model, audio_data=b"placeholder", language="auto")

    assert received == ["hello", "hello", "hello world"]
    assert transcriber.accumulated_text == "hello world"
    assert model.calls and model.calls[0]["audio"] == b"placeholder"


def test_run_native_stream_skips_empty_yields():
    """The is_final marker yields text='' — must be ignored."""
    received = []
    model = _FakeStreamingModel(frames=[
        SimpleNamespace(text="hi"),
        SimpleNamespace(text=""),  # final marker
        SimpleNamespace(text=" there"),
    ])
    asr = _FakeASR(model=model, loaded=True)
    transcriber = StreamingTranscriber(asr, on_partial_text=received.append)
    transcriber._running = True

    transcriber._run_native_stream(model, audio_data=b"x", language="auto")

    assert received == ["hi", "hi there"]


def test_run_native_stream_passes_language_when_specified():
    model = _FakeStreamingModel(frames=[SimpleNamespace(text="hi")])
    asr = _FakeASR(model=model, loaded=True)
    transcriber = StreamingTranscriber(asr, on_partial_text=lambda _: None)
    transcriber._running = True
    transcriber._run_native_stream(model, audio_data=b"x", language="zh")
    assert model.calls[0]["language"] == "zh"


def test_run_native_stream_omits_language_for_auto():
    model = _FakeStreamingModel(frames=[SimpleNamespace(text="hi")])
    asr = _FakeASR(model=model, loaded=True)
    transcriber = StreamingTranscriber(asr, on_partial_text=lambda _: None)
    transcriber._running = True
    transcriber._run_native_stream(model, audio_data=b"x", language="auto")
    assert "language" not in model.calls[0]


def test_run_native_stream_stops_when_running_flag_clears():
    received = []
    model = _FakeStreamingModel(frames=[
        SimpleNamespace(text="one"),
        SimpleNamespace(text="two"),
        SimpleNamespace(text="three"),
    ])
    asr = _FakeASR(model=model, loaded=True)
    transcriber = StreamingTranscriber(asr, on_partial_text=received.append)

    # Custom callback that flips _running to False after the first emit.
    def stop_after_first(text):
        received.append(text)
        transcriber._running = False

    transcriber._on_partial_text = stop_after_first
    transcriber._running = True
    transcriber._run_native_stream(model, audio_data=b"x", language="auto")

    # First yield "one" → accumulated "one" → callback fires, flips flag → loop stops
    assert received == ["one"]


def test_emit_partial_filters_regressive_snapshots():
    """When the loop kicks off a fresh transcription pass over a larger
    audio buffer, the first few snapshots are short and would cause the
    overlay to flicker. They should be filtered out."""
    received = []
    asr = _FakeASR(loaded=False)
    transcriber = StreamingTranscriber(asr, on_partial_text=received.append)

    transcriber._emit_partial("hello world how are you")
    # New pass starts from scratch — these should be ignored.
    transcriber._emit_partial("hi")
    transcriber._emit_partial("hello")
    transcriber._emit_partial("hello world")
    # Once the new pass catches up, it gets emitted again.
    transcriber._emit_partial("hello world how are you doing")

    assert received == [
        "hello world how are you",
        "hello world how are you doing",
    ]


def test_emit_partial_allows_equal_length_replacement():
    """Same length still passes the filter — useful for the model
    correcting a token without growing the total length."""
    received = []
    asr = _FakeASR(loaded=False)
    transcriber = StreamingTranscriber(asr, on_partial_text=received.append)

    transcriber._emit_partial("hello world")
    transcriber._emit_partial("hello there")  # same length, different content

    assert received == ["hello world", "hello there"]


def test_callback_errors_do_not_break_emission():
    def boom(_text):
        raise RuntimeError("nope")

    asr = _FakeASR(loaded=True)
    transcriber = StreamingTranscriber(asr, on_partial_text=boom)
    # Should not raise — error is caught and logged.
    transcriber._emit_partial("anything")
    assert transcriber.accumulated_text == "anything"


def test_feed_audio_buffers_chunks():
    asr = _FakeASR(loaded=True)
    transcriber = StreamingTranscriber(asr, on_partial_text=lambda _: None)
    transcriber.feed_audio(_FakeChunk([1, 2, 3]))
    transcriber.feed_audio(_FakeChunk([4, 5, 6]))
    assert len(transcriber._audio_buffer) == 2


def test_feed_audio_ignores_none():
    asr = _FakeASR(loaded=True)
    transcriber = StreamingTranscriber(asr, on_partial_text=lambda _: None)
    transcriber.feed_audio(None)
    assert transcriber._audio_buffer == []


class _FakeChunk:
    """Stand-in for a numpy chunk that supports `.copy()`."""

    def __init__(self, data):
        self.data = data

    def copy(self):
        return _FakeChunk(list(self.data))


def test_run_chunked_skips_non_qwen_backends(monkeypatch):
    received = []
    asr = _FakeASR(model="whisper-model", loaded=True, backend="whisper")
    transcriber = StreamingTranscriber(asr, on_partial_text=received.append)

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("mlx_audio"):
            raise AssertionError("mlx_audio should not be imported for whisper backend")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    transcriber._run_chunked(audio_data=b"x", language="auto")

    assert received == []
