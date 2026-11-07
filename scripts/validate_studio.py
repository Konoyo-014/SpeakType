import json
import os
from pathlib import Path
import sys
import time

root = Path(__file__).resolve().parents[1]
bundle = os.environ.get("SPEAKTYPE_TEST_BUNDLE")
if not bundle:
    sys.path.insert(0, str(root))

import AppKit
from Foundation import NSDate, NSMakeSize, NSRunLoop

from speaktype.app import SpeakTypeApp
from speaktype.config import CONFIG_DIR, DEFAULT_CONFIG, save_config
from speaktype.hotwords import HotwordStore
from speaktype.history import DictationHistory
from speaktype.i18n import set_language


assert CONFIG_DIR.is_relative_to(root / "work")
if bundle:
    assert Path(sys.prefix).resolve().is_relative_to(Path(bundle).resolve())
    assert Path(sys.modules["speaktype.app"].__file__).resolve().is_relative_to(Path(bundle).resolve())
    assert Path(sys.modules["speaktype.hotwords"].__file__).resolve().is_relative_to(Path(bundle).resolve())
save_config({**DEFAULT_CONFIG, "setup_completed": True, "polish_enabled": False,
             "translate_enabled": False, "sound_feedback": False,
             "hotword_learning_enabled": False})
DictationHistory().clear()
application = SpeakTypeApp()
AppKit.NSApplication.sharedApplication()
AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
AppKit.NSApp.finishLaunching()
set_language("zh")
application._show_main_window()
controller = application._main_controller
if bundle:
    assert Path(sys.modules["speaktype.main_window"].__file__).resolve().is_relative_to(Path(bundle).resolve())
    assert Path(sys.modules["speaktype.design"].__file__).resolve().is_relative_to(Path(bundle).resolve())


def advance():
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))
    while True:
        event = AppKit.NSApp.nextEventMatchingMask_untilDate_inMode_dequeue_(
            AppKit.NSEventMaskAny, NSDate.distantPast(), AppKit.NSDefaultRunLoopMode, True)
        if event is None:
            break
        AppKit.NSApp.sendEvent_(event)
    AppKit.NSApp.updateWindows()


def wait_for_models():
    deadline = time.monotonic() + 120
    while not application.asr._loaded or any(worker is not None and worker.is_alive() for worker in (
        application._engine_thread, application.asr._load_thread, application.asr._warmup_thread,
    )):
        assert not application._engine_error, application._engine_error
        assert time.monotonic() < deadline, "The actual speech engine did not finish loading"
        advance()
    application._refresh_main_readiness()
    while application._readiness_thread is not None and application._readiness_thread.is_alive():
        assert time.monotonic() < deadline, "Readiness inspection did not finish"
        advance()
    advance()
    application._refresh_main_window_main()
    assert not application._is_processing
    assert controller._snapshot["phase"] not in {"loading", "transcribing", "polishing", "translating", "delivering"}
    assert next(item for item in controller._readiness_details if item["key"] == "asr")["status"] == "ready"


def render(name):
    advance()
    view = controller.window.contentView()
    bitmap = view.bitmapImageRepForCachingDisplayInRect_(view.bounds())
    view.cacheDisplayInRect_toBitmapImageRep_(view.bounds(), bitmap)
    data = bitmap.representationUsingType_properties_(AppKit.NSBitmapImageFileTypePNG, {})
    destination = root / "work" / name
    assert data.writeToFile_atomically_(str(destination), True)
    return str(destination)


wait_for_models()
assert controller.get_final_text() == ""
assert controller._empty_hint.isHidden() is False
assert controller._status_label.frame().origin.y >= 0
assert controller._status_label.frame().origin.y + controller._status_label.frame().size.height <= controller._status_label.superview().bounds().size.height
assert all(button.imageHugsTitle() for button in (controller._record_button, controller._polish_button,
                                                  controller._translate_button, controller._copy_button,
                                                  controller._insert_button))
empty_render = render("studio-v301-empty-zh.png")
application.hotwords.upsert_manual("Qwen3-ASR", ["千问"], scope_app="com.apple.TextEdit", scope_scene="code")
application._main_learn_hotword("", "Qwen3-ASR")
scoped = next(entry for entry in application.hotwords.get_all() if entry["term"] == "Qwen3-ASR")
assert scoped["aliases"] == ["千问"]
assert scoped["scope_app"] == "com.apple.TextEdit" and scoped["scope_scene"] == "code"
application._main_learn_hotword("斯匹克泰普", "SpeakType")
assert controller._save_hotword("Speak Type", "SpeakType") is True
assert controller._save_hotword("", "a") is False
assert "2 to 80" in controller._status_label.stringValue()
assert controller._save_hotword("", "完整句子。") is False
assert "word or short name" in controller._status_label.stringValue()
assert controller._save_hotword("", "NeurIPS") is True
persisted = HotwordStore().get_all()
assert any(entry["term"] == "Qwen3-ASR" and "千问" in entry["aliases"] for entry in persisted)
assert any(entry["term"] == "SpeakType" and "斯匹克泰普" in entry["aliases"] for entry in persisted)
assert any(entry["term"] == "SpeakType" and "Speak Type" in entry["aliases"] for entry in persisted)
application._retain_dictation("使用千问检查斯匹克泰普的热词。", "使用 Qwen3-ASR 检查 SpeakType 的热词。", {},
                              hotword_changes=[{"original": "千问", "replacement": "Qwen3-ASR", "term": "Qwen3-ASR"},
                                               {"original": "斯匹克泰普", "replacement": "SpeakType", "term": "SpeakType"}])
advance()
text = controller.get_final_text()
prefix = text.index("Qwen3-ASR")
location = len(text[:prefix].encode("utf-16-le")) // 2
controller._final_view.setSelectedRange_((location, len("Qwen3-ASR")))
advance()
assert controller._selected_final_text() == "Qwen3-ASR"
assert controller._learn_button.isEnabled()
assert "Qwen3-ASR" in controller._hotword_summary.stringValue()
controller._final_view.setSelectedRange_((0, 0))
advance()
assert not controller._learn_button.isEnabled()
assert controller._raw_scroll.isHidden()
height = controller._final_scroll.frame().size.height
controller._raw_disclosure.performClick_(None)
advance()
assert controller._raw_expanded and not controller._raw_scroll.isHidden()
assert controller._final_scroll.frame().size.height == height - 96
assert controller._raw_view.string() == "使用千问检查斯匹克泰普的热词。"
controller._raw_disclosure.performClick_(None)
advance()
assert not controller._raw_expanded and controller._raw_scroll.isHidden()
assert controller._final_scroll.frame().size.height == height
controller._vocabulary_nav.performClick_(None)
advance()
assert application._hotwords_controller.window.isVisible()
application._hotwords_controller.window.close()
controller.window.makeKeyAndOrderFront_(None)
zh_render = render("studio-v301-zh.png")
controller.window.setAppearance_(AppKit.NSAppearance.appearanceNamed_(AppKit.NSAppearanceNameDarkAqua))
dark_render = render("studio-v301-zh-dark.png")
controller.window.setAppearance_(AppKit.NSAppearance.appearanceNamed_(AppKit.NSAppearanceNameAqua))
controller.window.setContentSize_(NSMakeSize(controller.MIN_WIDTH, controller.MIN_HEIGHT))
advance()
controller._raw_disclosure.performClick_(None)
advance()
assert controller._final_scroll.frame().size.height >= 150
assert controller._editor_material.frame().origin.x >= 0
assert controller._editor_material.frame().origin.x + controller._editor_material.frame().size.width <= controller._workspace.bounds().size.width
assert controller._insert_button.frame().origin.x + controller._insert_button.frame().size.width <= controller._footer.bounds().size.width
compact_render = render("studio-v301-compact.png")
controller.dispose()
application._main_controller = None
application.config["ui_language"] = "en"
set_language("en")
application._show_main_window()
controller = application._main_controller
wait_for_models()
assert controller._learn_button.title() == "Remember this word"
assert controller._vocabulary_nav.title() == "Vocabulary"
assert controller._final_view.accessibilityLabel() == "Final text"
en_render = render("studio-v301-en.png")
controller.dispose()
application._status_overlay.hide()
report = {"runtime": bundle or "source", "checks": ["Real app callback saved preferred spellings and aliases to isolated JSON",
                     "Remembering an existing word preserves its aliases and application/scene scopes",
                     "Invalid short words and complete sentences show the concrete validation error",
                     "Speech engine actually loaded and readiness worker completed before selection validation",
                     "Saving a selected misrecognition with a revised preferred spelling retains the alias",
                     "Native UTF-16 text selection enables vocabulary action",
                     "Native disclosure really shows original text and resizes the editor without changing it",
                     "Clearing selection disables vocabulary action",
                     "Actual vocabulary window opens from studio navigation",
                     "Per-dictation vocabulary changes are visible",
                     "Chinese and English native view rendering",
                     "Dark appearance and minimum window size with expanded original transcription"],
          "renders": [empty_render, zh_render, en_render, dark_render, compact_render], "config": str(CONFIG_DIR)}
destination = root / "work" / "studio-v301-report.json"
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"REPORT {destination}")
if "--review" in sys.argv:
    application._main_controller = None
    application.config["ui_language"] = "zh"
    set_language("zh")
    application._show_main_window()
    controller = application._main_controller
    wait_for_models()
    print(f"READY_STUDIO_REVIEW pid={os.getpid()}", flush=True)
    while controller.window.isVisible():
        advance()
    controller.dispose()
    application._status_overlay.hide()
