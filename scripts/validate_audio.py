import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading
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
import AppKit
from Foundation import NSDate, NSRunLoop

from speaktype import __version__
from speaktype.asr import ASREngine
from speaktype.audio import AudioRecorder
import sounddevice as sd
from speaktype.model_download import is_model_cached
from speaktype.polish import PolishEngine

if bundle:
    for module_name in ("numpy", "soundfile", "scipy.signal", "speaktype.asr", "speaktype.polish"):
        assert Path(sys.modules[module_name].__file__).resolve().is_relative_to(bundle), module_name


def start_recorder_with_event_loop(recorder):
    AppKit.NSApplication.sharedApplication()
    AppKit.NSApp.finishLaunching()
    results = []
    worker = threading.Thread(target=lambda: results.append(recorder.start()), daemon=True)
    worker.start()
    deadline = time.monotonic() + 20
    while worker.is_alive() and time.monotonic() < deadline:
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.02))
        while True:
            event = AppKit.NSApp.nextEventMatchingMask_untilDate_inMode_dequeue_(
                AppKit.NSEventMaskAny, NSDate.distantPast(), AppKit.NSDefaultRunLoopMode, True)
            if event is None:
                break
            AppKit.NSApp.sendEvent_(event)
        AppKit.NSApp.updateWindows()
    assert not worker.is_alive(), "Microphone start exceeded 20 seconds while the main event loop was running"
    assert results and results[0], recorder.last_start_error


parser = argparse.ArgumentParser()
capture_modes = parser.add_mutually_exclusive_group()
capture_modes.add_argument("--capture", action="store_true")
capture_modes.add_argument("--capture-only", action="store_true")
parser.add_argument("--capture-input", type=int)
parser.add_argument("--capture-output", type=int)
parser.add_argument("--ollama-model", default="qwen3-vl:2b-instruct")
parser.add_argument("--report", type=Path)
args = parser.parse_args()
if args.capture_input is not None and not (args.capture or args.capture_only):
    parser.error("--capture-input requires --capture or --capture-only")
if args.capture_output is not None and not args.capture:
    parser.error("--capture-output requires --capture")
logging.basicConfig(level=logging.INFO)
work = Path(__file__).resolve().parents[1] / "work" / "audio-validation"
work.mkdir(parents=True, exist_ok=True)
report_path = args.report or work / ("bundle-report.json" if bundle else "report.json")
if args.capture_only:
    input_index = sd.default.device[0] if args.capture_input is None else args.capture_input
    input_info = dict(sd.query_devices(input_index, kind="input"))
    recorder = AudioRecorder(device=args.capture_input)
    logging.info("Starting microphone-only capture: input %s (%s)", input_index, input_info["name"])
    start_recorder_with_event_loop(recorder)
    logging.info("Microphone-only capture started")
    try:
        time.sleep(5)
    finally:
        captured = recorder.stop_audio()
    assert captured is not None, recorder.last_stop_message
    capture_path = work / ("bundle-capture-only.wav" if bundle else "capture-only.wav")
    sf.write(capture_path, captured, recorder.sample_rate, subtype="FLOAT")
    report = {"version": __version__, "runtime": str(bundle) if bundle else "source",
              "validation": "microphone_capture_only", "speech_recognition_asserted": False,
              "microphone": {"input_index": int(input_index), "input_device": input_info,
                             "samples": len(captured), "sample_rate": recorder.sample_rate,
                             "seconds": len(captured) / recorder.sample_rate,
                             "peak": float(np.max(np.abs(captured))),
                             "rms": float(np.sqrt(np.mean(np.square(captured)))),
                             "audio_path": str(capture_path),
                             "audio_sha256": hashlib.sha256(capture_path.read_bytes()).hexdigest()}}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"REPORT {report_path}")
    raise SystemExit(0)
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
    input_index = sd.default.device[0] if args.capture_input is None else args.capture_input
    output_index = sd.default.device[1] if args.capture_output is None else args.capture_output
    input_info = dict(sd.query_devices(input_index, kind="input"))
    output_info = dict(sd.query_devices(output_index, kind="output"))
    assert output_index == sd.default.device[1], "afplay requires the selected output to be the current system default"
    output_rate = int(output_info["default_samplerate"])
    playback, source_rate = sf.read(work / "english.wav", dtype="float32")
    assert playback.ndim == 1
    recorder = AudioRecorder(device=args.capture_input)
    logging.info("Starting acoustic capture: input %s (%s)", input_index, input_info["name"])
    start_recorder_with_event_loop(recorder)
    logging.info("Acoustic microphone capture started")
    try:
        time.sleep(0.6)
        logging.info("Starting speaker playback: output %s (%s)", output_index, output_info["name"])
        subprocess.run(["afplay", str(work / "english.wav")], check=True)
        logging.info("Speaker playback completed")
        time.sleep(0.8)
    finally:
        captured = recorder.stop_audio()
    assert captured is not None, recorder.last_stop_message
    capture_path = work / ("bundle-hardware-capture.wav" if bundle else "hardware-capture.wav")
    sf.write(capture_path, captured, recorder.sample_rate, subtype="FLOAT")
    captured_text = engine.transcribe(captured, language="en")
    report["microphone"] = {
        "input_index": int(input_index), "input_device": input_info,
        "output_index": int(output_index), "output_device": output_info,
        "system_default_devices": [int(index) for index in sd.default.device],
        "playback_source": "macOS built-in speech synthesis played through selected physical output",
        "playback_backend": "afplay using the verified system default output",
        "microphone_start": "AudioRecorder.start on background thread with main AppKit run loop",
        "playback_peak": float(np.max(np.abs(playback))), "output_sample_rate": output_rate,
        "playback_source_sample_rate": source_rate,
        "samples": len(captured), "sample_rate": recorder.sample_rate,
        "seconds": len(captured) / recorder.sample_rate,
        "peak": float(np.max(np.abs(captured))),
        "rms": float(np.sqrt(np.mean(np.square(captured)))),
        "whisper_detected": recorder.whisper_was_active,
        "audio_path": str(capture_path), "audio_sha256": hashlib.sha256(capture_path.read_bytes()).hexdigest(),
        "output": captured_text,
        "expected_words": ["meeting", "notes"],
        "expected_words_present": "meeting" in captured_text.lower() and "notes" in captured_text.lower(),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    assert "meeting" in captured_text.lower() and "notes" in captured_text.lower(), captured_text

report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
print(f"REPORT {report_path}")
