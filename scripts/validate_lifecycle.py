import json
import os
from pathlib import Path
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

root = Path(__file__).resolve().parents[1]
bundle = os.environ.get("SPEAKTYPE_TEST_BUNDLE")
if not bundle:
    sys.path.insert(0, str(root))

from speaktype.app import SpeakTypeApp
from speaktype.asr import ASREngine
from speaktype.config import CONFIG_DIR, DEFAULT_CONFIG, load_config, save_config
from speaktype.history import DictationHistory
from speaktype.i18n import get_language, t
from Foundation import NSDate, NSRunLoop


assert CONFIG_DIR.is_relative_to(root / "work")
if bundle:
    assert Path(sys.prefix).resolve().is_relative_to(Path(bundle).resolve())
    assert Path(sys.modules["speaktype.app"].__file__).resolve().is_relative_to(Path(bundle).resolve())
save_config({**DEFAULT_CONFIG, "setup_completed": True, "polish_enabled": False,
             "translate_enabled": False, "sound_feedback": False,
             "hotword_learning_enabled": False, "hotword_context_enabled": False})
report = {"runtime": bundle or "source", "checks": []}
application = SpeakTypeApp()
application.history.clear()
application._make_ui_lang_callback("en")(application._ui_lang_items["en"][0])
assert application.config["ui_language"] == "en" and load_config()["ui_language"] == "en"
assert get_language() == "en"
assert application._main_item.title == t("menu_main_window")
assert application._ui_lang_items["en"][0].state and not application._ui_lang_items["zh"][0].state
if application._readiness_thread is not None:
    application._readiness_thread.join(timeout=15)
    assert not application._readiness_thread.is_alive()
assert application._engine_thread is None and not application.asr._loaded
report["checks"].append("The real language menu callback applies config, persisted language, menu titles and checkmarks through the complete settings path")

old_engine = application.asr
current_engine = ASREngine(model_name=application.config["asr_model"])
with application._operation_lock:
    application.asr = current_engine
before = dict(application._main_state)
assert not application._update_asr_engine_state(old_engine, phase="error", ready=False, status="旧模型回调")
assert application._main_state == before
assert application._update_asr_engine_state(current_engine, phase="idle", ready=False, status="当前模型尚未加载")
assert application._main_state["status"] == "当前模型尚未加载"
assert not old_engine._loaded and not current_engine._loaded
report["checks"].append("Two actual unloaded ASREngine objects verify identity rejection; no load result is substituted or claimed")

operation_id = application._new_operation()
entry = application._retain_dictation("退出时保留的原始文本。", "退出时保留的原始文本。", {}, operation_id=operation_id)
application._update_operation_state(operation_id, phase="polishing", busy=True)
assert application._prepare_to_quit(timeout=0.2)
persisted = next(item for item in DictationHistory(path=application.history.path).snapshot() if item["id"] == entry["id"])
assert persisted["outcome"] == "cancelled" and persisted["polished"] == entry["raw"]
assert application._quitting and not application._is_processing and not application._main_state["busy"]
application._main_transform("退出期间的输入。", False)
application._main_insert("退出期间的输入。")
application._main_record()
assert application._operation_id == operation_id
readiness_worker = application._readiness_thread
application._refresh_main_readiness()
application._refresh_main_window_main()
application._do_setup()
assert application._readiness_thread is readiness_worker and application._engine_thread is None
application.config["hotword_learning_enabled"] = True
observer_worker = application._edit_observer._thread
application._start_edit_observation(raw_text="退出期间的原文。", inserted_text="退出期间的文本。", app_info={})
assert application._edit_observer._thread is observer_worker
report["checks"].append("Quit preparation atomically marks a pending record cancelled, retains raw text and rejects new recording, insertion and transformation")
report["checks"].append("Quit preparation blocks readiness, ASR setup and post-insertion edit-observer worker creation")


def pending_save_application():
    app = SpeakTypeApp()
    operation = app._new_operation()
    record = app._retain_dictation("交付状态测试原文。", "交付状态测试原文。", {}, operation_id=operation)
    assert app._begin_delivery(operation)
    release = threading.Event()

    def save():
        assert release.wait(5)
        assert app._commit_dictation_text(record, "真实写入文件的最终文本。", operation, outcome="saved")
        app._finish_operation(operation)

    worker = threading.Thread(target=save, name="SpeakType-Lifecycle-FileWriter")
    app._processing_thread = worker
    worker.start()
    return app, record, worker, release


delivery, record, worker, release = pending_save_application()
timer = threading.Timer(0.1, release.set)
timer.start()
assert delivery._prepare_to_quit(timeout=2)
worker.join(timeout=1)
timer.join(timeout=1)
assert not worker.is_alive()
persisted = next(item for item in delivery.history.snapshot() if item["id"] == record["id"])
assert persisted["outcome"] == "saved" and persisted["polished"] == "真实写入文件的最终文本。"
report["checks"].append("Quit waits for a real in-flight file commit to finish before invalidating its operation; the completed saved result remains persisted")

delivery, record, worker, release = pending_save_application()
assert not delivery._prepare_to_quit(timeout=0.05)
assert not delivery._quitting and delivery._operation_current(record["operation_id"])
assert next(item for item in delivery.history.snapshot() if item["id"] == record["id"])["outcome"] == "pending"
release.set()
worker.join(timeout=2)
assert not worker.is_alive()
assert next(item for item in delivery.history.snapshot() if item["id"] == record["id"])["outcome"] == "saved"
report["checks"].append("A quit deadline keeps the application alive and permits the genuine pending writer to complete afterward")
if "--capture-stop" in sys.argv:
    recording = SpeakTypeApp()
    operation_id = recording._new_operation()
    recording._recording_operation_id = operation_id
    recording._recording_start_time = time.time()
    recording._recording_preview_only = True
    assert recording.recorder.start(cancel_event=recording._operation_cancel), recording.recorder.last_start_error
    recording._update_operation_state(operation_id, phase="recording", busy=True)
    time.sleep(0.35)
    with ThreadPoolExecutor(max_workers=1) as executor:
        stopping = executor.submit(recording._stop_recording)
        deadline = time.monotonic() + 3
        while recording._stopping_operation_id is None and time.monotonic() < deadline:
            time.sleep(0.005)
        assert recording._stopping_operation_id == operation_id
        recording._main_cancel()
        deadline = time.monotonic() + 3
        while not stopping.done() and time.monotonic() < deadline:
            NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.02))
        stopping.result(timeout=1)
    assert recording._main_state["phase"] == "cancelled" and not recording._main_state["busy"]
    assert not recording._is_processing and not recording.recorder.is_recording
    assert recording.recorder.last_audio_original_samples > 0
    report["captured_stop_samples"] = recording.recorder.last_audio_original_samples
    assert recording._stopping_operation_id is None and recording._processing_thread is None
    report["checks"].append("An actual microphone stream stopped concurrently with cancellation keeps cancelled state and dispatches no ASR worker")
destination = root / "work" / ("bundle-lifecycle-report.json" if bundle else "lifecycle-report.json")
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"REPORT {destination}")
