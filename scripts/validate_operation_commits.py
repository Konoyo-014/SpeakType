from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import threading
import time

root = Path(__file__).resolve().parents[1]
bundle = os.environ.get("SPEAKTYPE_TEST_BUNDLE")
if not bundle:
    sys.path.insert(0, str(root))

import numpy as np
from Foundation import NSDate, NSRunLoop

from speaktype.app import SpeakTypeApp
from speaktype.config import CONFIG_DIR, DEFAULT_CONFIG, save_config
from speaktype.history import DictationHistory


assert CONFIG_DIR.is_relative_to(root / "work")
if bundle:
    assert Path(sys.prefix).resolve().is_relative_to(Path(bundle).resolve())
    assert Path(sys.modules["speaktype.app"].__file__).resolve().is_relative_to(Path(bundle).resolve())
save_config({**DEFAULT_CONFIG, "setup_completed": True, "polish_enabled": False,
             "translate_enabled": False, "sound_feedback": False,
             "hotword_learning_enabled": False, "hotword_context_enabled": False})
application = SpeakTypeApp()
application.history.clear()
report = {"runtime": bundle or "source", "checks": [], "races": []}
target = {"name": "SpeakType validation", "bundle_id": "", "pid": os.getpid()}


def entry_by_id(identifier):
    return next(item for item in DictationHistory(path=application.history.path).snapshot() if item["id"] == identifier)


def submit_after_signal(executor, started, function, *args, **kwargs):
    def run():
        started.set()
        return function(*args, **kwargs)
    return executor.submit(run)


with ThreadPoolExecutor(max_workers=2) as executor:
    for index in range(24):
        operation_id = application._new_operation()
        original = f"第 {index} 条原始输入：🙂 한국어 café。"
        entry = application._retain_dictation(original, original, target, operation_id=operation_id)
        assert entry is not None
        application._update_operation_state(operation_id, phase="polishing", busy=True)
        started = threading.Event()
        with application._operation_lock:
            future = submit_after_signal(executor, started, application._commit_dictation_text,
                                         entry, f"迟到的结果 {index}", operation_id, outcome="saved")
            assert started.wait(3), "The real worker did not start"
            application._main_cancel()
        assert future.result(timeout=3) is False
        persisted = entry_by_id(entry["id"])
        assert persisted["raw"] == original and persisted["polished"] == original
        assert persisted["outcome"] == "cancelled"
        assert application._main_state["phase"] == "cancelled"
        assert application._main_state["final"] == original
        assert not application._main_state["busy"] and not application._is_processing
        report["races"].append({"case": index, "commit_accepted": False, "outcome": persisted["outcome"]})
    report["checks"].append("24 real worker commits wait on the production operation lock; cancellation rejects every late result and preserves original text in persisted cancelled records")

    operation_id = application._new_operation()
    entry = application._retain_dictation("文件写入期间的原始文本。", "文件写入期间的原始文本。", target, operation_id=operation_id)
    application._update_operation_state(operation_id, phase="polishing", busy=True)
    with application.history._lock:
        commit_future = executor.submit(application._commit_dictation_text, entry, "原子保存完成的最终文本。", operation_id, outcome="saved")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            acquired = application._operation_lock.acquire(blocking=False)
            if not acquired:
                break
            application._operation_lock.release()
            time.sleep(0.002)
        assert not acquired, "The real writer did not enter its atomic commit"
        started = threading.Event()
        cancel_future = submit_after_signal(executor, started, application._main_cancel)
        assert started.wait(3)
        assert not cancel_future.done()
        assert not application._operation_cancel.is_set()
    deadline = time.monotonic() + 5
    while not (commit_future.done() and cancel_future.done()) and time.monotonic() < deadline:
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.02))
    assert commit_future.result(timeout=1) is True
    cancel_future.result(timeout=1)
    persisted = entry_by_id(entry["id"])
    assert persisted["polished"] == "原子保存完成的最终文本。" and persisted["outcome"] == "saved"
    assert application._main_state["phase"] == "cancelled" and not application._main_state["busy"]
    report["checks"].append("A real history-lock contention holds the atomic writer; a concurrent cancellation waits for the entire write, preserving the completed saved result")

    old_operation = application._new_operation()
    count = len(application.history.snapshot())
    started = threading.Event()
    with application._operation_lock:
        future = submit_after_signal(executor, started, application._retain_dictation,
                                     "尚未提交的原始文本。", "尚未提交的原始文本。", target, operation_id=old_operation)
        assert started.wait(3)
        application._main_cancel()
    assert future.result(timeout=3) is None
    assert len(application.history.snapshot()) == count
    assert application._update_operation_state(old_operation, phase="done", final="迟到内容") is False
    report["checks"].append("Cancellation also rejects late record creation and late phase/final updates")

    old_operation = application._new_operation()
    old_entry = application._retain_dictation("旧作业原始文本。", "旧作业原始文本。", target, operation_id=old_operation)
    application._main_cancel()
    operation_id = application._new_operation()
    current_entry = application._retain_dictation("新作业原始文本。", "新作业编辑结果。", target, operation_id=operation_id)
    assert application._commit_dictation_text(current_entry, "新作业已保存的结果。", operation_id, outcome="saved")
    state_before = dict(application._main_state)
    snapshot_before = application.history.snapshot()
    assert executor.submit(application._commit_dictation_text, old_entry, "迟到旧结果", old_operation, outcome="saved").result(timeout=3) is False
    assert executor.submit(application._finish_dictation_delivery, old_entry, False, operation_id=old_operation).result(timeout=3) is False
    executor.submit(application._finish_operation, old_operation).result(timeout=3)
    assert application._main_state == state_before
    assert application.history.snapshot() == snapshot_before
    assert application._latest_dictation["id"] == current_entry["id"]
    report["checks"].append("An old operation cannot overwrite the next operation's state, final text, latest record, history outcome or cleanup")

    application._main_cancel()
    assert entry_by_id(current_entry["id"])["outcome"] == "saved"
    assert entry_by_id(current_entry["id"])["polished"] == "新作业已保存的结果。"
    report["checks"].append("A result saved atomically before cancellation keeps its saved outcome and final text")

    count = len(application.history.snapshot())
    application.config["history_enabled"] = False
    operation_id = application._new_operation()
    session_entry = application._retain_dictation("仅当前会话的原始文本。", "仅当前会话的原始文本。", target, operation_id=operation_id)
    assert "id" not in session_entry
    started = threading.Event()
    with application._operation_lock:
        future = submit_after_signal(executor, started, application._commit_dictation_text,
                                     session_entry, "迟到的会话文本", operation_id, outcome="saved")
        assert started.wait(3)
        application._main_cancel()
    assert future.result(timeout=3) is False
    assert application._latest_dictation["outcome"] == "cancelled"
    assert application._latest_dictation["polished"] == "仅当前会话的原始文本。"
    assert len(application.history.snapshot()) == count
    report["checks"].append("History-disabled sessions retain cancelled raw text without creating persistent records")

    application._process_audio(np.zeros(16000, dtype=np.float32), 1.0, operation_id=operation_id, insert_result=False)
    assert not application._is_processing and not application._main_state["busy"]
    assert application._main_state["phase"] == "cancelled"
    report["checks"].append("A cancelled job entering the real pipeline cannot restore processing or busy state")

application._status_overlay.hide()
report["persisted_records"] = len(DictationHistory(path=application.history.path).snapshot())
destination = root / "work" / ("bundle-operation-commits-report.json" if bundle else "operation-commits-report.json")
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"REPORT {destination}")
