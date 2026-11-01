import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time

bundle = Path(os.environ["SPEAKTYPE_TEST_BUNDLE"]).resolve() if os.environ.get("SPEAKTYPE_TEST_BUNDLE") else None
runtime = bundle / "Contents" / "Resources" / "lib" / "python3.10" if bundle else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(runtime))
if bundle:
    assert Path(sys.prefix).resolve().is_relative_to(bundle), "Run with the app verify_runtime launcher"
    sys.path.insert(1, str(bundle / "Contents/Resources/lib/python310.zip"))
    sys.path.insert(2, str(runtime / "lib-dynload"))

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from speaktype import __version__
from speaktype.asr import ASREngine
from speaktype.audio import AudioRecorder
from speaktype.model_download import is_model_cached
from speaktype.polish import PolishEngine

if bundle:
    for module_name in ("numpy", "soundfile", "scipy.signal", "speaktype.asr", "speaktype.polish"):
        assert Path(sys.modules[module_name].__file__).resolve().is_relative_to(bundle), module_name


parser = argparse.ArgumentParser()
parser.add_argument("--capture", action="store_true")
parser.add_argument("--ollama-model", default="qwen3-vl:2b-instruct")
parser.add_argument("--report", type=Path)
args = parser.parse_args()
logging.basicConfig(level=logging.INFO)
work = Path(__file__).resolve().parents[1] / "work" / "audio-validation"
work.mkdir(parents=True, exist_ok=True)
assert is_model_cached("mlx-community/Qwen3-ASR-1.7B-8bit"), "The complete default ASR model must be cached"
inputs = (
    ("english", "Samantha", "Please send the meeting notes tomorrow morning.", "en"),
    ("chinese", "Tingting", "请把今天的会议记录保存下来。", "zh"),
)
engine = ASREngine()
started = time.monotonic()
engine.load()
if engine._warmup_thread is not None:
    engine._warmup_thread.join(timeout=120)
    assert not engine._warmup_thread.is_alive(), "ASR warmup did not finish"
report = {"version": __version__, "runtime": str(bundle) if bundle else "source", "asr_model": engine.model_name,
          "load_seconds": round(time.monotonic() - started, 3), "cases": []}
for name, voice, sentence, language in inputs:
    path = work / f"{name}.wav"
    subprocess.run(["say", "-v", voice, "--file-format=WAVE", "--data-format=LEI16@16000",
                    "--channels=1", "-o", str(path), sentence], check=True)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    started = time.monotonic()
    text = engine.transcribe(path, language=language)
    assert path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == digest
    if language == "en":
        assert all(word in text.lower() for word in ("meeting", "notes", "tomorrow")), text
    else:
        assert "会议记录" in text, text
    report["cases"].append({"name": name, "input": sentence, "output": text,
                            "seconds": round(time.monotonic() - started, 3)})
    samples, sample_rate = sf.read(path, dtype="float32")
    samples = resample_poly(samples, 16000, sample_rate).astype(np.float32)
    in_memory_text = engine.transcribe(samples, language=language)
    assert "meeting" in in_memory_text.lower() if language == "en" else "会议记录" in in_memory_text
    report["cases"].append({"name": f"{name}_in_memory", "output": in_memory_text})

silence = engine.transcribe(np.zeros(32000, dtype=np.float32))
assert not silence.strip(), f"Silence produced text: {silence}"
report["cases"].append({"name": "silence", "output": silence})

polish = PolishEngine(model=args.ollama_model)
assert polish.check_available(), polish.last_error
polished = polish.polish("um please send the meeting notes tomorrow morning", language="en")
assert not polish.last_error and "meeting" in polished.lower() and "notes" in polished.lower(), (polished, polish.last_error)
translated = polish.translate("Please send the meeting notes tomorrow morning.", target_lang="zh")
assert not polish.last_error and any("\u4e00" <= char <= "\u9fff" for char in translated), (translated, polish.last_error)
report["ollama"] = {"model": polish.model, "polished": polished, "translated": translated}
report["ollama"]["language_cases"] = []
for language, sentence in (("en", "um thank you"), ("en", "uh yes"),
                           ("ko", "음 오늘 회의 내용을 정리해 주세요."),
                           ("ja", "ええと今日の会議の内容をまとめてください。")):
    result = polish.polish(sentence, language=language)
    assert result and not polish.last_error, (result, polish.last_error)
    if language == "en":
        assert not any("\u4e00" <= char <= "\u9fff" for char in result), result
        assert "thank" in result.lower() if "thank" in sentence else "yes" in result.lower(), result
    elif language == "ko":
        assert any("\uac00" <= char <= "\ud7af" for char in result), result
    else:
        assert any("\u3040" <= char <= "\u30ff" for char in result), result
    report["ollama"]["language_cases"].append({"language": language, "input": sentence, "output": result})

if args.capture:
    recorder = AudioRecorder()
    assert recorder.start(), recorder.last_start_error
    try:
        subprocess.run(["afplay", str(work / "english.wav")], check=True)
        time.sleep(0.4)
    finally:
        captured = recorder.stop_audio()
    assert captured is not None, recorder.last_stop_message
    captured_text = engine.transcribe(captured, language="en")
    assert "meeting" in captured_text.lower() and "notes" in captured_text.lower(), captured_text
    report["microphone"] = {"samples": len(captured), "output": captured_text}

report_path = args.report or work / ("bundle-report.json" if bundle else "report.json")
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
print(f"REPORT {report_path}")
