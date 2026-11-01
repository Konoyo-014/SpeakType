import argparse
import json
import os
from pathlib import Path
import sys
import threading

root = Path(__file__).resolve().parents[1]
bundle = os.environ.get("SPEAKTYPE_TEST_BUNDLE")
if not bundle:
    sys.path.insert(0, str(root))

import AppKit
from Foundation import NSDate, NSRunLoop

from speaktype.app import SpeakTypeApp
from speaktype.config import CONFIG_DIR, DEFAULT_CONFIG, save_config, write_json_file


parser = argparse.ArgumentParser()
parser.add_argument("--report", type=Path, required=True)
args = parser.parse_args()
assert CONFIG_DIR.is_relative_to(root / "work")
assert args.report.resolve().is_relative_to(root / "work")
if bundle:
    assert Path(sys.prefix).resolve().is_relative_to(Path(bundle).resolve())
    assert Path(sys.modules["speaktype.app"].__file__).resolve().is_relative_to(Path(bundle).resolve())
save_config({**DEFAULT_CONFIG, "setup_completed": True, "polish_enabled": False,
             "translate_enabled": False, "llm_model": "qwen3-vl:2b-instruct",
             "hotword_learning_enabled": False, "sound_feedback": False})
AppKit.NSApplication.sharedApplication()
application = SpeakTypeApp()
application._show_setup_center()
application._show_diagnostics(None)
center = application._setup_center
diagnostics = application._diagnostics_controller
started = threading.Event()
release = threading.Event()
written = CONFIG_DIR / "real-worker-write.json"


def write_after_release():
    started.set()
    assert release.wait(30)
    write_json_file(written, {"text": "退出等待结束后的真实写入 🙂 한국어"})


worker = center._start_worker(write_after_release, "SpeakTypeRecoveryFileWriter")
assert started.wait(5)
assert not application._prepare_to_quit(timeout=0)
assert not application._quitting
assert not center._shutting_down
application._show_setup_center()
application._show_diagnostics(None)
NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))
assert application._setup_center is center and center.window.isVisible()
assert application._diagnostics_controller.window.isVisible()
release.set()
worker.join(timeout=5)
assert not worker.is_alive()
assert json.loads(written.read_text(encoding="utf-8"))["text"] == "退出等待结束后的真实写入 🙂 한국어"
assert application._prepare_to_quit(timeout=30)
assert not application._active_model_workers()
assert not application.asr._loaded
report = {"runtime": bundle or "source", "prefix": sys.prefix,
          "module_path": str(Path(sys.modules["speaktype.app"].__file__).resolve()),
          "checks": ["A real setup-center worker waits, then commits a Unicode file through write_json_file",
                     "A zero quit deadline keeps the application running and resumes setup and diagnostics",
                     "Both actual native windows show and refresh after the postponed quit",
                     "The real file writer completes and a later quit preparation joins all remaining workers"],
          "asr_model_loaded": application.asr._loaded}
for window in list(AppKit.NSApplication.sharedApplication().windows()):
    if window.isVisible():
        window.close()
NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.05))
assert not any(window.isVisible() for window in AppKit.NSApplication.sharedApplication().windows())
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"REPORT {args.report}")
