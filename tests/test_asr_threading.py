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

    def test_qwen_load_starts_background_warmup(self, monkeypatch):
        engine = ASREngine()
        calls = []

        monkeypatch.setattr("speaktype.model_download.is_model_cached", lambda model_name: True)
        monkeypatch.setattr("speaktype.model_download.get_cached_model_path", lambda model_name: None)
        monkeypatch.setattr("mlx_audio.stt.utils.load_model", lambda model_name: object())
        monkeypatch.setattr(engine, "warmup_async", lambda: calls.append("warmup"))

        engine._load_qwen()

        assert engine._loaded is True
        assert calls == ["warmup"]

    def test_qwen_load_prefers_cached_snapshot_path(self, monkeypatch, tmp_path):
        engine = ASREngine(model_name="model-a")
        calls = []
        cached_path = tmp_path / "snapshot"
        cached_path.mkdir()

        monkeypatch.setattr("speaktype.model_download.is_model_cached", lambda model_name: True)
        monkeypatch.setattr("speaktype.model_download.get_cached_model_path", lambda model_name: cached_path)
        monkeypatch.setattr("mlx_audio.stt.utils.load_model", lambda model_name: calls.append(model_name) or object())
        monkeypatch.setattr(engine, "warmup_async", lambda: None)

        engine._load_qwen()

        assert calls == [str(cached_path)]
        assert engine.model_name == "model-a"

    def test_qwen_load_falls_back_when_cached_snapshot_path_fails(self, monkeypatch, tmp_path):
        engine = ASREngine(model_name="model-a")
        calls = []
        cached_path = tmp_path / "snapshot"
        cached_path.mkdir()

        def fake_load_model(model_name):
            calls.append(model_name)
            if model_name == str(cached_path):
                raise RuntimeError("bad local cache")
            return object()

        monkeypatch.setattr("speaktype.model_download.is_model_cached", lambda model_name: True)
        monkeypatch.setattr("speaktype.model_download.get_cached_model_path", lambda model_name: cached_path)
        monkeypatch.setattr("mlx_audio.stt.utils.load_model", fake_load_model)
        monkeypatch.setattr(engine, "warmup_async", lambda: None)

        engine._load_qwen()

        assert calls == [str(cached_path), "model-a"]
        assert engine._loaded is True

    def test_warmup_qwen_uses_nonblocking_inference_slot(self, monkeypatch):
        engine = ASREngine()
        engine._loaded = True
        engine.backend = "qwen"
        calls = []

        monkeypatch.setattr(engine, "_transcribe_qwen", lambda audio, language: calls.append((len(audio), language)) or "")

        engine._warmup_qwen()

        assert calls == [(3200, "auto")]
        assert engine._warmed is True

    def test_warmup_qwen_skips_when_inference_busy(self, monkeypatch):
        engine = ASREngine()
        engine._loaded = True
        engine.backend = "qwen"
        engine.acquire_inference(blocking=True)

        monkeypatch.setattr(
            engine,
            "_transcribe_qwen",
            lambda audio, language: (_ for _ in ()).throw(AssertionError("warmup should not run")),
        )

        try:
            engine._warmup_qwen()
        finally:
            engine.release_inference()

        assert engine._warmed is False
