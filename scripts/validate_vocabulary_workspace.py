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
from Foundation import NSDate, NSIndexSet, NSMakeSize, NSRunLoop

from speaktype.app import SpeakTypeApp
from speaktype.config import CONFIG_DIR, CUSTOM_DICT_FILE, load_custom_dictionary, save_custom_dictionary
from speaktype.hotwords import HotwordStore
from speaktype.hotwords_window import (
    EXPORT_SCHEMA, HotwordsWindowController, hotword_alias_conflicts, hotword_export_payload,
    hotword_window_rows, validate_hotword_import,
)
from speaktype.i18n import set_language


assert CONFIG_DIR.is_relative_to(root / "work"), "Use SPEAKTYPE_CONFIG_DIR under work"
if bundle:
    assert Path(sys.prefix).resolve().is_relative_to(Path(bundle).resolve())
    assert Path(sys.modules["speaktype.hotwords_window"].__file__).resolve().is_relative_to(Path(bundle).resolve())
destination = root / "work" / "vocabulary-validation"
destination.mkdir(parents=True, exist_ok=True)
save_custom_dictionary([])
store = HotwordStore(destination / f"hotwords-{uuid4().hex}.json")
AppKit.NSApplication.sharedApplication()
changes = []
controller = HotwordsWindowController(store, on_change=lambda: changes.append(store.get_all()))
set_language("zh")
report = {"runtime": bundle or "source", "scope": "Real AppKit controls, real persistent HotwordStore and real text replacement; no ASR claim", "checks": []}


def advance():
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))


def snapshot(name, active):
    advance()
    view = active.window.contentView()
    view.displayIfNeeded()
    representation = view.bitmapImageRepForCachingDisplayInRect_(view.bounds())
    view.cacheDisplayInRect_toBitmapImageRep_(view.bounds(), representation)
    data = representation.representationUsingType_properties_(AppKit.NSBitmapImageFileTypePNG, {})
    assert data.writeToFile_atomically_(str(destination / name), True)


controller.show()
advance()
assert controller.window.isVisible()
assert controller.window.contentView().frame().size == NSMakeSize(1120, 760)
assert controller.window.appearance() is None
assert isinstance(controller._sidebar, AppKit.NSView)
assert controller._sidebar.frame().size.width == 190
assert isinstance(controller._table, AppKit.NSTableView)
assert controller._table.headerView() is not None
controller.window.setAppearance_(AppKit.NSAppearance.appearanceNamed_(AppKit.NSAppearanceNameAqua))
assert controller._visible_rows == []
assert not controller._toggle_button.isEnabled() and not controller._delete_button.isEnabled()
snapshot("vocabulary-empty.png", controller)
controller._term_field.setStringValue_("Qwen3-ASR")
controller._aliases_view.setString_("千问三 ASR\nQwen three ASR\n\n")
controller._save_button.performClick_(None)
advance()
entry = store.get_all()[0]
assert entry["term"] == "Qwen3-ASR" and entry["aliases"] == ["千问三 ASR", "Qwen three ASR"]
assert entry["active"] and len(changes) == 1
assert HotwordStore(store._path).get_all() == store.get_all()
report["checks"].append("Native save button persists one standard spelling with multiple newline-separated aliases")
controller._test_input.setString_("今天使用千问三 ASR 和 Qwen three ASR。")
result = controller.test_text()
assert result.text == "今天使用Qwen3-ASR 和 Qwen3-ASR。" and len(result.changes) == 2
assert controller._test_output.string() == result.text
assert "千问三 ASR → Qwen3-ASR" in controller._changes_field.stringValue()
controller._toggle_button.performClick_(None)
assert not store.get_all()[0]["active"] and store.get_all()[0]["user_disabled"]
controller._filter_buttons["disabled"].performClick_(None)
assert [row["term"] for row in controller._visible_rows] == ["Qwen3-ASR"]
controller._toggle_button.performClick_(None)
assert store.get_all()[0]["active"]
controller._filter_buttons["active"].performClick_(None)
assert len(controller._visible_rows) == 1
assert len(changes) == 3
report["checks"].append("Actual replacement output and changes, enabled/disabled filters, persistent toggles and change callback")
controller._term_field.setStringValue_("Qwen3 ASR")
controller._app_field.setStringValue_("TextEdit")
controller._scene_picker.selectItemAtIndex_(3)
controller._save_button.performClick_(None)
assert len(store.get_all()) == 1 and store.get_all()[0]["term"] == "Qwen3 ASR"
assert store.get_all()[0]["scope_app"] == "TextEdit" and store.get_all()[0]["scope_scene"] == "code"
controller._test_input.setString_("千问三 ASR")
assert controller.test_text().text == "千问三 ASR"
controller._test_app_field.setStringValue_("TextEdit")
controller._test_scene_picker.selectItemAtIndex_(3)
assert controller.test_text().text == "Qwen3 ASR"
report["checks"].append("Editing renames an existing entry; actual application and scene scope constrain replacement")
controller.new_entry()
controller._term_field.setStringValue_("OmniEcho")
controller._aliases_view.setString_("Omni Echo\n奥米 Echo")
controller._save_button.performClick_(None)
store.add_or_reinforce("NeurIPS", aliases=["NIPS"], confidence=0.2)
controller.refresh()
assert len(hotword_window_rows(store.get_all(), filter_id="pending")) == 1
controller._filter_buttons["pending"].performClick_(None)
assert [row["term"] for row in controller._visible_rows] == ["NeurIPS"]
controller._filter_buttons["all"].performClick_(None)
controller._search_field.setStringValue_("奥米")
controller._render_rows()
assert [row["term"] for row in controller._visible_rows] == ["OmniEcho"]
controller._search_field.setStringValue_("没有匹配")
controller._render_rows()
assert not controller._visible_rows
controller._search_field.setStringValue_("")
controller._render_rows()
report["checks"].append("Pending learned-word review, alias search and meaningful no-match state")
table_index = next(index for index, row in enumerate(controller._visible_rows) if row["term"] == "OmniEcho")
controller._table.selectRowIndexes_byExtendingSelection_(NSIndexSet.indexSetWithIndex_(table_index), False)
advance()
assert controller._selected_term == "OmniEcho" and controller._term_field.stringValue() == "OmniEcho"
report["checks"].append("Native NSTableView selection opens the actual stored entry in the compact system-themed window")
controller.new_entry()
controller._term_field.setStringValue_("OmniEcho")
assert controller.save_entry() is False
assert "已经存在" in controller._copy_feedback_field.stringValue()
assert len(store.get_all()) == 3
controller._term_field.setStringValue_("Invalid")
controller._aliases_view.setString_("\n".join(str(index) for index in range(9)))
assert controller.save_entry() is False and len(store.get_all()) == 3
report["checks"].append("Invalid forms and duplicate terms show errors without changing the dictionary")
controller._term_field.selectText_(None)
field_editor = controller._term_field.currentEditor()
assert field_editor is not None
field_editor.insertText_replacementRange_("UnSavedProject", field_editor.selectedRange())
controller._aliases_view.setString_("Un Saved Project\n尚未保存项目")
controller._app_field.setStringValue_("TextEdit")
controller._scene_picker.selectItemAtIndex_(4)
advance()
assert "尚未保存" in controller._editor_title.stringValue()
controller.select_entry("OmniEcho")
controller._aliases_view.insertText_replacementRange_("\nOmni Eko", (len(controller._aliases_view.string()), 0))
advance()
assert "尚未保存" in controller._editor_title.stringValue()
controller.new_entry()
assert controller._term_field.stringValue() == "UnSavedProject"
assert controller._aliases_view.string() == "Un Saved Project\n尚未保存项目", (controller._aliases_view.string(), controller._drafts)
assert controller._app_field.stringValue() == "TextEdit" and controller._scene_picker.indexOfSelectedItem() == 4
controller.select_entry("OmniEcho")
assert "Omni Eko" in controller._aliases_view.string()
controller.refresh()
assert "Omni Eko" in controller._aliases_view.string()
controller.window.performClose_(None)
controller.show()
assert "Omni Eko" in controller._aliases_view.string() and controller.has_unsaved_changes()
controller._save_button.performClick_(None)
assert "Omni Eko" in next(entry for entry in store.get_all() if entry["term"] == "OmniEcho")["aliases"]
assert "OmniEcho" not in controller._drafts
controller.new_entry()
assert controller._term_field.stringValue() == "UnSavedProject"
controller._term_field.setStringValue_("")
controller._aliases_view.setString_("")
controller._app_field.setStringValue_("")
controller._scene_picker.selectItemAtIndex_(0)
controller._editor_changed()
assert not controller.has_unsaved_changes()
report["checks"].append("Real native text-edit notifications mark unsaved drafts; new and existing drafts survive switching, refresh, native close and reopen; save clears the matching draft")
export_path = destination / "exported-vocabulary.json"
controller.export_file(export_path)
payload = json.loads(export_path.read_text(encoding="utf-8"))
assert payload["schema"] == EXPORT_SCHEMA and len(validate_hotword_import(payload)) == 3
controller.select_entry("OmniEcho")
controller._delete_button.performClick_(None)
assert len(store.get_all()) == 2
assert controller.import_file(export_path) == 3 and len(store.get_all()) == 3
assert controller.import_file(export_path) == 3 and len(store.get_all()) == 3
pending = next(entry for entry in store.get_all() if entry["term"] == "NeurIPS")
assert not pending["active"] and not pending["user_disabled"] and pending["source"] == "post_edit"
assert pending["observations"] == 1 and pending["confidence"] == 0.2
invalid = destination / "invalid-vocabulary.json"
invalid.write_text(json.dumps({"schema": EXPORT_SCHEMA, "version": 1, "entries": [
    {"term": "First valid"}, {"term": "Invalid", "enabled": "false"},
]}), encoding="utf-8")
before = store._path.read_bytes()
try:
    controller.import_file(invalid)
except ValueError as error:
    assert "第 2 条" in str(error)
else:
    raise AssertionError("Invalid import must be rejected")
assert store._path.read_bytes() == before
report["checks"].append("Real JSON export, delete, import and update round trip; invalid later entry leaves saved file unchanged")
application = SpeakTypeApp()
application.hotwords = store
controller.on_test = application._apply_vocabulary_corrections
controller.test_status = application._vocabulary_test_status
controller._test_input.setString_("Omni Echo")
controller._test_app_field.setStringValue_("")
controller._test_scene_picker.selectItemAtIndex_(0)
application.config["hotword_context_enabled"] = False
assert controller.test_text().text == "Omni Echo"
assert "热词功能已关闭" in controller._test_status_field.stringValue()
application.config["hotword_context_enabled"] = True
application.config["hotword_auto_corrections_enabled"] = False
assert controller.test_text().text == "OmniEcho"
assert "仅应用手动添加或已确认" in controller._test_status_field.stringValue()
pending_backup = hotword_export_payload([pending])["entries"]
controller.select_entry("NeurIPS")
controller._toggle_button.performClick_(None)
confirmed = next(entry for entry in store.get_all() if entry["term"] == "NeurIPS")
assert confirmed["active"] and confirmed["user_confirmed"]
assert confirmed["source"] == "post_edit" and confirmed["confidence"] == 0.2
controller._test_input.setString_("NIPS")
assert controller.test_text().text == "NeurIPS"
store.import_manual(pending_backup)
controller.refresh()
assert not next(entry for entry in store.get_all() if entry["term"] == "NeurIPS")["user_confirmed"]
report["checks"].append("Test callback uses the real application's vocabulary settings; disabled vocabulary stays unchanged; explicitly enabling a low-confidence candidate approves aliases without changing learning confidence or source")
controller.new_entry()
controller._term_field.setStringValue_("OmniVoice")
controller._aliases_view.setString_("Omni Echo")
before_conflict = store.get_all()
assert controller.save_entry() is False
assert store.get_all() == before_conflict
assert "Omni Echo" in controller._copy_feedback_field.stringValue()
assert "OmniEcho" in controller._copy_feedback_field.stringValue() and "OmniVoice" in controller._copy_feedback_field.stringValue()
assert controller._term_field.stringValue() == "OmniVoice" and controller.has_unsaved_changes()
controller._term_field.setStringValue_("")
controller._aliases_view.setString_("")
controller._editor_changed()
store.upsert_manual("OmniVoice", ["Omni Echo"])
controller.refresh()
controller._test_input.setString_("Omni Echo")
assert controller.test_text().text == "OmniEcho"
assert "OmniEcho" in controller._changes_field.stringValue() and "OmniVoice" in controller._changes_field.stringValue()
store.remove("OmniVoice")
store.upsert_manual("LegacyAlpha", ["Shared Echo"])
store.upsert_manual("LegacyBeta", ["Shared Echo"])
controller.refresh()
controller._test_input.setString_("Shared Echo")
assert controller.test_text().text == "Shared Echo"
assert "LegacyAlpha" in controller._changes_field.stringValue() and "LegacyBeta" in controller._changes_field.stringValue()
store.remove("LegacyAlpha")
store.remove("LegacyBeta")
store.upsert_manual("ScopedAlpha", ["Scoped name"], scope_app="Application Alpha")
store.upsert_manual("ScopedBeta", ["Scoped name"], scope_app="Application Beta")
assert not any("ScopedAlpha" in conflict["terms"] for conflict in hotword_alias_conflicts(store.get_all()))
store.upsert_manual("ScopedAlpha", ["Scoped name"], scope_scene="chat")
store.upsert_manual("ScopedBeta", ["Scoped name"], scope_scene="code")
assert not any("ScopedAlpha" in conflict["terms"] for conflict in hotword_alias_conflicts(store.get_all()))
actual_app = next(app for app in AppKit.NSWorkspace.sharedWorkspace().runningApplications()
                  if app.localizedName() and app.bundleIdentifier() and app.activationPolicy() == AppKit.NSApplicationActivationPolicyRegular)
store.upsert_manual("ScopedAlpha", ["Scoped name"], scope_app=str(actual_app.localizedName()))
store.upsert_manual("ScopedBeta", ["Scoped name"], scope_app=str(actual_app.bundleIdentifier()))
assert any(set(conflict["terms"]) == {"ScopedAlpha", "ScopedBeta"} for conflict in hotword_alias_conflicts(store.get_all()))
store.remove("ScopedAlpha")
store.remove("ScopedBeta")
controller.refresh()
report["checks"].append("Alias conflicts reject form saves while preserving drafts, identify existing conflicting targets during tests, preserve ambiguous text, allow exclusive scopes, and resolve actual running application names and bundle IDs")
store.import_manual([{"term": "PartialApproval", "aliases": ["Approved Alias", "Observed Alias"],
                      "enabled": True, "state": "active", "source": "post_edit", "confidence": 0.9,
                      "observations": 3, "user_confirmed": True, "approved_aliases": ["Approved Alias"],
                      "alias_confidences": {"Approved Alias": 0.95, "Observed Alias": 0.2}}])
controller.refresh()
approval_export = destination / "alias-approval-vocabulary.json"
controller.export_file(approval_export)
approval_payload = json.loads(approval_export.read_text(encoding="utf-8"))
approval_entries = validate_hotword_import(approval_payload)
partial_export = next(entry for entry in approval_entries if entry["term"] == "PartialApproval")
assert partial_export["approved_aliases"] == ["Approved Alias"]
assert partial_export["alias_confidences"] == {"Approved Alias": 0.95, "Observed Alias": 0.2}
controller.import_file(approval_export)
partial = next(entry for entry in store.get_all() if entry["term"] == "PartialApproval")
assert partial["approved_aliases"] == ["Approved Alias"]
assert partial["alias_confidences"] == partial_export["alias_confidences"]
controller._test_input.setString_("Approved Alias + Observed Alias")
controller._test_app_field.setStringValue_("")
controller._test_scene_picker.selectItemAtIndex_(0)
assert controller.test_text().text == "PartialApproval + Observed Alias"
for index, metadata in enumerate((
    {"approved_aliases": ["Missing Alias"]},
    {"approved_aliases": ["Safe Alias", "Safe Alias"]},
    {"alias_confidences": {"Missing Alias": 0.9}},
    {"alias_confidences": {"Safe Alias": True}},
    {"alias_confidences": {"Safe Alias": float("inf")}},
    {"state": "pending", "enabled": False, "source": "post_edit", "approved_aliases": ["Safe Alias"]},
)):
    invalid_metadata = destination / f"invalid-alias-metadata-{index}.json"
    invalid_metadata.write_text(json.dumps({"schema": EXPORT_SCHEMA, "version": 1, "entries": [
        {"term": "MetadataCheck", "aliases": ["Safe Alias"], **metadata},
    ]}), encoding="utf-8")
    before = store._path.read_bytes()
    try:
        controller.import_file(invalid_metadata)
    except ValueError as error:
        assert str(error)
    else:
        raise AssertionError("Invalid alias metadata must be rejected")
    assert store._path.read_bytes() == before
controller.select_entry("PartialApproval")
controller._delete_button.performClick_(None)
report["checks"].append("Real JSON export/import preserves per-alias approval and confidence without approving an observed alias; invalid alias metadata and pending approvals leave the persistent file unchanged")
legacy_words = ["LegacyPause", "LegacyDelete", "LegacyEdit", "LegacyRename", "LegacyCanonical"]
save_custom_dictionary(legacy_words)
legacy_bytes = CUSTOM_DICT_FILE.read_bytes()
controller.refresh()
assert set(legacy_words).issubset({row["term"] for row in controller._visible_rows})
assert all(next(entry for entry in controller._last_entries if entry["term"] == term)["source"] == "dictionary" for term in legacy_words)
table_index = next(index for index, row in enumerate(controller._visible_rows) if row["term"] == "LegacyPause")
controller._table.selectRowIndexes_byExtendingSelection_(NSIndexSet.indexSetWithIndex_(table_index), False)
advance()
assert controller._selected_term == "LegacyPause" and controller._entry_meta_field.stringValue() == "原有词典"
controller._toggle_button.performClick_(None)
advance()
paused = next(entry for entry in controller._last_entries if entry["term"] == "LegacyPause")
assert paused["user_disabled"] and not paused["active"]
assert "LegacyPause" not in HotwordStore(store._path).active_context(dictionary=load_custom_dictionary()).terms
assert store.apply("legacypause", dictionary=load_custom_dictionary()).text == "legacypause"
controller._toggle_button.performClick_(None)
assert "LegacyPause" in HotwordStore(store._path).active_context(dictionary=load_custom_dictionary()).terms
assert store.apply("legacypause", dictionary=load_custom_dictionary()).text == "LegacyPause"
controller._toggle_button.performClick_(None)
controller.select_entry("LegacyDelete")
controller._delete_button.performClick_(None)
assert "LegacyDelete" not in {entry["term"] for entry in controller._last_entries}
reloaded_store = HotwordStore(store._path)
assert "LegacyDelete" not in reloaded_store.active_context(dictionary=load_custom_dictionary()).terms
assert reloaded_store.apply("legacydelete", dictionary=load_custom_dictionary()).text == "legacydelete"
reopened = HotwordsWindowController(reloaded_store)
reopened.show()
advance()
assert "LegacyDelete" not in {row["term"] for row in reopened._visible_rows}
assert not next(entry for entry in reopened._last_entries if entry["term"] == "LegacyPause")["active"]
reopened.close()
controller.select_entry("LegacyEdit")
controller._aliases_view.setString_("Legacy Edit\nLegacy Eddit")
controller._app_field.setStringValue_("TextEdit")
controller._scene_picker.selectItemAtIndex_(3)
controller._save_button.performClick_(None)
edited_legacy = next(entry for entry in store.get_all() if entry["term"] == "LegacyEdit")
assert edited_legacy["aliases"] == ["Legacy Edit", "Legacy Eddit"]
assert edited_legacy["scope_app"] == "TextEdit" and edited_legacy["scope_scene"] == "code"
assert edited_legacy["source"] == "manual"
controller.refresh()
assert controller._aliases_view.string() == "Legacy Edit\nLegacy Eddit"
assert controller._app_field.stringValue() == "TextEdit" and controller._scene_picker.indexOfSelectedItem() == 3
controller.select_entry("LegacyRename")
controller._term_field.setStringValue_("LegacyRenamed")
controller._aliases_view.setString_("Legacy Rename")
controller._save_button.performClick_(None)
assert controller._selected_term == "LegacyRenamed"
merged_names = {entry["term"] for entry in HotwordStore(store._path).get_all(dictionary=load_custom_dictionary())}
assert "LegacyRename" not in merged_names and "LegacyRenamed" in merged_names
context_names = HotwordStore(store._path).active_context(dictionary=load_custom_dictionary()).terms
assert "LegacyRename" not in context_names and "LegacyRenamed" in context_names
assert CUSTOM_DICT_FILE.read_bytes() == legacy_bytes
report["checks"].append("Real legacy dictionary file appears in the native list with its source; pause, enable, delete, edit and rename persist overrides, preserve aliases/scopes, and suppress old recognition terms across a new store and window without changing the legacy file")
controller.new_entry()
controller._term_field.setStringValue_("LegacyReplacement")
controller._aliases_view.setString_("LegacyCanonical")
before_legacy_conflict = store._path.read_bytes()
assert controller.save_entry() is False
assert store._path.read_bytes() == before_legacy_conflict
assert "LegacyCanonical" in controller._copy_feedback_field.stringValue()
assert "LegacyReplacement" in controller._copy_feedback_field.stringValue()
controller._term_field.setStringValue_("LegacyCanonical")
controller._aliases_view.setString_("")
assert controller.save_entry() is False
assert "已经存在" in controller._copy_feedback_field.stringValue()
store.upsert_manual("LegacyConflict", ["LegacyCanonical"], enabled=False)
controller.refresh()
controller.select_entry("LegacyConflict")
before_legacy_conflict = store._path.read_bytes()
controller._toggle_button.performClick_(None)
assert store._path.read_bytes() == before_legacy_conflict
assert not next(entry for entry in store.get_all() if entry["term"] == "LegacyConflict")["active"]
assert "LegacyCanonical" in controller._copy_feedback_field.stringValue()
store.set_active("LegacyConflict", True)
controller.refresh()
controller._test_input.setString_("LegacyCanonical")
controller._test_app_field.setStringValue_("")
controller._test_scene_picker.selectItemAtIndex_(0)
assert controller.test_text().text == "LegacyCanonical"
assert "LegacyCanonical" in controller._changes_field.stringValue() and "LegacyConflict" in controller._changes_field.stringValue()
controller.select_entry("LegacyConflict")
controller._delete_button.performClick_(None)
assert CUSTOM_DICT_FILE.read_bytes() == legacy_bytes
report["checks"].append("Legacy standard spellings participate in duplicate checks, alias-conflict save rejection, enable rejection and the actual replacement-test warning without changing canonical output")
legacy_export = destination / "legacy-exported-vocabulary.json"
controller.export_file(legacy_export)
legacy_payload = json.loads(legacy_export.read_text(encoding="utf-8"))
legacy_exported = validate_hotword_import(legacy_payload)
assert any(entry["term"] == "LegacyCanonical" and entry["source"] == "manual" for entry in legacy_exported)
assert controller.import_file(legacy_export) == len(legacy_exported)
assert "LegacyDelete" not in {entry["term"] for entry in controller._last_entries}
assert "LegacyRename" not in {entry["term"] for entry in controller._last_entries}
assert not next(entry for entry in controller._last_entries if entry["term"] == "LegacyPause")["active"]
assert CUSTOM_DICT_FILE.read_bytes() == legacy_bytes
application._open_dict(None)
legacy_editor = application._dict_controller
advance()
legacy_editor._word_field.setStringValue_("LegacyFromEditor")
legacy_editor._add_word()
legacy_editor._do_save()
advance()
assert set(load_custom_dictionary()) == set(legacy_words + ["LegacyFromEditor"])
controller.refresh()
assert next(entry for entry in controller._last_entries if entry["term"] == "LegacyFromEditor")["source"] == "dictionary"
assert "LegacyDelete" not in {entry["term"] for entry in controller._last_entries}
assert "LegacyRename" not in {entry["term"] for entry in controller._last_entries}
assert not next(entry for entry in controller._last_entries if entry["term"] == "LegacyPause")["active"]
report["checks"].append("Merged vocabulary exports and imports through real JSON files; the real original dictionary editor still saves its file, refresh discovers its new words, and stored overrides retain priority")
controller.select_entry("OmniEcho")
controller._test_input.setString_("Omni Echo 和 奥米 Echo 的研究进展。")
controller._test_app_field.setStringValue_("")
controller._test_scene_picker.selectItemAtIndex_(0)
controller.test_text()
snapshot("vocabulary-zh.png", controller)
controller.window.setAppearance_(AppKit.NSAppearance.appearanceNamed_(AppKit.NSAppearanceNameDarkAqua))
controller.window.contentView().setNeedsDisplay_(True)
snapshot("vocabulary-zh-dark.png", controller)
assert controller.window.effectiveAppearance().bestMatchFromAppearancesWithNames_([AppKit.NSAppearanceNameAqua, AppKit.NSAppearanceNameDarkAqua]) == AppKit.NSAppearanceNameDarkAqua
identity = controller.window.windowNumber()
controller.close()
controller.show()
assert controller.window.windowNumber() == identity
controller.close()
set_language("en")
english = HotwordsWindowController(store)
english.show()
assert english.window.appearance() is None
english.select_entry("LegacyFromEditor")
assert english._entry_meta_field.stringValue() == "Existing dictionary"
english.window.setAppearance_(AppKit.NSAppearance.appearanceNamed_(AppKit.NSAppearanceNameAqua))
english.select_entry("OmniEcho")
english._test_input.setString_("Omni Echo works with Qwen three ASR.")
english.test_text()
snapshot("vocabulary-en.png", english)
english.window.setAppearance_(AppKit.NSAppearance.appearanceNamed_(AppKit.NSAppearanceNameDarkAqua))
english.window.contentView().setNeedsDisplay_(True)
snapshot("vocabulary-en-dark.png", english)
assert english._save_button.title() == "Save word"
assert english._editor_title.stringValue() == "Edit word"
english.close()
report["checks"].append("Real native rendering in Chinese and English in Aqua and Dark Aqua, no forced application theme, material sidebar, window reuse, editable and selectable text controls")
report["callback_count"] = len(changes)
report["artifacts"] = [str(destination / name) for name in ("vocabulary-empty.png", "vocabulary-zh.png", "vocabulary-zh-dark.png", "vocabulary-en.png", "vocabulary-en-dark.png")]
report_path = destination / ("bundle-report.json" if bundle else "report.json")
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"REPORT {report_path}")
