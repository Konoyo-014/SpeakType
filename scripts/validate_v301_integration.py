import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

root = Path(__file__).resolve().parents[1]
bundle = os.environ.get("SPEAKTYPE_TEST_BUNDLE")
if not bundle:
    sys.path.insert(0, str(root))

import AppKit
from Foundation import NSDate, NSRunLoop
import soundfile as sf

from speaktype import __version__
from speaktype.app import SpeakTypeApp
from speaktype.config import CONFIG_DIR, DEFAULT_CONFIG, save_config, save_custom_dictionary
from speaktype.history import DictationHistory
from speaktype.hotwords import HotwordStore
from speaktype.edit_observer import EditObservation


parser = argparse.ArgumentParser()
parser.add_argument("--report", type=Path, required=True)
args = parser.parse_args()
assert CONFIG_DIR.is_relative_to(root / "work")
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
if bundle:
    assert Path(sys.prefix).resolve().is_relative_to(Path(bundle).resolve())
    for name in ("speaktype.app", "speaktype.history", "speaktype.hotwords"):
        assert Path(sys.modules[name].__file__).resolve().is_relative_to(Path(bundle).resolve())
save_config({**DEFAULT_CONFIG, "setup_completed": True, "polish_enabled": False,
             "translate_enabled": False, "sound_feedback": False, "language": "en",
             "hotword_learning_enabled": False})
save_custom_dictionary(["PyTorch", "NeurIPS"])
application = SpeakTypeApp()
AppKit.NSApplication.sharedApplication()
application._main_learn_hotword("Speak Type", "SpeakType")
application._main_learn_hotword("", "SpeakType")
assert "Speak Type" in application.hotwords.get_all()[0]["aliases"]
context = application._hotword_context_for_app({})
assert {"PyTorch", "NeurIPS", "SpeakType"}.issubset(context.terms)
assert context.context.startswith("Vocabulary: ")
application.asr.load()
if application.asr._warmup_thread is not None:
    application.asr._warmup_thread.join(timeout=120)
    assert not application.asr._warmup_thread.is_alive()
application._show_main_window()


def advance():
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.04))


def process(samples, rate, app_info):
    operation = application._new_operation()
    worker = threading.Thread(target=application._process_audio,
                              args=(samples.copy(), len(samples) / rate),
                              kwargs={"insert_result": False, "app_info": app_info, "operation_id": operation})
    application._processing_thread = worker
    worker.start()
    deadline = time.monotonic() + 150
    while worker.is_alive() and time.monotonic() < deadline:
        advance()
    assert not worker.is_alive(), "Actual ASR pipeline did not finish"
    assert application._main_state["phase"] == "done", application._main_state
    assert not application._is_processing
    return application.history.get_recent(1)[0]


report = {"version": __version__, "runtime": bundle or "source", "checks": [], "audio": []}
try:
    path = CONFIG_DIR / "dictation.wav"
    sentence = "Please open the Speak Type project and save the notes."
    subprocess.run(["say", "-v", "Samantha", "--file-format=WAVE", "--data-format=LEI16@16000",
                    "--channels=1", "-o", str(path), sentence], check=True)
    samples, rate = sf.read(path, dtype="float32")
    assert rate == 16000
    first = process(samples, rate, {})
    assert "SpeakType" in first["polished"], first
    assert first["hotword_terms"] == context.terms
    assert "SpeakType" in first["raw"] or "Speak Type" in first["raw"], first
    loaded = DictationHistory(path=application.history.path).get_recent(1)[0]
    assert loaded["hotword_terms"] == first["hotword_terms"]
    assert loaded["hotword_changes"] == first["hotword_changes"]
    report["audio"].append({"source": "macOS built-in speech synthesis", "sentence": sentence,
                            "original": first["raw"], "final": first["polished"],
                            "hints": first["hotword_terms"], "changes": first["hotword_changes"]})
    report["checks"].append("Actual Qwen ASR flows through the application into persisted original/final text and vocabulary metadata")

    application.corrections.add("Speak Type", "LegacyProject")
    application.corrections.add("SpeakType", "LegacyProject")
    test_result = application._apply_vocabulary_corrections("Please open the Speak Type project and save the notes.")
    assert "LegacyProject" in test_result.text
    assert any(change.original == "Speak Type" and change.replacement == "LegacyProject" for change in test_result.changes)
    with_existing_rules = process(samples, rate, {})
    same_input_result = application._apply_vocabulary_corrections(with_existing_rules["raw"])
    assert with_existing_rules["polished"] == same_input_result.text, (with_existing_rules, same_input_result)
    assert any(change["replacement"] == "LegacyProject" for change in with_existing_rules["hotword_changes"])
    application.config["hotword_context_enabled"] = False
    assert application._apply_vocabulary_corrections("Speak Type").text == "LegacyProject"
    application.config["hotword_context_enabled"] = True
    application.corrections.remove("Speak Type")
    application.corrections.remove("SpeakType")
    report["checks"].append("The real ASR pipeline and vocabulary test share saved correction rules, rule order and explicit change details")

    correction = application.hotwords.apply("使用Speak Type和pytorch。", dictionary=["PyTorch"])
    assert correction.text == "使用SpeakType和PyTorch。"
    operation = application._new_operation()
    metadata = [asdict(change) for change in correction.changes]
    entry = application._retain_dictation("使用Speak Type和pytorch。", correction.text, {},
                                          operation_id=operation, hotword_changes=metadata,
                                          hotword_terms=context.terms)
    assert application._commit_dictation_text(entry, correction.text, operation, outcome="saved")
    application._main_select_recent(entry["id"])
    assert application._main_state["hotword_changes"] == metadata
    assert "SpeakType" in application._main_controller._hotword_summary.stringValue()
    assert "Speak Type → SpeakType" in application._main_controller._hotword_summary.toolTip()
    application._main_edit(correction.text + "已核对。")
    loaded = next(item for item in DictationHistory(path=application.history.path).snapshot() if item["id"] == entry["id"])
    assert loaded["raw"] == "使用Speak Type和pytorch。" and loaded["hotword_changes"] == metadata
    assert loaded["hotword_terms"] == context.terms and loaded["polished"].endswith("已核对。")
    report["checks"].append("Real replacement metadata survives native recent-record selection, user editing and history reload")

    for index in range(9):
        application.history.add(f"历史检查 {index}", f"历史检查 {index}", outcome="saved")
    assert entry["id"] not in {item["id"] for item in application.history.get_recent(8)}
    application._show_history(None)
    history_window = application._history_controller
    history_window._search.setStringValue_("使用Speak Type和pytorch")
    history_window._filter_rows()
    assert history_window._selected_entry()["id"] == entry["id"]
    assert history_window._vocabulary_button.isEnabled()
    assert history_window._open_button.isEnabled()
    history_window._open_button.performClick_(None)
    assert application._latest_dictation["id"] == entry["id"]
    assert application._main_state["hotword_changes"] == metadata
    assert application._main_controller.get_final_text().endswith("已核对。")
    assert not history_window.window.isVisible()
    report["checks"].append("A record older than the recent eight opens from full history into the actual editor with its original correction details")

    application._main_learn_hotword("", "FreshTerm")
    assert "FreshTerm" in application._hotword_context_for_app({}).terms
    application.hotwords.set_active("SpeakType", False)
    assert "SpeakType" not in application._hotword_context_for_app({}).terms
    assert application.hotwords.apply("Speak Type").text == "Speak Type"
    assert HotwordStore().get_all() == application.hotwords.get_all()
    application.config["hotword_context_enabled"] = False
    assert application._hotword_context_for_app({}).terms == []
    application._open_hotwords_window(None)
    vocabulary_window = application._hotwords_controller
    vocabulary_window._test_input.setString_("pytorch")
    assert vocabulary_window.test_text().text == "pytorch"
    assert "关闭" in application._vocabulary_test_status()
    application.config["hotword_context_enabled"] = True
    assert vocabulary_window.test_text().text == "PyTorch"
    vocabulary_window.close()
    application.hotwords.upsert_manual("ScopedTerm", ["scope term"], scope_app="TextEdit")
    assert "ScopedTerm" not in application._hotword_context_for_app({"name": "Mail"}).terms
    assert "ScopedTerm" in application._hotword_context_for_app({"name": "TextEdit"}).terms
    report["checks"].append("New terms apply immediately; pause, global vocabulary switch and application scope control the real application context")
    report["checks"].append("The vocabulary test uses the same application correction function and current feature settings as actual dictation")

    application.config["hotword_learning_enabled"] = True
    observation = EditObservation(
        raw_text="Please use pie torch for the audio model.",
        inserted_text="Please use pie torch for the audio model.",
        edited_text="Please use PyTorch for the audio model.",
        app_info={"name": "TextEdit", "bundle_id": "com.apple.TextEdit"}, scene="code", language="en",
    )
    previous = next((entry for entry in application.hotwords.get_all() if entry["term"] == "PyTorch"), None)
    count = previous["observations"] if previous else 0
    application._handle_observed_edit(observation)
    learned = next(entry for entry in application.hotwords.get_all() if entry["term"] == "PyTorch")
    assert learned["observations"] == count + 1, learned
    application.config["hotword_learning_enabled"] = False
    application._handle_observed_edit(observation)
    paused = next(entry for entry in application.hotwords.get_all() if entry["term"] == "PyTorch")
    assert paused["observations"] == learned["observations"]
    report["learning"] = {"model": application.config["llm_model"], "term": learned["term"],
                          "observations_added": 1, "confidence": learned["confidence"],
                          "aliases": learned["aliases"], "disabled_learning_prevents_new_observation": True}
    report["checks"].append("The actual local language model learns an immediate technical-term edit once; disabling learning prevents another observation")
finally:
    application._main_controller.dispose()
    application._main_controller = None
    application._status_overlay.hide()
    application._cancel_edit_observation()
    if application.hotkey_listener:
        application.hotkey_listener.stop()
    application._permission_watch_stop.set()
    if application._readiness_thread is not None:
        application._readiness_thread.join(timeout=20)
        assert not application._readiness_thread.is_alive()
    if application._history_controller is not None:
        application._history_controller.close()
    if getattr(application, "_hotwords_controller", None) is not None:
        application._hotwords_controller.close()
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"REPORT {args.report}")
