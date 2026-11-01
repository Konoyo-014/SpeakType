import json
import os
from pathlib import Path
import sys
import threading
import time

root = Path(__file__).resolve().parents[1]
bundle = os.environ.get("SPEAKTYPE_TEST_BUNDLE")
if not bundle:
    sys.path.insert(0, str(root))

import soundfile as sf

from speaktype.asr import ASREngine
from speaktype.streaming import StreamingTranscriber


if bundle:
    assert Path(sys.prefix).resolve().is_relative_to(Path(bundle).resolve())
    assert Path(sys.modules["speaktype.asr"].__file__).resolve().is_relative_to(Path(bundle).resolve())
engine = ASREngine()
engine.load()
if engine._warmup_thread:
    engine._warmup_thread.join(timeout=120)
    assert not engine._warmup_thread.is_alive()
report = {"runtime": bundle or "source", "cases": []}
for name, language, expected in (("english", "en", "meeting"), ("chinese", "zh", "会议记录")):
    samples, rate = sf.read(root / "work/audio-validation" / f"{name}.wav", dtype="float32")
    assert rate == 16000
    partials = []
    streaming = StreamingTranscriber(engine, on_partial_text=partials.append)
    streaming.start(language=language)
    for start in range(0, len(samples), 4800):
        streaming.feed_audio(samples[start:start + 4800])
        time.sleep(0.3)
    deadline = time.monotonic() + 30
    while expected not in streaming.accumulated_text.lower() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert partials and expected in streaming.accumulated_text.lower(), partials
    final = []

    def transcribe_final():
        final.append(engine.transcribe(samples, language=language))

    worker = threading.Thread(target=transcribe_final)
    worker.start()
    worker.join(timeout=30)
    assert not worker.is_alive() and len(final) == 1, final
    assert expected in final[0].lower(), final
    preview = streaming.stop(wait=True)
    snapshot = streaming.snapshot()
    assert expected in preview.lower()
    assert snapshot.covered_samples > 0
    assert all("\ufffd" not in text for text in partials), partials
    count = len(partials)
    time.sleep(0.2)
    assert len(partials) == count
    report["cases"].append({"language": language, "partials": partials, "preview": preview,
                            "final": final[0], "covered_samples": snapshot.covered_samples,
                            "concurrent_final_completed": True, "stopped_callbacks": True})
destination = root / "work" / ("bundle-streaming-report.json" if bundle else "streaming-report.json")
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"REPORT {destination}")
