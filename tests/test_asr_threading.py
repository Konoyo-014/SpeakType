"""Tests for ASREngine.load() concurrency."""

import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

from speaktype.asr import ASREngine


class TestLoadIsSingleShot:
    def test_concurrent_loads_only_run_once(self):
        engine = ASREngine()
        call_count = {"count": 0}

        def fake_load_qwen(progress_callback=None):
            call_count["count"] += 1
            engine._loaded = True

        with patch.object(engine, "_load_qwen", side_effect=fake_load_qwen):
            threads = [threading.Thread(target=engine.load) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert call_count["count"] == 1
        assert engine._loaded

    def test_already_loaded_short_circuits(self):
        engine = ASREngine()
        engine._loaded = True
        with patch.object(engine, "_load_qwen") as mocked:
            engine.load()
            mocked.assert_not_called()

    def test_load_async_reuses_existing_worker(self):
        engine = ASREngine()
        release = threading.Event()

        def fake_load(progress_callback=None):
            release.wait(timeout=1)

        with patch.object(engine, "load", side_effect=fake_load):
            first = engine.load_async()
            second = engine.load_async()
            assert first is second
            release.set()
            first.join(timeout=1)

    def test_transcribe_in_memory_audio_skips_unlink(self):
        engine = ASREngine()
        engine._loaded = True
        engine.backend = "qwen"
        fake_audio = object()

        with patch.object(engine, "_transcribe_qwen", return_value="ok") as transcribe_qwen, patch("speaktype.asr.os.unlink") as unlink:
            assert engine.transcribe(fake_audio) == "ok"

        transcribe_qwen.assert_called_once_with(fake_audio, "auto")
        unlink.assert_not_called()

    def test_transcribe_file_path_unlinks_after_success(self):
        engine = ASREngine()
        engine._loaded = True
        engine.backend = "qwen"

        with patch.object(engine, "_transcribe_qwen", return_value="ok") as transcribe_qwen, patch("speaktype.asr.os.unlink") as unlink:
            assert engine.transcribe("/tmp/fake.wav") == "ok"

        transcribe_qwen.assert_called_once_with("/tmp/fake.wav", "auto")
        unlink.assert_called_once_with("/tmp/fake.wav")

    def test_transcribe_serializes_inference_calls(self):
        engine = ASREngine()
        engine._loaded = True
        engine.backend = "qwen"
        active = 0
        max_active = 0
        active_lock = threading.Lock()

        def fake_transcribe(_audio, _language):
            nonlocal active, max_active
            with active_lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.02)
            with active_lock:
                active -= 1
            return "ok"

        with patch.object(engine, "_transcribe_qwen", side_effect=fake_transcribe):
            threads = [threading.Thread(target=lambda: engine.transcribe(object())) for _ in range(5)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        assert max_active == 1

    def test_qwen_transcribe_uses_temp_output_path_and_cleans_mlx_transcript(self, tmp_path, monkeypatch):
        engine = ASREngine()
        engine.model = object()
        output_stem = str(tmp_path / "mlx-output")
        calls = []

        def fake_generate_transcription(**kwargs):
            calls.append(kwargs)
            (tmp_path / "mlx-output.txt").write_text("leaked", encoding="utf-8")
            return SimpleNamespace(text="ok")

        monkeypatch.setattr("speaktype.asr._make_temp_transcript_output_path", lambda: output_stem)
        monkeypatch.setattr("mlx_audio.stt.generate.generate_transcription", fake_generate_transcription)

        assert engine._transcribe_qwen(audio_input=object(), language="auto") == "ok"

        assert calls and calls[0]["output_path"] == output_stem
        assert not (tmp_path / "mlx-output.txt").exists()
