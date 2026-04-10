"""Tests for ASREngine.load() concurrency."""

import threading
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
