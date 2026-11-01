import argparse
import gc
import json
import logging
import os
from pathlib import Path
import sys
import time
import weakref

root = Path(__file__).resolve().parents[1]
bundle = os.environ.get("SPEAKTYPE_TEST_BUNDLE")
if not bundle:
    sys.path.insert(0, str(root))

import AppKit
import rumps

from speaktype.app import SpeakTypeApp
from speaktype.config import CONFIG_DIR, DEFAULT_CONFIG, save_config


parser = argparse.ArgumentParser()
parser.add_argument("--stage", choices=("loading", "load_async", "warmup", "timeout", "replaced"), required=True)
parser.add_argument("--report", type=Path, required=True)
args = parser.parse_args()
assert CONFIG_DIR.is_relative_to(root / "work")
assert args.report.resolve().is_relative_to(root / "work")
if bundle:
    assert Path(sys.prefix).resolve().is_relative_to(Path(bundle).resolve())
    assert Path(sys.modules["speaktype.app"].__file__).resolve().is_relative_to(Path(bundle).resolve())
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
save_config({**DEFAULT_CONFIG, "setup_completed": True, "polish_enabled": False,
             "translate_enabled": False, "sound_feedback": False,
             "llm_model": "qwen3-vl:2b-instruct", "hotword_learning_enabled": False,
             "hotword_context_enabled": False})
application = SpeakTypeApp()
runtime = {"engine": application.asr, "load_started": False}
started = time.monotonic()


def check_and_quit(timer):
    assert time.monotonic() - started < 180, application._main_state
    engine = runtime["engine"]
    if not runtime["load_started"]:
        runtime["load_started"] = True
        if args.stage == "load_async":
            engine.load_async()
        else:
            application._do_setup()
        return
    if args.stage in {"loading", "load_async"}:
        if not engine._load_lock.locked() or engine._loaded:
            return
    else:
        warmup = engine._warmup_thread
        if warmup is None or not warmup.is_alive():
            assert not engine._warmed, "The real warmup completed before observation"
            return
    timer.stop()
    report = {"runtime": bundle or "source", "stage": args.stage,
              "pid": os.getpid(), "model": engine.model_name,
              "module_path": str(Path(sys.modules["speaktype.app"].__file__).resolve()),
              "prefix": sys.prefix, "loaded_before_quit": engine._loaded,
              "load_lock_held_before_quit": engine._load_lock.locked(),
              "warmup_alive_before_quit": bool(engine._warmup_thread and engine._warmup_thread.is_alive())}
    if args.stage == "replaced":
        application._apply_settings({**application.config, "asr_model": "mlx-community/Qwen3-ASR-0.6B-4bit"})
        assert application.asr is not engine and not application.asr._loaded
        assert engine._warmup_thread in application._active_model_workers()
        report["old_engine_warmup_tracked_after_settings_change"] = True
    if args.stage == "timeout":
        assert not application._prepare_to_quit(timeout=0)
        assert not application._quitting and application._active_model_workers()
        readiness_timer = getattr(application, "_readiness_timer", None)
        if readiness_timer:
            assert readiness_timer.is_alive()
        report["zero_deadline_kept_application_alive"] = True
        report["readiness_timer_restarted"] = bool(readiness_timer)
        assert application._readiness_thread is not None
        application._readiness_thread.join(timeout=15)
        assert not application._readiness_thread.is_alive()
        assert application._main_state["ready"]
        report["actual_loaded_asr_readiness_restored"] = True
    report["workers_before_quit"] = [{"name": worker.name, "ident": worker.ident}
                                     for worker in application._active_model_workers()]
    quit_started = time.monotonic()
    assert application._prepare_to_quit(timeout=120)
    report["quit_wait_seconds"] = time.monotonic() - quit_started
    assert not application._active_model_workers()
    assert engine._loaded and engine._warmed
    assert not engine._warmup_thread.is_alive()
    if engine._load_thread is not None:
        assert not engine._load_thread.is_alive()
    report["real_model_loaded"] = True
    report["real_warmup_completed"] = True
    report["all_tracked_workers_finished"] = True
    if args.stage == "replaced":
        old = weakref.ref(engine)
        runtime.pop("engine")
        del engine
        gc.collect()
        assert old() is None
        report["unused_old_engine_released"] = True
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"NATIVE_QUIT {args.report}", flush=True)
    application._finish_quit()


monitor = rumps.Timer(check_and_quit, 0.02)
monitor.start()
application.run()
