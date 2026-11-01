import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import time


root = Path(__file__).resolve().parents[1]
if not os.environ.get("SPEAKTYPE_TEST_BUNDLE"):
    sys.path.insert(0, str(root))

import AppKit
from Foundation import NSDate, NSRunLoop
from PyObjCTools.AppHelper import callLater, runEventLoop, stopEventLoop

from speaktype.audio import AudioRecorder
from speaktype.config import CONFIG_DIR, DEFAULT_CONFIG, load_config, save_config
from speaktype.inserter import _restore_pasteboard, _snapshot_pasteboard
from speaktype.model_manager import inspect_asr
from speaktype.permissions import get_permission_status, microphone_is_authorized
from speaktype.setup_center import SetupCenterController


parser = argparse.ArgumentParser()
parser.add_argument("--exercise-active-download", action="store_true")
parser.add_argument("--exercise-upgrade-error", action="store_true")
parser.add_argument("--exercise-cache-repair", action="store_true")
parser.add_argument("--inspect-seconds", type=float, default=0)
args = parser.parse_args()
assert CONFIG_DIR.is_relative_to(root / "work"), "Use an isolated SPEAKTYPE_CONFIG_DIR under work"
bundle = os.environ.get("SPEAKTYPE_TEST_BUNDLE")
if bundle:
    assert Path(sys.modules["speaktype.setup_center"].__file__).resolve().is_relative_to(Path(bundle).resolve())

application = AppKit.NSApplication.sharedApplication()
application.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
initial = {**DEFAULT_CONFIG, "ui_language": "zh", "polish_enabled": False, "translate_enabled": False}
current = deepcopy(initial)
save_config(current)


def save_patch(patch):
    current.update(patch)
    save_config(current)


def wait_until(predicate, timeout=20):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise TimeoutError("The native setup center did not reach the expected state")
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.03))


def verify_error_sheet(kind):
    expected = controller._errors[kind]
    assert not controller._controls[f"{kind}.error"].isHidden()
    pasteboard = AppKit.NSPasteboard.generalPasteboard()
    original = _snapshot_pasteboard(pasteboard)
    try:
        controller._controls[f"{kind}.error"].performClick_(None)
        wait_until(lambda: controller._error_alert is not None and controller._error_alert.window().isVisible())
        assert controller._error_view.string() == expected
        assert not controller._error_view.isEditable()
        assert controller._error_view.isSelectable()
        previous = deepcopy(controller.config)
        controller.apply_config({**previous, "ui_language": "en"})
        assert controller._error_alert.messageText() == "Model preparation failed"
        assert controller._error_alert.buttons()[1].title() == "Copy error"
        assert controller._error_view.string() == expected
        controller.apply_config(previous)
        controller._error_alert.buttons()[1].performClick_(None)
        wait_until(lambda: controller._error_alert is None)
        assert pasteboard.stringForType_(AppKit.NSPasteboardTypeString) == expected
    finally:
        _restore_pasteboard(pasteboard, original)


recorder = AudioRecorder()
controller = SetupCenterController(initial, save_patch, recorder.start)
controller.show()
wait_until(lambda: not any(controller._checking.values()))
assert controller.window.isVisible()
assert controller.window.contentView().frame().size.width == 1000
assert controller.window.contentView().frame().size.height == 720
assert controller._microphone == microphone_is_authorized()
assert controller._permissions == get_permission_status()
if args.exercise_cache_repair:
    assert controller._asr_cache_error
    assert controller._states["asr"] == "failed"
    try:
        inspect_asr(initial["asr_model"])
    except json.JSONDecodeError:
        pass
    else:
        raise AssertionError("Cache repair validation requires an actually damaged JSON file")
else:
    assert controller._asr_snapshot == inspect_asr(initial["asr_model"])
assert initial["polish_enabled"] is False
report = {"runtime": bundle or "source", "window": str(controller.window.title()),
          "microphone": controller._microphone, "input_permissions": controller.input_permissions_ready,
          "asr": controller._asr_snapshot, "ollama": controller._ollama_snapshot}

controller._controls["polish.enabled"].performClick_(None)
assert load_config()["polish_enabled"] is True
assert initial["polish_enabled"] is False
controller._controls["translation.enabled"].performClick_(None)
assert load_config()["translate_enabled"] is True
controller._controls["dictation.only"].performClick_(None)
assert load_config()["polish_enabled"] is False
assert load_config()["translate_enabled"] is False
report["feature_changes_saved"] = True

models = controller._ollama_snapshot["models"]
if models:
    popup = controller._controls["ollama.model"]
    index = controller._model_choices.index(models[0]["name"])
    popup.selectItemAtIndex_(index)
    popup.sendAction_to_(popup.action(), popup.target())
    assert load_config()["llm_model"] == models[0]["name"]
    report["installed_model_selected"] = models[0]["name"]

window_number = controller.window.windowNumber()
controller.window.performClose_(None)
assert not controller.window.isVisible()
controller.show()
assert controller.window.windowNumber() == window_number
wait_until(lambda: not any(controller._checking.values()))
report["same_window_after_close"] = True

if args.exercise_cache_repair:
    assert controller._controls["asr.download"].title() == "重新下载完整模型"
    report["real_cache_error"] = controller._errors["asr"]
    verify_error_sheet("asr")
    report["complete_cache_error_copied"] = True
    assert controller._controls["asr.download"].isEnabled()
    controller._controls["asr.download"].performClick_(None)
    wait_until(lambda: (controller._progress["asr"] is not None and controller._progress["asr"].completed > 0)
               or controller._states["asr"] == "failed", timeout=60)
    if controller._states["asr"] == "failed":
        raise RuntimeError(controller._errors["asr"])
    progress = controller._progress["asr"]
    assert 0 < progress.completed <= progress.total
    report["actual_cache_repair_progress"] = {"completed": progress.completed, "total": progress.total,
                                               "percent": progress.percent}
    controller._controls["asr.cancel"].performClick_(None)
    wait_until(lambda: controller._tasks["asr"] is None, timeout=20)
    assert controller._states["asr"] == "cancelled"
    report["cache_repair_cancelled"] = True

if args.exercise_active_download:
    controller._change_config({"llm_model": initial["llm_model"]})
    controller._controls["ollama.download"].performClick_(None)
    wait_until(lambda: (controller._progress["ollama"] is not None and controller._progress["ollama"].total > 0)
               or controller._states["ollama"] == "failed", timeout=40)
    if controller._states["ollama"] == "failed":
        raise RuntimeError(controller._errors["ollama"])
    progress = controller._progress["ollama"]
    assert 0 < progress.completed <= progress.total
    assert 0 <= progress.percent <= 100
    report["actual_download_progress"] = {"completed": progress.completed, "total": progress.total,
                                          "percent": progress.percent}
    token = controller._tasks["ollama"]
    current["ui_language"] = "en"
    save_config(current)
    controller.apply_config(current)
    assert controller._tasks["ollama"] is token
    assert controller.window.windowNumber() == window_number
    assert controller._controls["ollama.cancel"].title() == "Cancel download"
    current["ui_language"] = "zh"
    save_config(current)
    controller.apply_config(current)
    assert controller._tasks["ollama"] is token
    report["language_change_preserved_active_task"] = True
    controller.close()
    assert controller._tasks["ollama"] is not None
    controller.show()
    assert controller.window.windowNumber() == window_number
    controller._controls["ollama.cancel"].performClick_(None)
    wait_until(lambda: controller._tasks["ollama"] is None, timeout=20)
    assert controller._states["ollama"] == "cancelled"
    assert "重试" in controller._controls["ollama.download"].title()
    report["download_cancelled_after_reopen"] = True

if args.exercise_upgrade_error:
    controller._change_config({"llm_model": "qwen3-vl:4b-instruct"})
    wait_until(lambda: not controller._checking["ollama"])
    assert controller._controls["ollama.download"].isEnabled()
    controller._controls["ollama.download"].performClick_(None)
    wait_until(lambda: controller._tasks["ollama"] is None, timeout=40)
    assert controller._states["ollama"] == "failed", controller._states["ollama"]
    assert controller._ollama_update_required
    assert "更新 Ollama" in controller._controls["ollama.service.action"].title()
    report["real_upgrade_error"] = controller._errors["ollama"]
    report["upgrade_action_available"] = True
    verify_error_sheet("ollama")
    report["complete_service_error_copied"] = True
    if models:
        controller._change_config({"llm_model": models[0]["name"]})

current["ui_language"] = "en"
save_config(current)
controller.apply_config(current)
wait_until(lambda: not any(controller._checking.values()))
assert controller.window.title() == "Get SpeakType ready"
assert controller._controls["back"].title() == "Back to main window"
assert controller._controls["asr.error"].title() == "Error details…"
assert controller._controls["ollama.error"].title() == "Error details…"
report["english_labels"] = True
report["dictation_ready"] = controller.ready_for_dictation
output = root / "work" / "setup-center-validation"
output.mkdir(parents=True, exist_ok=True)
report_name = "cache-repair-report.json" if args.exercise_cache_repair else "report.json"
(output / report_name).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
if args.inspect_seconds > 0:
    callLater(args.inspect_seconds, stopEventLoop)
    runEventLoop()
controller._controls["back"].performClick_(None)
assert not controller.window.isVisible()
controller.shutdown()
print("Native setup center permissions, cache, actual service, persisted controls, close/reopen, and labels passed.")
