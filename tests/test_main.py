"""Tests for the standalone smoke-test entrypoint."""

import sys
from types import SimpleNamespace

import main as main_entry


def test_pipeline_returns_failure_for_empty_transcription(monkeypatch, capsys):
    class FakePolishEngine:
        def __init__(self):
            self._available = False

        def check_available(self):
            return False

    class FakeASREngine:
        def load(self):
            return None

        def transcribe(self, audio_path):
            return ""

    class FakeAudioRecorder:
        def start(self):
            return None

        def stop(self):
            return "/tmp/fake.wav"

    monkeypatch.setitem(sys.modules, "speaktype.polish", SimpleNamespace(PolishEngine=FakePolishEngine))
    monkeypatch.setitem(sys.modules, "speaktype.asr", SimpleNamespace(ASREngine=FakeASREngine))
    monkeypatch.setitem(sys.modules, "speaktype.audio", SimpleNamespace(AudioRecorder=FakeAudioRecorder))
    monkeypatch.setitem(sys.modules, "time", SimpleNamespace(sleep=lambda _: None))

    result = main_entry.test_pipeline()
    output = capsys.readouterr().out

    assert result == 1
    assert "Empty transcription" in output


def test_pipeline_returns_success_for_non_empty_transcription(monkeypatch, capsys):
    class FakePolishEngine:
        def __init__(self):
            self._available = True

        def check_available(self):
            return True

        def polish(self, text):
            return "Hello."

    class FakeASREngine:
        def load(self):
            return None

        def transcribe(self, audio_path):
            return "hello"

    class FakeAudioRecorder:
        def start(self):
            return None

        def stop(self):
            return "/tmp/fake.wav"

    monkeypatch.setitem(sys.modules, "speaktype.polish", SimpleNamespace(PolishEngine=FakePolishEngine))
    monkeypatch.setitem(sys.modules, "speaktype.asr", SimpleNamespace(ASREngine=FakeASREngine))
    monkeypatch.setitem(sys.modules, "speaktype.audio", SimpleNamespace(AudioRecorder=FakeAudioRecorder))
    monkeypatch.setitem(sys.modules, "time", SimpleNamespace(sleep=lambda _: None))

    result = main_entry.test_pipeline()
    output = capsys.readouterr().out

    assert result == 0
    assert "Raw: hello" in output
    assert "Polished: Hello." in output
