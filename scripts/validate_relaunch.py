import argparse
import faulthandler
import json
import os
from pathlib import Path
import signal
import sys
import time

import rumps

from speaktype.app import SpeakTypeApp
from speaktype.config import CONFIG_DIR, DEFAULT_CONFIG, load_config, save_config


parser = argparse.ArgumentParser()
parser.add_argument("--report", type=Path, required=True)
parser.add_argument("--verify-after", action="store_true")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
assert CONFIG_DIR.is_relative_to(root / "work")
assert os.environ.get("SPEAKTYPE_TEST_BUNDLE")
assert Path(sys.prefix).resolve().is_relative_to(Path(os.environ["SPEAKTYPE_TEST_BUNDLE"]).resolve())
if args.verify_after:
    import AppKit

    report = json.loads(args.report.read_text(encoding="utf-8"))
    try:
        os.kill(report["old_pid"], 0)
    except ProcessLookupError:
        pass
    else:
        raise AssertionError("The original process is still running")
    expected = str(Path(report["bundle"]) / "Contents/MacOS/SpeakType")
    running = [app for app in AppKit.NSWorkspace.sharedWorkspace().runningApplications()
               if app.executableURL() and str(app.executableURL().path()) == expected]
    assert len(running) == 1, [int(app.processIdentifier()) for app in running]
    config = load_config()
    assert config["ui_language"] == "en" and config["last_seen_version"] == "3.0.0"
    assert not config["permission_restart_pending_after_refresh"]
    log = (CONFIG_DIR / "speaktype.log").read_text(encoding="utf-8")
    assert "Starting SpeakType v3.0.0" in log and "ASR engine loaded" in log
    assert "Hotkey backend active: nsevent" in log
    assert args.report.with_suffix(".fault.log").stat().st_size == 0, "The original process reported a native failure"
    report.update(new_pid=int(running[0].processIdentifier()), original_process_exited=True,
                  isolated_configuration_preserved=True, native_main_restarted=True,
                  real_asr_loaded_after_restart=True, native_shortcut_running=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0)
fault_log = args.report.with_suffix(".fault.log").open("w", encoding="utf-8")
faulthandler.enable(file=fault_log, all_threads=True)
faulthandler.register(signal.SIGTRAP, file=fault_log, all_threads=True, chain=True)
save_config({**DEFAULT_CONFIG, "setup_completed": False, "ui_language": "en",
             "polish_enabled": False, "translate_enabled": False,
             "llm_model": "qwen3-vl:2b-instruct", "sound_feedback": False})
application = SpeakTypeApp()
started = time.monotonic()


def restart_when_ready(timer):
    assert time.monotonic() - started < 150, application._main_state
    if application._main_controller is None or not application.asr._loaded:
        return
    if not application._main_state.get("ready"):
        return
    timer.stop()
    report = {"old_pid": os.getpid(), "config_dir": str(CONFIG_DIR),
              "bundle": os.environ["SPEAKTYPE_TEST_BUNDLE"],
              "phase_before_relaunch": application._main_state["phase"],
              "readiness_before_relaunch": application._main_state["readiness"]}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"RELAUNCHING {os.getpid()}", flush=True)
    application._relaunch_app()


timer = rumps.Timer(restart_when_ready, 0.25)
timer.start()
application.run()
