import csv
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

root = Path(__file__).resolve().parents[1]
bundle = os.environ.get("SPEAKTYPE_TEST_BUNDLE")
if not bundle:
    sys.path.insert(0, str(root))

import AppKit
from Foundation import NSDate, NSRunLoop

from speaktype.config import CONFIG_DIR, load_custom_dictionary, save_custom_dictionary
from speaktype.hotwords import HotwordStore
from speaktype.hotwords_window import HotwordsWindowController, hotword_export_payload
from speaktype.i18n import set_language


assert CONFIG_DIR.is_relative_to(root / "work")
destination = root / "work" / "vocabulary-priority-validation"
destination.mkdir(parents=True, exist_ok=True)
run = destination / uuid4().hex
run.mkdir()
AppKit.NSApplication.sharedApplication()
set_language("zh")
save_custom_dictionary([])
assert load_custom_dictionary() == []
store = HotwordStore(run / "hotwords.json")
controller = HotwordsWindowController(store)
controller.show()
checks = []
terms = ["Apache Arrow", "AppKit", "AudioCraft", "AVFoundation", "BERT", "Chroma", "CoreAudio",
         "CUDA", "DeepSpeed", "Docker", "DynamoDB", "FastAPI", "Flask", "Gemini", "GitHub",
         "Hugging Face", "JAX", "Jupyter", "Kubernetes", "LightGBM", "Matplotlib", "MLflow",
         "NeurIPS", "NumPy", "Ollama", "OpenCV", "Pandas", "PyTorch", "Qwen3-ASR", "Raycast",
         "Scikit-learn", "SpeakType", "TensorFlow", "WhisperKit", "Zotero"]
text_path = run / "words.txt"
text_path.write_text("\ufeff" + "\r\n".join(terms) + "\r\n\r\n", encoding="utf-8")
assert controller.import_file(text_path) == len(terms)
assert len(controller._visible_rows) == 35
assert len(controller._context_selection.terms) == 30
assert controller._context_selection.eligible_count == 35
assert len(controller._context_selection.omitted_terms) == 5
assert "30 / 35" in controller._budget_field.stringValue()
checks.append("TXT import uses a real UTF-8 BOM file with CRLF and blank lines; all 35 words persist and real selection shows 30 of 35")

controller.select_entry("Zotero")
controller._pinned_check.performClick_(None)
assert controller.has_unsaved_changes()
controller.select_entry("NumPy")
controller.select_entry("Zotero")
assert controller._pinned_check.state() == AppKit.NSControlStateValueOn
controller._save_button.performClick_(None)
assert next(entry for entry in HotwordStore(store._path).get_all() if entry["term"] == "Zotero")["pinned"]
assert controller._context_selection.terms[0] == "Zotero"
assert controller._visible_rows[0]["term"] == "Zotero"
controller._filter_buttons["pinned"].performClick_(None)
assert [entry["term"] for entry in controller._visible_rows] == ["Zotero"]
controller._toggle_button.performClick_(None)
assert "Zotero" not in controller._context_selection.terms
controller._toggle_button.performClick_(None)
assert controller._context_selection.terms[0] == "Zotero"
checks.append("Native priority checkbox persists through drafts and save; priority affects the actual hint selector; paused prioritized words remain excluded")

store.record_usage("NumPy works with Zotero.", app_info={"name": "TextEdit", "bundle_id": "com.apple.TextEdit"})
store.record_usage("NumPy.", app_info={"name": "TextEdit", "bundle_id": "com.apple.TextEdit"})
controller.refresh()
controller._filter_buttons["all"].performClick_(None)
controller._sort_picker.selectItemAtIndex_(2)
controller._sort_picker.sendAction_to_(controller._sort_picker.action(), controller._sort_picker.target())
assert [entry["term"] for entry in controller._visible_rows[:2]] == ["NumPy", "Zotero"]
controller.select_entry("NumPy")
assert "使用 2 次" in controller._usage_field.stringValue()
assert "最近" in controller._usage_field.stringValue()
assert store.get_all() == HotwordStore(store._path).get_all()
checks.append("Actual store usage recording drives the native usage sort and details, with persisted counters and recent date; no acoustic accuracy claim")

controller.select_entry("NeurIPS")
controller._aliases_view.setString_('new rips\nnew, rips\nnew "rips"')
assert controller.save_entry()
controller._test_input.setString_('new, rips and new "rips"')
controller._test_button.performClick_(None)
assert controller._test_output.string() == "NeurIPS and NeurIPS"
controller.select_entry("WhisperKit")
controller._app_field.setStringValue_("TextEdit")
controller._pinned_check.setState_(AppKit.NSControlStateValueOn)
assert controller.save_entry()
assert "WhisperKit" not in controller._context_selection.terms
controller._test_app_field.setStringValue_("TextEdit")
controller._test_button.performClick_(None)
assert "WhisperKit" in controller._context_selection.terms
checks.append("Native correction test handles actual quoted/comma aliases; test application changes update the actual eligible hint list and scoped priority")

json_path = run / "vocabulary.json"
csv_path = run / "vocabulary.csv"
controller.export_file(json_path)
controller.export_file(csv_path)
expected = hotword_export_payload(store.get_all())
assert json.loads(json_path.read_text(encoding="utf-8")) == expected
for path in (json_path, csv_path):
    restored = HotwordStore(run / f"restored-{path.suffix[1:]}.json")
    importer = HotwordsWindowController(restored)
    importer.show()
    assert importer.import_file(path) == 35
    assert hotword_export_payload(restored.get_all()) == expected
    importer.close()
checks.append("Real JSON and CSV files round-trip all state, priority, usage, date, per-app counters and quote/comma aliases")

before_reimport = hotword_export_payload(store.get_all())
assert controller.import_file(text_path) == 0
term_only_path = run / "words-only.csv"
with term_only_path.open("w", encoding="utf-8", newline="") as destination_file:
    writer = csv.writer(destination_file)
    writer.writerow(["term"])
    writer.writerows([[term] for term in terms])
assert controller.import_file(term_only_path) == 0
assert hotword_export_payload(store.get_all()) == before_reimport
checks.append("Reimporting TXT or term-only CSV preserves existing aliases, priority, pause/scope settings and usage metadata")

invalid_path = run / "invalid.csv"
with invalid_path.open("w", encoding="utf-8", newline="") as destination_file:
    writer = csv.writer(destination_file)
    writer.writerow(["term", "pinned"])
    writer.writerow(["NewProject", "true"])
    writer.writerow(["InvalidProject", '"yes"'])
before = store._path.read_bytes()
try:
    controller.import_file(invalid_path)
except ValueError:
    pass
else:
    raise AssertionError("Invalid CSV priority must fail before writing")
assert store._path.read_bytes() == before
assert "NewProject" not in {entry["term"] for entry in store.get_all()}
checks.append("A later invalid CSV entry leaves the real file unchanged and imports no earlier entries")

controller._sort_picker.selectItemAtIndex_(0)
controller.select_entry("NeurIPS")
artifacts = []
for appearance, name in [(AppKit.NSAppearanceNameAqua, "priority-zh-light.png"),
                         (AppKit.NSAppearanceNameDarkAqua, "priority-zh-dark.png")]:
    controller.window.setAppearance_(AppKit.NSAppearance.appearanceNamed_(appearance))
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.2))
    view = controller.window.contentView()
    view.setNeedsDisplay_(True)
    view.displayIfNeeded()
    representation = view.bitmapImageRepForCachingDisplayInRect_(view.bounds())
    view.cacheDisplayInRect_toBitmapImageRep_(view.bounds(), representation)
    data = representation.representationUsingType_properties_(AppKit.NSBitmapImageFileTypePNG, {})
    path = destination / name
    assert data.writeToFile_atomically_(str(path), True)
    artifacts.append(str(path))
controller.close()
large_entries = []
for index in range(10020):
    state = ("active", "pending", "disabled")[index % 3]
    aliases = [f"alternative term {index:05d}", f"候选词语 {index:05d}"]
    approved = aliases if state == "active" else []
    large_entries.append({
        "term": f"VocabularyTerm{index:05d}", "aliases": aliases,
        "state": state, "enabled": state == "active", "pinned": index % 11 == 0,
        "scope_app": "TextEdit" if index % 5 == 0 else "",
        "scope_scene": "notes" if index % 7 == 0 else "",
        "source": "imported", "confidence": 0.82 if state == "active" else 0.2,
        "observations": index % 9, "user_confirmed": state == "active",
        "approved_aliases": approved, "alias_confidences": {alias: 0.82 for alias in aliases},
        "usage_count": index % 13,
        "last_used_at": "2026-11-07T12:00:00+00:00" if index % 13 else "",
        "usage_apps": {"com.apple.TextEdit": index % 13} if index % 13 else {},
    })
large_store = HotwordStore(run / "large-words.json")
assert large_store.import_manual(large_entries) == 10020
assert len(HotwordStore(large_store._path).get_all()) == 10020
large_controller = HotwordsWindowController(large_store)
large_expected = hotword_export_payload(large_store.get_all())
large_sizes = {}
for extension in ("json", "csv"):
    path = run / f"large-vocabulary.{extension}"
    large_controller.export_file(path)
    large_sizes[extension] = path.stat().st_size
    restored = HotwordStore(run / f"large-restored-{extension}.json")
    importer = HotwordsWindowController(restored)
    assert importer.import_file(path) == 10020
    assert hotword_export_payload(restored.get_all()) == large_expected
    assert hotword_export_payload(HotwordStore(restored._path).get_all()) == large_expected
assert large_sizes["json"] > 3 * 1024 * 1024
checks.append("10,020 real saved vocabulary entries export and reimport through JSON and CSV into fresh stores; all exported fields and reloaded state, priority and usage metadata match exactly")

invalid_large_path = run / "large-invalid.json"
invalid_large_payload = json.loads((run / "large-vocabulary.json").read_text(encoding="utf-8"))
invalid_large_payload["entries"][-1]["pinned"] = "yes"
invalid_large_path.write_text(json.dumps(invalid_large_payload, ensure_ascii=False), encoding="utf-8")
preserved_store = HotwordStore(run / "large-invalid-target.json")
preserved_store.upsert_manual("PreservedTerm", ["preserved term"], pinned=True)
preserved_before = preserved_store._path.read_bytes()
preserved_controller = HotwordsWindowController(preserved_store)
try:
    preserved_controller.import_file(invalid_large_path)
except ValueError:
    pass
else:
    raise AssertionError("Invalid final entry must prevent the entire large import")
assert preserved_store._path.read_bytes() == preserved_before
assert len(HotwordStore(preserved_store._path).get_all()) == 1
checks.append("An invalid final entry in a 10,020-entry JSON file is rejected before any change to the existing persisted store")
report = {"runtime": bundle or "source", "scope": "Real native controls and filesystem; actual vocabulary selector and replacement engine; no ASR accuracy claim",
          "checks": checks, "artifacts": artifacts, "large_roundtrip": {"entries": 10020, "export_bytes": large_sizes}}
report_path = destination / ("bundle-report.json" if bundle else "report.json")
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"REPORT {report_path}")
