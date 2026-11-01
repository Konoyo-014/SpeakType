import argparse
import json
import os
from pathlib import Path
import sys
import threading
import time

bundle = Path(os.environ["SPEAKTYPE_TEST_BUNDLE"]).resolve() if os.environ.get("SPEAKTYPE_TEST_BUNDLE") else None
root = Path(__file__).resolve().parents[1]
runtime = bundle / "Contents/Resources/lib/python3.10" if bundle else root
sys.path.insert(0, str(runtime))
if bundle:
    assert Path(sys.prefix).resolve().is_relative_to(bundle), "Run with the app verify_runtime launcher"
    sys.path.insert(1, str(bundle / "Contents/Resources/lib/python310.zip"))
    sys.path.insert(2, str(runtime / "lib-dynload"))

import AppKit
from Foundation import NSDate, NSRunLoop
import soundfile as sf

from speaktype.app import SpeakTypeApp
from speaktype.config import CONFIG_DIR, DEFAULT_CONFIG, save_config
from speaktype.context import get_active_app
from speaktype.inserter import _prepare_target_app, _restore_pasteboard, _snapshot_pasteboard
from speaktype.polish import PolishEngine

parser = argparse.ArgumentParser()
parser.add_argument("--ollama-model", default="qwen3-vl:2b-instruct")
parser.add_argument("--full-pipeline", action="store_true")
parser.add_argument("--report", type=Path)
args = parser.parse_args()

assert CONFIG_DIR.is_relative_to(root / "work"), "Use an isolated SPEAKTYPE_CONFIG_DIR under work"
config = {**DEFAULT_CONFIG, "setup_completed": True, "polish_enabled": False,
          "translate_enabled": False, "streaming_preview": False, "sound_feedback": False,
          "hotword_learning_enabled": False, "hotword_context_enabled": False}
save_config(config)
application = SpeakTypeApp()
application.asr.load()
if application.asr._warmup_thread:
    application.asr._warmup_thread.join(timeout=120)
samples, rate = sf.read(root / "work/audio-validation/english.wav", dtype="float32")
assert rate == 16000
pb = AppKit.NSPasteboard.generalPasteboard()
original = _snapshot_pasteboard(pb)
results = []

def advance():
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.05))

def wait_for(worker):
    deadline = time.monotonic() + 120
    while worker.is_alive() and time.monotonic() < deadline:
        advance()
    assert not worker.is_alive(), "The real dictation worker did not finish"
    advance()

def dictate():
    _prepare_target_app(bundle_id="com.apple.TextEdit")
    assert get_active_app()["bundle_id"] == "com.apple.TextEdit", "Focus the dedicated TextEdit test document"
    worker = threading.Thread(target=application._process_audio, args=(samples.copy(), len(samples) / rate))
    application._processing_thread = worker
    worker.start()
    wait_for(worker)

commands = "insert, fail, copy, retry, session, polish, translate, finish" if args.full_pipeline else "insert, fail, copy, retry, session, finish"
print(f"READY: use a dedicated TextEdit document; commands: {commands}", flush=True)
try:
    for line in sys.stdin:
        command = line.strip()
        if command in {"insert", "fail"}:
            dictate()
            entry = application.history.get_recent(1)[0]
            expected = "inserted" if command == "insert" else "failed"
            assert entry["outcome"] == expected, entry
            assert "meeting notes" in entry["polished"].lower(), entry
            results.append({"command": command, "entry": entry})
        elif command == "copy":
            application._copy_last_dictation(None)
            assert pb.stringForType_(AppKit.NSPasteboardTypeString) == application._latest_dictation["polished"]
            results.append({"command": command, "verified": True})
        elif command == "retry":
            _prepare_target_app(bundle_id="com.apple.TextEdit")
            assert get_active_app()["bundle_id"] == "com.apple.TextEdit"
            entry_id = application._latest_dictation["id"]
            application._insert_last_dictation(None)
            wait_for(application._processing_thread)
            entry = application.history.get_recent(1)[0]
            assert entry["id"] == entry_id and entry["outcome"] == "inserted", entry
            results.append({"command": command, "entry": entry})
        elif command == "session":
            application.config["history_enabled"] = False
            previous_count = len(application.history.snapshot())
            dictate()
            assert len(application.history.snapshot()) == previous_count
            assert not application._latest_dictation.get("id")
            application._copy_last_dictation(None)
            assert pb.stringForType_(AppKit.NSPasteboardTypeString) == application._latest_dictation["polished"]
            results.append({"command": command, "verified": True})
        elif command in {"polish", "translate"}:
            assert args.full_pipeline
            application.config.update({"history_enabled": True, "polish_enabled": True,
                                       "translate_enabled": command == "translate", "translate_target": "zh",
                                       "llm_model": args.ollama_model})
            application.polish_engine = PolishEngine(model=args.ollama_model)
            assert application.polish_engine.check_available(), application.polish_engine.last_error
            dictate()
            entry = application.history.get_recent(1)[0]
            assert entry["outcome"] == "inserted" and "meeting notes" in entry["raw"].lower(), entry
            assert not application.polish_engine.last_error, application.polish_engine.last_error
            if command == "polish":
                assert "meeting" in entry["polished"].lower(), entry
            else:
                assert any("\u4e00" <= char <= "\u9fff" for char in entry["polished"]), entry
            results.append({"command": command, "model": args.ollama_model, "entry": entry})
        elif command == "finish":
            expected_commands = ["insert", "fail", "copy", "retry", "session"]
            if args.full_pipeline:
                expected_commands.extend(["polish", "translate"])
            assert [result["command"] for result in results] == expected_commands
            destination = args.report or root / "work" / ("bundle-delivery-report.json" if bundle else "delivery-report.json")
            destination.write_text(json.dumps({"runtime": str(bundle) if bundle else "source", "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"REPORT {destination}", flush=True)
            break
        else:
            raise ValueError(f"Unknown validation command: {command}")
        print(f"VERIFIED {command}", flush=True)
finally:
    application._status_overlay.hide()
    application._cancel_edit_observation()
    time.sleep(1)
    _restore_pasteboard(pb, original)
