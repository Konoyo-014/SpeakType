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

from speaktype.app import SpeakTypeApp
from speaktype.config import CONFIG_DIR, DEFAULT_CONFIG, load_config, load_custom_dictionary, save_config
from speaktype.settings_window import settings_section_ids


assert CONFIG_DIR.is_relative_to(root / "work"), "Use an isolated SPEAKTYPE_CONFIG_DIR under work"
bundle = os.environ.get("SPEAKTYPE_TEST_BUNDLE")
if bundle:
    assert Path(sys.prefix).resolve().is_relative_to(Path(bundle).resolve())
    assert Path(sys.modules["speaktype.app"].__file__).resolve().is_relative_to(Path(bundle).resolve())
config = {**DEFAULT_CONFIG, "setup_completed": True, "polish_enabled": False,
          "translate_enabled": False, "sound_feedback": False,
          "hotword_learning_enabled": False, "hotword_context_enabled": False}
save_config(config)
application = SpeakTypeApp()
application.history.add("检查原始文本", "检查最终文本。", "TextEdit", 1.5, outcome="inserted")
report = {"runtime": bundle or "source", "windows": [], "settings_sections": []}


def advance():
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.05))


def show_twice(method_name, controller_name):
    method = getattr(application, method_name)
    method(None)
    advance()
    controller = getattr(application, controller_name)
    assert controller.window.isVisible(), method_name
    window_number = controller.window.windowNumber()
    method(None)
    advance()
    assert getattr(application, controller_name) is controller, method_name
    assert controller.window.windowNumber() == window_number
    report["windows"].append({"menu": method_name, "title": str(controller.window.title()),
                              "same_window_on_repeat": True})
    return controller


settings = show_twice("_open_settings", "_settings_controller")
for index, section in enumerate(settings_section_ids()):
    settings._section_buttons[index].performClick_(None)
    advance()
    assert settings._current_section == section
    assert settings._controls, section
    report["settings_sections"].append({"section": section, "controls": list(settings._controls)})
    if section == "features":
        settings._controls["history_enabled"][1].setState_(0)
    elif section == "hotwords":
        settings._controls["hotword_observation_seconds"][1].setStringValue_("27")
        settings._controls["hotword_observation_stable_seconds"][1].setStringValue_("1.7")
settings._render_section("features")
assert settings._controls["history_enabled"][1].state() == 0
settings._render_section("hotwords")
assert settings._controls["hotword_observation_seconds"][1].stringValue() == "27"
assert settings._controls["hotword_observation_stable_seconds"][1].stringValue() == "1.7"
changed = settings._read_controls()
changed.pop("auto_start")
application._apply_settings(changed)
persisted = load_config()
assert persisted["history_enabled"] is False
assert persisted["hotword_observation_seconds"] == 27
assert persisted["hotword_observation_stable_seconds"] == 1.7
assert application.history.max_entries == persisted["history_max_entries"]
settings._do_cancel()
advance()
assert not settings.window.isVisible()
application._open_settings(None)
advance()
assert application._settings_controller is not settings
assert application._settings_controller.config["history_enabled"] is False
application._settings_controller._do_cancel()

dictionary = show_twice("_open_dict", "_dict_controller")
dictionary._word_field.setStringValue_("SpeakType 验证词")
dictionary._add_word()
dictionary._show_section("snippets")
dictionary._snippet_trigger_field.setStringValue_("验证短语")
dictionary._snippet_text_field.setStringValue_("真实保存的快捷短语。")
dictionary._add_snippet()
dictionary._show_section("corrections")
dictionary._correction_wrong_field.setStringValue_("Speak Type")
dictionary._correction_right_field.setStringValue_("SpeakType")
dictionary._add_correction()
dictionary._do_save()
advance()
assert "SpeakType 验证词" in load_custom_dictionary()
assert application.snippets.match("验证短语") == "真实保存的快捷短语。"
assert application.corrections.apply("Speak Type") == "SpeakType"
application._open_dict(None)
advance()
assert application._dict_controller is not dictionary
assert "SpeakType 验证词" in application._dict_controller._words
application._dict_controller.window.close()

controllers = []
for method_name, controller_name in (
    ("_show_history", "_history_controller"),
    ("_show_stats", "_stats_controller"),
    ("_open_hotwords_window", "_hotwords_controller"),
    ("_show_diagnostics", "_diagnostics_controller"),
):
    controller = show_twice(method_name, controller_name)
    controllers.append(controller)
diagnostics = application._diagnostics_controller
assert application._hotwords_controller.hotwords is application.hotwords
assert application.hotwords.add_or_reinforce("Qwen3-ASR", confidence=0.95)
application._hotwords_controller.refresh()
assert any(entry["term"] == "Qwen3-ASR" for entry in application._hotwords_controller._last_entries)
deadline = time.monotonic() + 45
while not diagnostics._last_items and time.monotonic() < deadline:
    advance()
assert diagnostics._last_items, diagnostics._last_report
assert any(item.key == "microphone" for item in diagnostics._last_items), diagnostics._last_items
assert all(item.status in {"ok", "warn", "fail"} for item in diagnostics._last_items)
report["diagnostics"] = [{"key": item.key, "status": item.status} for item in diagnostics._last_items]
for controller in controllers:
    controller.window.close()
application._status_overlay.hide()
destination = root / "work" / ("bundle-native-app-report.json" if bundle else "native-app-report.json")
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"REPORT {destination}")
