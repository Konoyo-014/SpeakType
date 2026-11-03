import argparse
import json
import logging
import os
from pathlib import Path
import sys
import threading
import time
from uuid import uuid4


parser = argparse.ArgumentParser()
parser.add_argument("--report", type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
run_directory = root / "work" / "microphone-lifecycle" / uuid4().hex
run_directory.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("SPEAKTYPE_CONFIG_DIR", str(run_directory / "config"))
bundle = Path(os.environ["SPEAKTYPE_TEST_BUNDLE"]).resolve() if os.environ.get("SPEAKTYPE_TEST_BUNDLE") else None
if not bundle:
    sys.path.insert(0, str(root))

import AppKit
import objc
from Foundation import NSDate, NSObject, NSMakeSize, NSRunLoop, NSTimer

from speaktype import __version__
from speaktype.app import SpeakTypeApp
from speaktype.audio import START_TIMEOUT_SECONDS
from speaktype.config import CONFIG_DIR, DEFAULT_CONFIG, save_config
from speaktype.history import DictationHistory
from speaktype.permissions import microphone_is_authorized


assert CONFIG_DIR.resolve().is_relative_to(root / "work"), "Use an isolated configuration under work"
report_path = args.report.resolve() if args.report else run_directory / ("bundle-report.json" if bundle else "source-report.json")
assert report_path.is_relative_to(root / "work"), "Save the validation report under work"
report_path.parent.mkdir(parents=True, exist_ok=True)
module_names = ("speaktype.app", "speaktype.audio", "speaktype.asr", "speaktype.main_window", "sounddevice", "numpy")
if bundle:
    assert Path(sys.prefix).resolve().is_relative_to(bundle), "Run with the bundled verification launcher"
    for name in module_names:
        if name in sys.modules:
            assert Path(sys.modules[name].__file__).resolve().is_relative_to(bundle), name
logging.basicConfig(level=logging.INFO)
save_config({**DEFAULT_CONFIG, "setup_completed": True, "polish_enabled": False,
             "translate_enabled": False, "sound_feedback": False, "streaming_preview": False,
             "plugins_enabled": False, "hotword_learning_enabled": False})
DictationHistory().clear()
report = {"version": __version__, "runtime": str(bundle) if bundle else "source", "status": "running",
          "scope": "Real main-window buttons, actual ASR readiness, real microphone helper processes and native run loop",
          "config": str(CONFIG_DIR), "run_directory": str(run_directory), "cycles": [], "checks": [],
          "speech_recognition_asserted": False, "microphone_samples_observed": False}
application = None
controller = None
sessions = []
pulse = None
timer = None


class _MainThreadPulse(NSObject):
    def init(self):
        self = objc.super(_MainThreadPulse, self).init()
        if self is not None:
            self.timestamps = []
        return self

    def tick_(self, timer):
        assert threading.current_thread() is threading.main_thread()
        self.timestamps.append(time.monotonic())


def advance(seconds=0.02):
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(seconds))
    for _ in range(128):
        event = AppKit.NSApp.nextEventMatchingMask_untilDate_inMode_dequeue_(
            AppKit.NSEventMaskAny, NSDate.distantPast(), AppKit.NSDefaultRunLoopMode, True)
        if event is None:
            break
        AppKit.NSApp.sendEvent_(event)
    AppKit.NSApp.updateWindows()


def wait_until(predicate, timeout, description):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, description
        advance()


def native_action(button, description):
    assert button.isEnabled(), description + " is disabled"
    started = time.monotonic()
    assert button.sendAction_to_(button.action(), button.target()), description + " was not dispatched"
    elapsed = time.monotonic() - started
    assert elapsed < 0.75, f"{description} blocked the main thread for {elapsed:.3f} seconds"
    return elapsed


def startup_workers():
    return [worker for worker in application._active_model_workers() if worker.name == "SpeakTypeDeviceStart"]


def wait_for_preparation():
    deadline = time.monotonic() + 180
    while not application.asr._loaded or any(worker is not None and worker.is_alive() for worker in (
        application._engine_thread, application.asr._load_thread, application.asr._warmup_thread,
    )):
        assert not application._engine_error, application._engine_error
        assert time.monotonic() < deadline, "The actual speech model did not finish loading"
        advance()
    application._refresh_main_readiness()
    wait_until(lambda: application._readiness_thread is None or not application._readiness_thread.is_alive(),
               20, "Actual readiness inspection did not finish")
    application._refresh_main_window_main()
    assert microphone_is_authorized(), "Microphone access is not authorized for this real runtime"
    assert controller._snapshot["ready"] and controller._record_button.isEnabled()
    report["preparation"] = {"asr_loaded": application.asr._loaded, "model": application.config["asr_model"],
                             "microphone_authorized": True, "readiness": controller._readiness_details}
    application._permission_watch_stop.set()
    if application.hotkey_listener is not None:
        application.hotkey_listener.stop()


def open_device(label):
    previous_operation = application._operation_id
    before_workers = set(startup_workers())
    requested = time.monotonic()
    returned = native_action(controller._record_button, label + " start")
    wait_until(lambda: application.recorder._capture_session is not None or controller._snapshot["phase"] == "error",
               3, label + " did not create a microphone session")
    session = application.recorder._capture_session
    assert session is not None, str(controller._snapshot.get("status"))
    wait_until(lambda: session.process is not None or session.error is not None, 3, label + " did not spawn a real helper")
    assert session.process is not None, str(session.error)
    assert session.process.poll() is None, label + " helper exited before cancellation could be tested"
    wait_until(lambda: session.device_info is not None or session.error is not None, 3,
               label + " helper did not resolve the actual microphone")
    assert session.device_info is not None, str(session.error)
    assert session.device_info["max_input_channels"] > 0, session.device_info
    assert application._operation_id > previous_operation
    assert session.cancellation is application._operation_cancel
    assert controller._snapshot["phase"] in {"loading", "recording"}
    if bundle:
        assert Path(session.process.args[0]).resolve().is_relative_to(bundle), session.process.args
    item = {"label": label, "operation_id": application._operation_id, "child_pid": session.process.pid,
            "worker_command": session.process.args, "start_button_seconds": returned,
            "device": session.device_info,
            "start_timeout_seconds": application.recorder.start_timeout_seconds,
            "log": str(application.recorder._capture_log_path), "requested_monotonic": requested,
            "device_opening_observed_monotonic": time.monotonic(),
            "start_workers": list(set(startup_workers()) - before_workers)}
    sessions.append((session, item))
    return session, item


def probe_responsiveness(label):
    before = len(pulse.timestamps)
    size = controller.window.contentView().frame().size
    original_width, original_height = size.width, size.height
    editor_width = controller._final_scroll.frame().size.width
    started = time.monotonic()
    controller.window.setContentSize_(NSMakeSize(original_width + 12, original_height + 8))
    advance(0.08)
    actual = controller.window.contentView().frame().size
    assert actual.width == original_width + 12
    assert controller._final_scroll.frame().size.width == editor_width + 12
    controller.window.setContentSize_(NSMakeSize(original_width, original_height))
    advance(0.08)
    assert len(pulse.timestamps) >= before + 3, label + " prevented native main-thread timer callbacks"
    return {"label": label, "timer_callbacks": len(pulse.timestamps) - before,
            "resize_seconds": time.monotonic() - started, "content_width": actual.width,
            "editor_width": editor_width + 12}


def frame_receipt(session):
    with application.recorder._lock:
        count = sum(len(frame) for frame in application.recorder._frames) if session is application.recorder._capture_session else 0
    observed = session.started and count > 0
    report["microphone_samples_observed"] |= observed
    return {"device_ready": session.started, "samples_before_cancel": count, "real_capture_observed": observed}


def cancel_device(session, item):
    item.update(frame_receipt(session))
    item["outcome"] = "recording_cancelled" if item["real_capture_observed"] else "opening_cancelled"
    item["cancel_button_seconds"] = native_action(controller._cancel_button, item["label"] + " cancel")
    assert session.cancellation.is_set()
    assert application.recorder._capture_session is None and not application.recorder.is_recording
    assert application._starting_operation_id is None
    assert controller._snapshot["phase"] == "cancelled" and not controller._snapshot["busy"]
    assert controller._record_button.isEnabled()


def session_finished(session, item):
    return (session.process.poll() is not None and (session.reader is None or not session.reader.is_alive())
            and all(not worker.is_alive() for worker in item["start_workers"]))


def public_item(item):
    return {key: value for key, value in item.items() if key != "start_workers"}


def execute():
    global application, controller, pulse, timer
    AppKit.NSApplication.sharedApplication()
    AppKit.NSApp.finishLaunching()
    application = SpeakTypeApp()
    application._show_main_window()
    controller = application._main_controller
    if bundle:
        for name in module_names:
            assert Path(sys.modules[name].__file__).resolve().is_relative_to(bundle), name
    report["modules"] = {name: str(Path(sys.modules[name].__file__).resolve()) for name in module_names}
    wait_for_preparation()
    assert application.recorder.start_timeout_seconds == START_TIMEOUT_SECONDS == 8
    pulse = _MainThreadPulse.alloc().init()
    timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(0.02, pulse, b"tick:", None, True)
    advance(0.08)
    first, first_item = open_device("first")
    first_item["responsiveness"] = probe_responsiveness("first device opening")
    cancel_device(first, first_item)
    first_item["old_work_alive_before_restart"] = not session_finished(first, first_item)
    second, second_item = open_device("second")
    assert second is not first and second.process.pid != first.process.pid
    assert second_item["operation_id"] > first_item["operation_id"]
    second_item["responsiveness"] = probe_responsiveness("second device opening")
    current_operation = application._operation_id
    started = time.monotonic()
    application.recorder.cancel_start(cancel_event=first.cancellation)
    assert application.recorder.stop_audio(cancel_event=first.cancellation) is None
    assert time.monotonic() - started < 0.25
    assert application.recorder._capture_session is second and not second.cancellation.is_set()
    assert second.process.poll() is None and application._operation_current(current_operation)
    wait_until(lambda: session_finished(first, first_item), 7, "The first helper or start worker did not finish")
    assert application.recorder._capture_session is second
    assert application._operation_id == current_operation and application._operation_current(current_operation)
    assert controller._snapshot["phase"] in {"loading", "recording"}
    assert not controller._snapshot.get("status", "").startswith("Microphone device did not start")
    first_item["child_return_code"] = first.process.poll()
    second_item["stale_session_calls_ignored"] = True
    second_item["old_worker_finished_without_changing_current_operation"] = True
    cancel_device(second, second_item)
    wait_until(lambda: session_finished(second, second_item), 7, "The second helper or start worker did not finish")
    second_item["child_return_code"] = second.process.poll()
    report["cycles"] = [public_item(first_item), public_item(second_item)]
    report["checks"].append("Actual main-window Start, Cancel, immediate Start and Cancel dispatch quickly; native timer callbacks and actual window/editor resizing continue while real microphone helpers are opening")
    report["checks"].append("Both cancelled device children and start workers finish; the old cancellation token cannot cancel or stop the new real session, and the old worker leaves the new operation current")

    probe, probe_item = open_device("uncancelled probe")
    probe_item["responsiveness"] = probe_responsiveness("normal microphone start")
    wait_until(lambda: probe.started or controller._snapshot["phase"] == "error",
               START_TIMEOUT_SECONDS + 2 * application.recorder.stop_timeout_seconds + 3,
               "The normal microphone start neither received real audio nor reported an error")
    if probe.started:
        wait_until(lambda: len(application.recorder._frames) > 0 and controller._snapshot["phase"] == "recording",
                   3, "The helper reported ready without actual recording samples and recording state")
        probe_item.update(frame_receipt(probe))
        assert probe_item["real_capture_observed"]
        cancel_device(probe, probe_item)
        report["normal_start"] = {**public_item(probe_item), "normal_start_timeout_observed": False}
        report["checks"].append("The real device recovered: actual microphone samples reached the recorder and the main window entered recording before cancellation")
    else:
        elapsed = time.monotonic() - probe_item["requested_monotonic"]
        message = str(controller._snapshot.get("status") or "")
        error = application.recorder.last_start_error
        assert isinstance(error, TimeoutError), repr(error)
        assert "did not start within 8 seconds" in str(error), str(error)
        expected_duration = "8 秒" if controller._language == "zh" else "8 seconds"
        assert expected_duration in message, message
        assert elapsed >= START_TIMEOUT_SECONDS - 0.25, elapsed
        assert application.recorder.last_stop_reason == "device_start_failed"
        assert not application.recorder.is_recording and application.recorder._capture_session is None
        assert not controller._snapshot["busy"] and controller._record_button.isEnabled()
        assert controller._status_label.stringValue() == message and not controller._status_label.isHidden()
        report["normal_start"] = {**public_item(probe_item), "outcome": "normal_start_timeout",
                                  "normal_start_timeout_observed": True, "elapsed_seconds": elapsed,
                                  "error": message, "raw_error": str(error), "error_type": type(error).__name__,
                                  "phase": controller._snapshot["phase"],
                                  "response_after_error": probe_responsiveness("after microphone timeout")}
        report["checks"].append("The blocked real device reaches its normal eight-second start timeout, displays the specific device error and leaves the window usable; this is an error-handling check, not recording success")
    wait_until(lambda: session_finished(probe, probe_item), 7, "The normal-start helper or worker did not finish")
    report["normal_start"]["child_return_code"] = probe.process.poll()
    marker = "取消和设备错误之后，窗口仍可编辑：🙂 café。"
    controller.window.makeFirstResponder_(controller._final_view)
    controller._final_view.insertText_replacementRange_(marker, controller._final_view.selectedRange())
    advance(0.6)
    assert marker in controller.get_final_text() and marker in application._main_state["final"]
    assert any(marker in entry.get("polished", "") for entry in DictationHistory(path=application.history.path).snapshot())
    report["checks"].append("After cancellation or the actual device error, native Unicode editing still persists through the real history callback")
    gaps = [right - left for left, right in zip(pulse.timestamps, pulse.timestamps[1:])]
    report["main_thread"] = {"native_timer_callbacks": len(pulse.timestamps), "maximum_callback_gap_seconds": max(gaps, default=0)}
    assert max(gaps, default=0) < 0.75, report["main_thread"]
    report["status"] = "passed"


try:
    execute()
except Exception as error:
    report["status"] = "failed"
    report["failure"] = {"type": type(error).__name__, "message": str(error),
                         "phase": controller._snapshot.get("phase") if controller is not None else None,
                         "status_text": controller._snapshot.get("status") if controller is not None else None,
                         "operation_id": application._operation_id if application is not None else None,
                         "operation_cancelled": application._operation_cancel.is_set() if application is not None else None,
                         "device_error": str(application.recorder.last_start_error) if application is not None else None,
                         "device_stop_reason": application.recorder.last_stop_reason if application is not None else None}
    report["cycles"] = [public_item(item) for _, item in sessions]
    raise
finally:
    if pulse is not None:
        gaps = [right - left for left, right in zip(pulse.timestamps, pulse.timestamps[1:])]
        report["main_thread"] = {"native_timer_callbacks": len(pulse.timestamps), "maximum_callback_gap_seconds": max(gaps, default=0)}
    if timer is not None:
        timer.invalidate()
    if application is not None:
        report["shutdown_prepared"] = application._prepare_to_quit(timeout=15)
        if controller is not None:
            controller.close()
        application._status_overlay.hide()
        advance(0.05)
    report["children"] = [{"pid": session.process.pid, "return_code": session.process.poll(),
                           "reader_alive": bool(session.reader is not None and session.reader.is_alive())}
                          for session, _ in sessions if session.process is not None]
    cleanup_failed = report["status"] == "passed" and (
        not report.get("shutdown_prepared")
        or any(child["return_code"] is None or child["reader_alive"] for child in report["children"]))
    if cleanup_failed:
        report["status"] = "failed"
        report["failure"] = {"type": "LifecycleCleanupError", "message": "A real helper, reader or model worker did not finish"}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"REPORT {report_path}", flush=True)
    assert not cleanup_failed, report["failure"]
