import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import threading
import time
from uuid import uuid4


parser = argparse.ArgumentParser()
parser.add_argument("--device", type=int, default=0)
parser.add_argument("--max-seconds", type=float, default=1.5)
parser.add_argument("--report", type=Path)
args = parser.parse_args()
assert 0.5 <= args.max_seconds <= 10, "Use a finite recording limit between 0.5 and 10 seconds"
root = Path(__file__).resolve().parents[1]
run_directory = root / "work" / "microphone-hardware" / uuid4().hex
temporary = run_directory / "temporary"
temporary.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("SPEAKTYPE_CONFIG_DIR", str(run_directory / "config"))
os.environ["TMPDIR"] = str(temporary)
bundle = Path(os.environ["SPEAKTYPE_TEST_BUNDLE"]).resolve() if os.environ.get("SPEAKTYPE_TEST_BUNDLE") else None
if not bundle:
    sys.path.insert(0, str(root))

import AppKit
from Foundation import NSDate, NSRunLoop
import numpy as np
import soundfile as sf

from speaktype import __version__
from speaktype.audio import AudioRecorder, sd
from speaktype.config import CONFIG_DIR
from speaktype.permissions import microphone_is_authorized


assert CONFIG_DIR.resolve().is_relative_to(root / "work"), "Use an isolated configuration under work"
report_path = args.report.resolve() if args.report else run_directory / ("bundle-report.json" if bundle else "source-report.json")
assert report_path.is_relative_to(root / "work"), "Save the hardware report under work"
report_path.parent.mkdir(parents=True, exist_ok=True)
if bundle:
    assert Path(sys.prefix).resolve().is_relative_to(bundle), "Run with the bundled verification launcher"
    for name in ("speaktype.audio", "sounddevice", "numpy", "soundfile"):
        assert Path(sys.modules[name].__file__).resolve().is_relative_to(bundle), name
logging.basicConfig(level=logging.INFO)
AppKit.NSApplication.sharedApplication()
AppKit.NSApp.finishLaunching()
report = {
    "version": __version__, "runtime": str(bundle) if bundle else "source", "status": "running",
    "method": "Actual built-in microphone PCM through the unmodified AudioRecorder and its real helper process",
    "run_directory": str(run_directory), "speech_recognition_asserted": False,
    "positive_hardware_verified": False, "checks": {
        "startup_and_pcm": "not_run", "max_duration": "not_run", "active_helper_exit": "not_run"},
    "modules": {name: str(Path(sys.modules[name].__file__).resolve())
                for name in ("speaktype.audio", "sounddevice", "numpy", "soundfile")},
}
sessions = []
recorders = []
operations = []


def advance(seconds=0.01):
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(seconds))
    while True:
        event = AppKit.NSApp.nextEventMatchingMask_untilDate_inMode_dequeue_(
            AppKit.NSEventMaskAny, NSDate.distantPast(), AppKit.NSDefaultRunLoopMode, True)
        if event is None:
            break
        AppKit.NSApp.sendEvent_(event)
    AppKit.NSApp.updateWindows()


def wait_until(predicate, seconds, message):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        advance()
    assert predicate(), message


def run_operation(function, seconds):
    result = []
    errors = []

    def execute():
        try:
            result.append(function())
        except Exception as error:
            errors.append(error)

    worker = threading.Thread(target=execute, name="SpeakTypeHardwareValidation", daemon=True)
    operations.append(worker)
    worker.start()
    deadline = time.monotonic() + seconds
    while worker.is_alive() and time.monotonic() < deadline:
        for recorder in recorders:
            with recorder._lock:
                session = recorder._capture_session
            if session is not None and all(session is not known for known in sessions):
                sessions.append(session)
        advance()
    assert not worker.is_alive(), "The real recorder operation exceeded its bounded deadline"
    if errors:
        raise errors[0]
    assert len(result) == 1
    return result[0]


def open_microphone(label, *, max_seconds=None, on_max_duration=None, on_error=None):
    recorder = AudioRecorder(device=args.device)
    recorders.append(recorder)
    chunks = []
    received_at = []
    chunk_lock = threading.Lock()
    cancellation = threading.Event()

    def receive(chunk):
        with chunk_lock:
            chunks.append(chunk.copy())
            received_at.append(time.monotonic())

    recorder.set_stream_callback(receive)
    requested = time.monotonic()

    def begin():
        success = recorder.start(max_seconds=max_seconds, on_max_duration=on_max_duration,
                                 cancel_event=cancellation, on_error=on_error)
        returned = time.monotonic()
        with chunk_lock:
            at_return = sum(len(chunk) for chunk in chunks)
        return success, returned, at_return

    success, returned, at_return = run_operation(begin, recorder.start_timeout_seconds + 5)
    with recorder._lock:
        session = recorder._capture_session
    item = {"label": label, "start_returned": success, "start_seconds": returned - requested,
            "samples_at_start_return": at_return, "log": str(recorder._capture_log_path)}
    report[label] = item
    if not success:
        item["error"] = {"type": type(recorder.last_start_error).__name__, "message": str(recorder.last_start_error)}
        assert recorder.last_start_error is not None
        assert not recorder.is_recording and session is None and not cancellation.is_set()
        return None
    assert session is not None and session.started and session.start_accepted and recorder.is_recording
    if all(session is not known for known in sessions):
        sessions.append(session)
    assert session.device_info["name"] == report["input_device"]["name"]
    wait_until(lambda: len(chunks) >= 3, 1.5, "Successful microphone start did not deliver continuous real PCM")
    with chunk_lock:
        assert all(chunk.dtype == np.float32 and chunk.ndim == 2 and chunk.shape[1] == 1
                   and len(chunk) > 0 and np.all(np.isfinite(chunk)) for chunk in chunks)
        item["first_callback_relative_to_start_return_seconds"] = received_at[0] - returned
    assert recorder.sample_rate == 16000
    item.update({"device_ready_from_actual_pcm": session.started, "sample_rate": recorder.sample_rate,
                 "dtype": "float32", "channels": 1, "child_pid": session.process.pid,
                 "worker_command": session.process.args})
    return recorder, session, chunks, chunk_lock, cancellation, item


def save_pcm(label, recorder, chunks, chunk_lock):
    output = run_operation(lambda: recorder.stop_audio(), recorder.stop_timeout_seconds + 5)
    with chunk_lock:
        pcm = np.concatenate(chunks, axis=0).flatten()
    assert len(pcm) >= recorder.sample_rate * 0.3
    assert recorder.last_audio_original_samples == len(pcm), "Streaming callbacks and final recording lost different sample counts"
    if output is not None:
        assert output.dtype == np.float32 and np.array_equal(output, pcm)
    else:
        assert recorder.last_stop_reason == "too_quiet", recorder.last_stop_message
    path = run_directory / f"{label}.wav"
    sf.write(path, pcm, recorder.sample_rate, subtype="FLOAT")
    return {"stream_samples": len(pcm), "seconds": len(pcm) / recorder.sample_rate,
            "peak": float(np.max(np.abs(pcm))), "rms": float(np.sqrt(np.mean(np.square(pcm)))),
            "finalized_samples": len(output) if output is not None else 0,
            "stop_reason": recorder.last_stop_reason,
            "audio_path": str(path), "audio_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def execute():
    assert microphone_is_authorized(), "The actual microphone permission must already be authorized"
    info = dict(sd.query_devices(args.device, kind="input"))
    assert info["max_input_channels"] > 0
    assert "MacBook" in info["name"] or "Built-in" in info["name"], "Select the physical built-in microphone"
    report.update({"input_index": args.device, "input_device": info,
                   "default_devices": list(sd.default.device), "microphone_authorized": True})
    opened = open_microphone("startup")
    if opened is None:
        report["status"] = "blocked"
        report["blocking_reason"] = "The physical microphone supplied no successful start; all positive hardware checks remain unverified"
        return
    recorder, session, chunks, chunk_lock, cancellation, item = opened
    wait_until(lambda: len(chunks) >= 6, 2, "Actual microphone callbacks stopped unexpectedly")
    item.update(save_pcm("startup", recorder, chunks, chunk_lock))
    wait_until(lambda: session.process.poll() is not None and not session.reader.is_alive(), 4,
               "The normally stopped physical microphone helper did not finish")
    assert session.clean_stop and session.error is None and session.process.returncode == 0
    assert recorder._capture_session is None and not recorder.is_recording and not cancellation.is_set()
    report["checks"]["startup_and_pcm"] = "passed"

    limit_calls = []
    opened = open_microphone("automatic_limit", max_seconds=args.max_seconds,
                             on_max_duration=lambda: limit_calls.append(time.monotonic()))
    assert opened is not None, "The real microphone failed to restart for its duration limit"
    recorder, session, chunks, chunk_lock, cancellation, item = opened
    wait_until(lambda: session.stopped.is_set(), args.max_seconds + 4,
               "The actual duration limit did not stop the device helper automatically")
    wait_until(lambda: session.process.poll() is not None, 4, "The duration-limited helper did not exit")
    assert len(limit_calls) == 1 and session.clean_stop and session.error is None
    assert session.stop_requested and session.process.returncode == 0
    item.update({"configured_max_seconds": args.max_seconds, "limit_callback_count": len(limit_calls),
                 "helper_stopped_before_parent_stop_request": True})
    item.update(save_pcm("automatic-limit", recorder, chunks, chunk_lock))
    duration_tolerance = 0.3
    minimum_duration = args.max_seconds - duration_tolerance
    maximum_duration = args.max_seconds + duration_tolerance
    duration_matches_limit = minimum_duration <= item["seconds"] <= maximum_duration
    item.update({"pcm_duration_deviation_seconds": item["seconds"] - args.max_seconds,
                 "pcm_duration_tolerance_seconds": duration_tolerance,
                 "expected_pcm_duration_seconds": {"minimum": minimum_duration, "maximum": maximum_duration},
                 "duration_tolerance_basis": "100 ms callback blocks, the final queued block, and built-in input latency",
                 "pcm_duration_within_expected_range": duration_matches_limit})
    assert duration_matches_limit, (
        f"Actual PCM duration {item['seconds']:.3f}s differs from the configured "
        f"{args.max_seconds:.3f}s limit by more than {duration_tolerance:.3f}s")
    assert recorder._capture_session is None and not recorder.is_recording and not cancellation.is_set()
    report["checks"]["max_duration"] = "passed"

    error_calls = []
    opened = open_microphone("active_helper_exit", on_error=lambda error: error_calls.append(error))
    assert opened is not None, "The real microphone failed to restart for the active-device error check"
    recorder, session, chunks, chunk_lock, cancellation, item = opened
    assert session.process.poll() is None and session.start_accepted and len(chunks) >= 3
    terminated_at = time.monotonic()
    session.process.terminate()
    wait_until(lambda: len(error_calls) == 1 and session.process.poll() is not None
               and not session.reader.is_alive(), 5, "The actual active helper exit did not notify and finish cleanup")
    assert recorder._capture_session is None and not recorder.is_recording
    assert not recorder._frames and recorder.last_error is error_calls[0]
    assert recorder.last_stop_reason == "device_error" and not cancellation.is_set()
    with chunk_lock:
        final_count = len(chunks)
    until = time.monotonic() + 0.2
    while time.monotonic() < until:
        advance()
    assert len(error_calls) == 1 and len(chunks) == final_count
    item.update({"actual_termination_signal": "SIGTERM", "child_return_code": session.process.returncode,
                 "cleanup_seconds": time.monotonic() - terminated_at, "on_error_count": len(error_calls),
                 "error_type": type(error_calls[0]).__name__, "error": str(error_calls[0]),
                 "parent_session_detached": True, "parent_recording": recorder.is_recording,
                 "reader_alive": session.reader.is_alive(), "external_cancel_unchanged": True})
    report["checks"]["active_helper_exit"] = "passed"
    report["positive_hardware_verified"] = True
    report["status"] = "passed"


try:
    execute()
except Exception as error:
    report["status"] = "failed"
    report["failure"] = {"type": type(error).__name__, "message": str(error)}
    raise
finally:
    for recorder in recorders:
        if recorder._capture_session is not None:
            recorder.cancel_start()
    deadline = time.monotonic() + 5
    while any(session.process is not None and session.process.poll() is None
              or session.reader is not None and session.reader.is_alive() for session in sessions) and time.monotonic() < deadline:
        advance()
    report["children"] = [{"pid": session.process.pid if session.process else None,
                           "return_code": session.process.poll() if session.process else None,
                           "reader_alive": session.reader.is_alive() if session.reader else False,
                           "device": session.device_info, "actual_pcm_ready": session.started}
                          for session in sessions]
    cleanup_complete = all(child["return_code"] is not None and not child["reader_alive"]
                           for child in report["children"]) and all(not worker.is_alive() for worker in operations)
    report["cleanup_complete"] = cleanup_complete
    if not cleanup_complete:
        report["status"] = "failed"
        report["failure"] = {"type": "HardwareCleanupError", "message": "A real helper, reader or recorder operation remains active"}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"STATUS {report['status']}", flush=True)
    print(f"REPORT {report_path}", flush=True)

raise SystemExit(0 if report["status"] == "passed" else 2)
