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
from Foundation import NSDate, NSRunLoop

from speaktype.config import CONFIG_DIR, DEFAULT_CONFIG, load_config
from speaktype.i18n import t
from speaktype.model_download import is_model_cached
from speaktype.permissions import get_permission_status, microphone_is_authorized
from speaktype.setup_wizard import SetupWizardController, _check_ollama_model


assert CONFIG_DIR.is_relative_to(root / "work"), "Use an isolated SPEAKTYPE_CONFIG_DIR under work"
if bundle:
    assert Path(sys.prefix).resolve().is_relative_to(Path(bundle).resolve())
AppKit.NSApplication.sharedApplication()
permissions = get_permission_status()
assert microphone_is_authorized() and permissions.accessibility and permissions.post_event and permissions.listen_event
assert is_model_cached(DEFAULT_CONFIG["asr_model"])
assert _check_ollama_model("qwen3-vl:2b-instruct")
assert not _check_ollama_model("qwen3-vl:speaktype-validation-missing-tag")
report = {"runtime": bundle or "source", "cases": []}


def advance():
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.05))


def buttons(controller, action):
    return [view for view in controller.window.contentView().subviews()
            if isinstance(view, AppKit.NSButton) and str(view.action()) == action]


for skip_llm in (False, True):
    complete = []
    config = {**DEFAULT_CONFIG, "setup_completed": False, "polish_enabled": True,
              "translate_enabled": True,
              "llm_model": "qwen3-vl:speaktype-validation-missing-tag" if skip_llm else "qwen3-vl:2b-instruct"}
    wizard = SetupWizardController(config, on_complete=lambda: complete.append(True))
    wizard.show()
    advance()
    assert wizard.window.isVisible() and wizard.STEPS[wizard._step_idx] == "welcome"
    buttons(wizard, "onNext:")[0].performClick_(None)
    advance()
    assert wizard.STEPS[wizard._step_idx] == "permissions"
    assert set(wizard._status_labels) >= {"mic", "access", "listen"}
    buttons(wizard, "onNext:")[0].performClick_(None)
    advance()
    assert wizard.STEPS[wizard._step_idx] == "asr"
    assert len(buttons(wizard, "onNext:")) == 1
    wizard._start_asr_download()
    deadline = time.monotonic() + 60
    while wizard._asr_download_state == "running" and time.monotonic() < deadline:
        advance()
    assert wizard._asr_download_state == "done", wizard._asr_download_error
    assert len(buttons(wizard, "onNext:")) == 1
    buttons(wizard, "onNext:")[0].performClick_(None)
    advance()
    assert wizard.STEPS[wizard._step_idx] == "llm"
    if skip_llm:
        assert f"ollama pull {config['llm_model']}" in wizard._copy_commands.values()
        buttons(wizard, "onSkip:")[0].performClick_(None)
    else:
        assert not wizard._copy_commands
        buttons(wizard, "onNext:")[0].performClick_(None)
    advance()
    assert wizard.STEPS[wizard._step_idx] == "complete"
    buttons(wizard, "onDone:")[0].performClick_(None)
    advance()
    assert complete == [True] and not wizard.window.isVisible()
    stored = load_config()
    assert stored["setup_completed"] is True
    assert stored["polish_enabled"] is (not skip_llm)
    assert stored["translate_enabled"] is (not skip_llm)
    report["cases"].append({"skip_optional_llm": skip_llm,
                            "completed": stored["setup_completed"],
                            "polish_enabled": stored["polish_enabled"],
                            "translate_enabled": stored["translate_enabled"],
                            "complete_asr_cache": True,
                            "single_next_button": True})
destination = root / "work" / ("bundle-setup-wizard-report.json" if bundle else "setup-wizard-report.json")
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"REPORT {destination}")
