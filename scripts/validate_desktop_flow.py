import argparse
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import threading
import time

root = Path(__file__).resolve().parents[1]
bundle = Path(os.environ["SPEAKTYPE_TEST_BUNDLE"]).resolve() if os.environ.get("SPEAKTYPE_TEST_BUNDLE") else None
if bundle:
    assert Path(sys.prefix).resolve().is_relative_to(bundle)
else:
    sys.path.insert(0, str(root))

import AppKit
from Foundation import NSDate, NSRunLoop
import soundfile as sf

from speaktype import __version__
from speaktype.app import SpeakTypeApp
from speaktype.config import CONFIG_DIR, DEFAULT_CONFIG, save_config
from speaktype.context import get_active_app, get_selected_text
from speaktype.delivery_target import capture_target_field, prepare_unchanged_target
from speaktype.inserter import _get_focused_element, _copy_ax_attribute, _prepare_target_app, _restore_pasteboard, _snapshot_pasteboard


parser = argparse.ArgumentParser()
parser.add_argument("--ollama-model", default="qwen3-vl:2b-instruct")
parser.add_argument("--ui-language", choices=("zh", "en"), default="zh")
parser.add_argument("--interactive", action="store_true")
parser.add_argument("--report", type=Path, required=True)
args = parser.parse_args()
assert CONFIG_DIR.is_relative_to(root / "work")
save_config({**DEFAULT_CONFIG, "setup_completed": True, "polish_enabled": False,
             "translate_enabled": False, "streaming_preview": False,
             "hotkey": "f6", "dictation_mode": "toggle", "language": "en",
             "llm_model": args.ollama_model, "ui_language": args.ui_language, "sound_feedback": False,
             "hotword_learning_enabled": False, "hotword_context_enabled": False})
application = SpeakTypeApp()
AppKit.NSApplication.sharedApplication()
AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
AppKit.NSApp.finishLaunching()
application.asr.load()
if application.asr._warmup_thread:
    application.asr._warmup_thread.join(timeout=120)
    assert not application.asr._warmup_thread.is_alive()
assert application.polish_engine.check_available(), application.polish_engine.last_error
application._restart_hotkey_listener()
assert application.hotkey_listener.is_running
application._show_main_window(None)
samples, rate = sf.read(root / "work/audio-validation/english.wav", dtype="float32")
assert rate == 16000
pb = AppKit.NSPasteboard.generalPasteboard()
clipboard = _snapshot_pasteboard(pb)
report = {"version": __version__, "runtime": str(bundle) if bundle else "source",
          "asr_model": application.asr.model_name, "ollama_model": args.ollama_model, "cases": []}
captured_target = None


def advance(seconds=0.06):
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(seconds))
    while True:
        event = AppKit.NSApp.nextEventMatchingMask_untilDate_inMode_dequeue_(
            AppKit.NSEventMaskAny, NSDate.distantPast(), AppKit.NSDefaultRunLoopMode, True)
        if event is None:
            break
        AppKit.NSApp.sendEvent_(event)
    AppKit.NSApp.updateWindows()


def wait_until(predicate, timeout=150):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        advance()
    assert predicate(), f"Timed out: {application._main_state}"
    advance()


def wait_for(worker):
    wait_until(lambda: not worker.is_alive())
    assert not application._is_processing
    assert not application._main_state["busy"]


def preview(operation_id=None):
    worker = threading.Thread(target=application._process_audio,
                              args=(samples.copy(), len(samples) / rate),
                              kwargs={"insert_result": False, "app_info": {}, "operation_id": operation_id})
    application._processing_thread = worker
    worker.start()
    return worker


def latest():
    return application.history.get_recent(1)[0]


def activate_textedit():
    result = {}
    worker = threading.Thread(target=lambda: result.update(pid=_prepare_target_app(bundle_id="com.apple.TextEdit")))
    worker.start()
    wait_for(worker)
    assert result["pid"] is not None, "TextEdit activation failed"
    target = get_active_app()
    assert target["bundle_id"] == "com.apple.TextEdit", target
    return target


def commands():
    while True:
        readable, _, _ = select.select([sys.stdin], [], [], 0)
        if readable:
            line = sys.stdin.readline()
            if not line:
                return
            yield line
        else:
            advance()


def checked(name, **details):
    report["cases"].append({"case": name, **details})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"VERIFIED {name}", flush=True)


try:
    wait_until(lambda: application._main_state.get("ready"))
    assert len(application._main_state["readiness"]) == 5
    checked("actual_readiness", rows=application._main_state["readiness"])
    before_clipboard = pb.changeCount()
    wait_for(preview())
    entry = latest()
    assert entry["outcome"] == "saved" and "meeting notes" in entry["raw"].lower(), entry
    assert pb.changeCount() == before_clipboard
    checked("preview_saved_without_external_input", entry=entry)

    # 使用真实推理锁重现等待中的识别任务，在取消后允许实际识别完成。
    previous_entries = application.history.snapshot()
    previous_latest = dict(application._latest_dictation)
    application.asr.acquire_inference()
    try:
        worker = preview()
        wait_until(lambda: application._main_state["phase"] == "transcribing")
        application._main_controller._cancel_button.performClick_(None)
        assert application._main_state["phase"] == "cancelled"
    finally:
        application.asr.release_inference()
    wait_for(worker)
    assert application._main_state["phase"] == "cancelled"
    assert application.history.snapshot() == previous_entries
    assert application._latest_dictation == previous_latest
    checked("cancel_during_real_asr_wait_preserves_result")

    wait_for(preview())
    assert latest()["outcome"] == "saved"
    checked("recording_job_after_cancel", entry=latest())

    wait_until(lambda: application._main_controller._llm_ready)
    assert application._main_controller._polish_button.isEnabled()
    assert application._main_controller._translate_button.isEnabled()

    view = application._main_controller._final_view
    view.setSelectedRange_((0, len(str(view.string()))))
    view.insertText_("Please send the meeting notes tomorrow morning. Added by editing.")
    application._main_controller._copy_button.performClick_(None)
    entry = latest()
    original_raw, entry_id = entry["raw"], entry["id"]
    assert "Added by editing." in entry["polished"] and entry["outcome"] == "saved"
    assert pb.stringForType_(AppKit.NSPasteboardTypeString) == entry["polished"]
    checked("native_edit_copy_and_save", entry=entry)

    application._main_controller._polish_button.performClick_(None)
    wait_for(application._processing_thread)
    entry = latest()
    assert entry["id"] == entry_id and entry["raw"] == original_raw and entry["outcome"] == "saved"
    assert "meeting" in entry["polished"].lower() and application._main_state["phase"] == "done"
    checked("native_polish_same_record", entry=entry)
    application._main_set_translate_language("zh")
    application._main_controller._translate_button.performClick_(None)
    wait_for(application._processing_thread)
    entry = latest()
    assert entry["id"] == entry_id and entry["raw"] == original_raw and entry["outcome"] == "saved"
    assert application._main_state["phase"] == "done", application._main_state
    assert any("\u4e00" <= char <= "\u9fff" for char in entry["polished"])
    checked("native_translate_same_record", entry=entry)

    application._main_controller._record_button.performClick_(None)
    assert application.recorder.is_recording and application.hotkey_listener.is_active
    advance(0.4)
    application._main_controller._cancel_button.performClick_(None)
    assert not application.recorder.is_recording and not application.hotkey_listener.is_active
    assert application._main_state["phase"] == "cancelled" and not application._main_state["busy"]
    checked("native_record_cancel_resets_toggle")

    application._show_setup_center("help")
    assert application._help_controller.window.isVisible()
    application._help_controller.close()
    application._show_setup_center()
    assert application._setup_center.window.isVisible()
    application._setup_center.close()
    checked("help_and_preparation_open_from_main")

    if args.interactive:
        print("READY_INTERACTIVE: capture, toggle, target, changed, insert, finish", flush=True)
        for line in commands():
            command = line.strip()
            if command in {"capture", "toggle"}:
                application._show_main_window(None)
                application._main_controller._record_button.performClick_(None)
                assert application.recorder.is_recording and application.hotkey_listener.is_active
                advance(0.3)
                subprocess.run(["afplay", str(root / "work/audio-validation/english.wav")], check=True)
                advance(0.5)
                if command == "toggle":
                    print("READY_PRESS_F6_TO_STOP", flush=True)
                    wait_until(lambda: not application.recorder.is_recording, timeout=120)
                else:
                    application._main_controller._record_button.performClick_(None)
                wait_until(lambda: not application._is_processing and application._main_state["phase"] in {"done", "error"})
                wait_for(application._processing_thread)
                assert not application.hotkey_listener.is_active
                entry = latest()
                assert entry["outcome"] == "saved" and "meeting" in entry["raw"].lower(), entry
                checked(f"microphone_{command}", entry=entry, samples=application.recorder.last_audio_original_samples)
            elif command == "target":
                target = activate_textedit()
                captured_target = capture_target_field(target)
                assert captured_target.element is not None and captured_target.value is not None
                assert prepare_unchanged_target(captured_target)
                checked("target_capture", target=target, value=captured_target.value,
                        selection=captured_target.selection, selected=get_selected_text())
                print("READY_CHANGE_TEXTEDIT_CARET_OR_DOCUMENT", flush=True)
            elif command == "changed":
                assert captured_target is not None, "Capture the actual target first"
                assert not prepare_unchanged_target(captured_target), "Change the actual TextEdit selection before continuing"
                before = _copy_ax_attribute(_get_focused_element(), "AXValue")
                application._process_audio(samples.copy(), len(samples) / rate,
                                           app_info=captured_target.app, target_field=captured_target)
                after = _copy_ax_attribute(_get_focused_element(), "AXValue")
                assert before == after and latest()["outcome"] == "failed"
                checked("changed_target_keeps_text_and_result", entry=latest(), field=after)
            elif command == "insert":
                assert captured_target is not None
                application._main_select_target(captured_target.app)
                application._main_insert(application._main_state["final"])
                wait_for(application._processing_thread)
                assert latest()["outcome"] == "inserted", latest()
                checked("explicit_reinsert_to_selected_pid", entry=latest())
            elif command == "finish":
                break
            else:
                raise ValueError(command)
            print("READY_INTERACTIVE", flush=True)
finally:
    if application.recorder.is_recording:
        application._main_cancel()
    application._status_overlay.hide()
    application._cancel_edit_observation()
    application.hotkey_listener.stop()
    application._permission_watch_stop.set()
    readiness_timer = getattr(application, "_readiness_timer", None)
    if readiness_timer:
        readiness_timer.stop()
    if application._setup_center:
        application._setup_center.shutdown()
    for name in ("_main_controller", "_help_controller", "_setup_center"):
        controller = getattr(application, name, None)
        if controller:
            controller.close()
    advance()
    _restore_pasteboard(pb, clipboard)
print(f"REPORT {args.report}", flush=True)
