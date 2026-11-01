from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

root = Path(__file__).resolve().parents[1]
bundle = os.environ.get("SPEAKTYPE_TEST_BUNDLE")
if not bundle:
    sys.path.insert(0, str(root))

from speaktype.app import SpeakTypeApp
from speaktype.config import CONFIG_DIR, DEFAULT_CONFIG, save_config


assert CONFIG_DIR.is_relative_to(root / "work")
if bundle:
    assert Path(sys.prefix).resolve().is_relative_to(Path(bundle).resolve())
    assert Path(sys.modules["speaktype.app"].__file__).resolve().is_relative_to(Path(bundle).resolve())
save_config({**DEFAULT_CONFIG, "llm_model": "qwen3-vl:2b-instruct", "setup_completed": True,
             "polish_enabled": False, "translate_enabled": False, "sound_feedback": False})
application = SpeakTypeApp()
ui_engine = application.polish_engine
first = application._new_polish_engine()
second = application._new_polish_engine()
assert first is not second and first is not ui_engine and second is not ui_engine
assert first.model == second.model == application.config["llm_model"]
assert first.ollama_url == application.config["ollama_url"].rstrip("/")
application.config["llm_model"] = f"speaktype-validation-missing-{uuid4().hex}:latest"
missing = application._new_polish_engine()
application.config["llm_model"] = second.model
with ThreadPoolExecutor(max_workers=2) as executor:
    available_request = executor.submit(second.check_available)
    missing_request = executor.submit(missing.check_available)
    assert available_request.result(timeout=15), second.last_error
    assert not missing_request.result(timeout=15)
assert missing.last_error and missing.model in missing.last_error
assert not second.last_error and not first.last_error and not ui_engine.last_error
assert first.model == second.model == "qwen3-vl:2b-instruct"
report = {"runtime": bundle or "source", "model": second.model,
          "checks": ["Each operation receives a separate real PolishEngine with configured model and URL",
                     "Concurrent actual Ollama /api/tags requests keep available-model success and missing-model failure in their own instances",
                     "The shared readiness/prewarm engine retains its own state"],
          "requests": "metadata only; no model inference or download"}
destination = root / "work" / ("bundle-polish-isolation-report.json" if bundle else "polish-isolation-report.json")
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"REPORT {destination}")
