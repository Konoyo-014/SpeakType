import argparse
import faulthandler
import gc
import json
import os
from pathlib import Path
import signal
import sys
import time

root = Path(__file__).resolve().parents[1]
bundle = os.environ.get("SPEAKTYPE_TEST_BUNDLE")
if not bundle:
    sys.path.insert(0, str(root))

import rumps

from speaktype.app import SpeakTypeApp
from speaktype.config import CONFIG_DIR, DEFAULT_CONFIG, save_config


parser = argparse.ArgumentParser()
parser.add_argument("--cycles", type=int, default=20)
parser.add_argument("--all-windows", action="store_true")
parser.add_argument("--report", type=Path, required=True)
args = parser.parse_args()
assert CONFIG_DIR.is_relative_to(root / "work")
if bundle:
    assert Path(sys.prefix).resolve().is_relative_to(Path(bundle).resolve())
    assert Path(sys.modules["speaktype.app"].__file__).resolve().is_relative_to(Path(bundle).resolve())
else:
    assert Path(sys.modules["speaktype.app"].__file__).resolve().is_relative_to(root / "speaktype")
args.report.parent.mkdir(parents=True, exist_ok=True)
fault_log = args.report.with_suffix(".fault.log").open("w", encoding="utf-8")
faulthandler.enable(file=fault_log, all_threads=True)
faulthandler.register(signal.SIGTRAP, file=fault_log, all_threads=True, chain=True)
save_config({**DEFAULT_CONFIG, "setup_completed": True, "ui_language": "en",
             "polish_enabled": False, "translate_enabled": False,
             "llm_model": "qwen3-vl:2b-instruct", "sound_feedback": False,
             "hotword_learning_enabled": False, "hotword_context_enabled": False})
application = SpeakTypeApp()
windows = [("_open_settings", "_settings_controller")]
if args.all_windows:
    windows.extend([("_open_dict", "_dict_controller"), ("_show_stats", "_stats_controller"),
                    ("_show_history", "_history_controller"), ("_open_hotwords_window", "_hotwords_controller"),
                    ("_show_diagnostics", "_diagnostics_controller"),
                    ("_show_main_window", "_main_controller"), ("_show_setup_center", "_setup_center"),
                    ("help", "_help_controller"), ("wizard", "_wizard_controller")])
report = {"runtime": bundle or "source", "pid": os.getpid(), "checks": [], "language_changes": []}
phase = 0
started = time.monotonic()


def save_report():
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def tick(timer):
    global phase
    assert time.monotonic() - started < 180, report
    if not application.asr._loaded or (application.asr._warmup_thread and application.asr._warmup_thread.is_alive()):
        return
    cycle, stage = divmod(phase, len(windows) * 4)
    if cycle == args.cycles:
        timer.stop()
        report.update(completed_cycles=cycle, actual_event_loop=True, passed=True)
        save_report()
        print(f"REPORT {args.report}", flush=True)
        application._quit(None)
        return
    index, action = divmod(stage, 4)
    method, name = windows[index]
    report["next_action"] = {"cycle": cycle, "window": name, "action": action}
    save_report()
    if action in (0, 2):
        if action == 2:
            gc.collect()
        if method == "help":
            application._show_setup_center("help")
        elif method == "wizard":
            application._show_setup_wizard()
        else:
            getattr(application, method)(None)
        controller = getattr(application, name)
        assert controller.window.isVisible()
        assert not controller.window.isReleasedWhenClosed()
        report["checks"].append({"cycle": cycle, "window": name, "action": "open" if action == 0 else "reopen",
                                  "number": int(controller.window.windowNumber())})
    else:
        getattr(application, name).window.close()
        if bundle and index == len(windows) - 1 and action == 3:
            previous_main = application._main_controller
            language = "zh" if application.config["ui_language"] == "en" else "en"
            item = application._ui_lang_items[language][0]
            application._make_ui_lang_callback(language)(item)
            assert application.config["ui_language"] == language
            assert previous_main._disposed
            assert previous_main._edit_timer is None and previous_main._undo_manager is None
            assert previous_main._delegate._controller is None
            assert application._main_controller is not previous_main
            report["language_changes"].append(language)
    phase += 1


timer = rumps.Timer(tick, 0.1)
timer.start()
application.run()
