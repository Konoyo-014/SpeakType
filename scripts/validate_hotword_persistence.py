import argparse
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--report", type=Path)
args = parser.parse_args()
run_dir = root / "work" / f"hotword-persistence-{uuid4().hex[:10]}"
run_dir.mkdir(parents=True)
os.environ["SPEAKTYPE_CONFIG_DIR"] = str(run_dir / "config")
bundle = os.environ.get("SPEAKTYPE_TEST_BUNDLE")
if not bundle:
    sys.path.insert(0, str(root))

from speaktype.config import write_json_file
from speaktype.corrections import CorrectionStore
from speaktype.hotwords import HotwordStore

if bundle:
    assert Path(sys.prefix).resolve().is_relative_to(Path(bundle).resolve())
    assert Path(sys.modules["speaktype.hotwords"].__file__).resolve().is_relative_to(Path(bundle).resolve())

report = {"runtime": bundle or "source", "run_dir": str(run_dir),
          "scope": "Real files and permission-denied writes; real store operations with explicitly supplied text; no ASR claim",
          "write_failures": [], "checks": []}


def verify_failed_write(name, action):
    directory = run_dir / name
    directory.mkdir()
    store = HotwordStore(directory / "hotwords.json")
    store.upsert_manual("OriginalProject", ["original project"])
    dictionary = ["LegacyProject"]
    before = store.get_all(include_deleted=True)
    before_visible = store.get_all(dictionary=dictionary)
    before_bytes = store._path.read_bytes()
    directory.chmod(0o500)
    caught = None
    try:
        action(store, dictionary)
    except OSError as error:
        caught = {"type": type(error).__name__, "message": str(error)}
    finally:
        directory.chmod(0o700)
    assert caught is not None, "Actual filesystem permissions must reject the write"
    assert store._path.read_bytes() == before_bytes, name
    assert store.get_all(include_deleted=True) == before, name
    assert store.get_all(dictionary=dictionary) == before_visible, name
    assert HotwordStore(store._path).get_all(include_deleted=True) == before, name
    report["write_failures"].append({"name": name, "error": caught,
                                     "memory_and_saved_file_unchanged": True})


for name, action in (
    ("new_word", lambda store, words: store.upsert_manual("NewProject", ["new project"])),
    ("edit_word", lambda store, words: store.upsert_manual("OriginalProject", ["new spelling"])),
    ("rename_word", lambda store, words: store.upsert_manual("RenamedProject", original_term="OriginalProject")),
    ("toggle_word", lambda store, words: store.set_active("OriginalProject", False)),
    ("delete_word", lambda store, words: store.remove("OriginalProject")),
    ("learn_new_word", lambda store, words: store.add_or_reinforce("LearnedProject", ["learned project"], confidence=0.95)),
    ("learn_existing_word", lambda store, words: store.add_or_reinforce("OriginalProject", ["learned alias"], confidence=0.2)),
    ("import_words", lambda store, words: store.import_manual([{"term": "ImportedProject"}])),
    ("legacy_rename", lambda store, words: store.upsert_manual("RenamedLegacy", original_term="LegacyProject", dictionary=words)),
    ("legacy_toggle", lambda store, words: store.set_active("LegacyProject", False, dictionary=words)),
    ("legacy_delete", lambda store, words: store.remove("LegacyProject", dictionary=words)),
):
    verify_failed_write(name, action)

for name, action in (
    ("correction_add", lambda store: store.add("new phrase", "NewProject")),
    ("correction_remove", lambda store: store.remove("original project")),
    ("correction_clear", lambda store: store.clear()),
    ("correction_replace", lambda store: store.replace_all([{"wrong": "new phrase", "right": "NewProject"}])),
):
    directory = run_dir / name
    directory.mkdir()
    store = CorrectionStore(directory / "corrections.json")
    store.add("original project", "OriginalProject")
    before = store.get_all()
    before_bytes = store._path.read_bytes()
    before_result = store.apply_with_changes("Use original project and new phrase.")
    directory.chmod(0o500)
    caught = None
    try:
        action(store)
    except OSError as error:
        caught = {"type": type(error).__name__, "message": str(error)}
    finally:
        directory.chmod(0o700)
    assert caught is not None
    assert store._path.read_bytes() == before_bytes and store.get_all() == before
    assert store.apply_with_changes("Use original project and new phrase.") == before_result
    assert CorrectionStore(store._path).get_all() == before
    report["write_failures"].append({"name": name, "error": caught,
                                     "memory_saved_file_and_compiled_rules_unchanged": True})

replacement = HotwordStore(run_dir / "replace-failure.json")
replacement.upsert_manual("OriginalProject", ["original project"])
before = replacement.get_all(include_deleted=True)
backup = run_dir / "replace-failure-saved.json"
replacement._path.rename(backup)
replacement._path.mkdir()
replace_error = None
try:
    replacement.upsert_manual("NewProject", ["new project"])
except OSError as error:
    replace_error = {"type": type(error).__name__, "message": str(error)}
finally:
    replacement._path.rmdir()
    backup.rename(replacement._path)
assert replace_error is not None and replacement.get_all(include_deleted=True) == before
assert HotwordStore(replacement._path).get_all(include_deleted=True) == before
assert not list(run_dir.glob(".replace-failure.json.*.tmp"))
report["write_failures"].append({"name": "atomic_replace_failure_after_temporary_write", "error": replace_error,
                                 "memory_and_saved_file_unchanged": True})

deleted = HotwordStore(run_dir / "deleted.json")
deleted.add_or_reinforce("OmniEcho", ["omni echo"], confidence=0.95,
                         raw_fragment="omni echo", edited_fragment="OmniEcho")
assert deleted.remove("OmniEcho")
assert deleted.get_all() == [] and len(deleted) == 0
marker = deleted.get_all(include_deleted=True)[0]
assert marker["user_deleted"] and marker["user_disabled"] and not marker["active"]
assert marker["aliases"] == [] and marker["approved_aliases"] == [] and marker["alias_confidences"] == {}
assert marker["evidence"] == [] and marker["observations"] == 0 and marker["apps"] == {}
before = deleted._path.read_bytes()
assert deleted.add_or_reinforce("OmniEcho", ["omni echo"], confidence=0.99) is None
assert deleted._path.read_bytes() == before
assert deleted.learn_from_payload({"learn": True, "hotwords": [{"term": "OmniEcho", "confidence": 0.99}]}, edited_text="OmniEcho") == []
assert deleted.active_context(dictionary=["OmniEcho"]).terms == []
assert deleted.get_all(dictionary=["OmniEcho"]) == []
assert not deleted.set_active("OmniEcho", True)
assert HotwordStore(deleted._path).get_all() == []
restored = deleted.upsert_manual("OmniEcho", ["omni echo"])
assert not restored["user_deleted"] and restored["observations"] == 0
assert deleted.apply("omni echo", learned_corrections_enabled=False).text == "OmniEcho"
deleted.remove("OmniEcho")
assert deleted.import_manual([{"term": "OmniEcho", "aliases": ["omni echo"]}]) == 1
assert not deleted.get_all()[0]["user_deleted"] and deleted.get_all()[0]["observations"] == 0
deleted.remove("OmniEcho")
assert deleted.import_manual([{"term": "OmniEcho", "aliases": ["omni echo"], "state": "pending"}]) == 1
candidate = deleted.get_all()[0]
assert candidate["source"] == "imported" and candidate["confidence"] == 0.5 and candidate["observations"] == 0
assert candidate["approved_aliases"] == [] and candidate["alias_confidences"] == {"omni echo": 0.5}
report["checks"].append("Deletion stores only a hidden marker, removes learning content, blocks late learning and legacy reappearance, and allows explicit manual or import restoration")

legacy = HotwordStore(run_dir / "legacy.json")
dictionary = ["LegacyProject", "OtherProject", " legacyproject "]
merged = legacy.get_all(dictionary=dictionary)
assert len(merged) == 2 and all(entry["source"] == "dictionary" for entry in merged)
assert legacy.get_all() == []
assert legacy.set_active("LegacyProject", False, dictionary=dictionary)
assert legacy.active_context(dictionary=dictionary).terms == ["OtherProject"]
assert not next(entry for entry in legacy.get_all(dictionary=dictionary) if entry["term"] == "LegacyProject")["active"]
assert legacy.set_active("LegacyProject", True, dictionary=dictionary)
legacy.upsert_manual("RenamedLegacy", ["legacy spelling"], original_term="LegacyProject", dictionary=dictionary)
assert {entry["term"] for entry in legacy.get_all(dictionary=dictionary)} == {"RenamedLegacy", "OtherProject"}
assert "LegacyProject" not in legacy.active_context(dictionary=dictionary).terms
assert legacy.remove("OtherProject", dictionary=dictionary)
assert {entry["term"] for entry in legacy.get_all(dictionary=dictionary)} == {"RenamedLegacy"}
reloaded = HotwordStore(legacy._path)
assert reloaded.get_all(dictionary=dictionary) == legacy.get_all(dictionary=dictionary)
assert reloaded.add_or_reinforce("LegacyProject", confidence=0.99) is None
assert reloaded.add_or_reinforce("OtherProject", confidence=0.99) is None
report["checks"].append("Legacy words appear as complete manageable entries; one-commit pause, enable, rename and delete retain their meaning after reload and suppress the original legacy name")

manual = HotwordStore(run_dir / "per-alias.json")
manual.upsert_manual("ManualProject", ["manual spelling"])
learned = manual.add_or_reinforce("ManualProject", ["new automatic spelling"], confidence=0.2)
assert learned["source"] == "manual" and learned["confidence"] == 1.0
assert learned["approved_aliases"] == ["manual spelling"]
assert learned["alias_confidences"]["new automatic spelling"] == 0.2
assert manual.apply("manual spelling", learned_corrections_enabled=False).text == "ManualProject"
assert manual.apply("new automatic spelling", learned_corrections_enabled=False).text == "new automatic spelling"
assert manual.apply("new automatic spelling", learned_corrections_enabled=True).text == "new automatic spelling"
manual.add_or_reinforce("ManualProject", ["new automatic spelling"], confidence=0.95)
assert manual.apply("new automatic spelling", learned_corrections_enabled=True).text == "ManualProject"
assert manual.apply("new automatic spelling", learned_corrections_enabled=False).text == "new automatic spelling"
manual.add_or_reinforce("ManualProject", ["weak automatic spelling"], confidence=0.1)
assert manual.set_active("ManualProject", True)
confirmed = manual.get_all()[0]
assert confirmed["alias_confidences"]["weak automatic spelling"] == 0.1
assert set(confirmed["approved_aliases"]) == set(confirmed["aliases"])
assert manual.apply("weak automatic spelling", learned_corrections_enabled=False).text == "ManualProject"
assert HotwordStore(manual._path).get_all() == manual.get_all()
report["checks"].append("New automatic aliases have independent confidence and approval; manual spelling still works with learned corrections disabled; explicit enable approves current aliases without rewriting confidence")

old_path = run_dir / "old-format.json"
write_json_file(old_path, [
    {"term": "OldManual", "aliases": ["old manual spelling"], "source": "manual", "active": True, "confidence": 1.0},
    {"term": "OldConfirmed", "aliases": ["old confirmed spelling"], "source": "post_edit", "active": True, "confidence": 0.3, "user_confirmed": True},
    {"term": "OldLearned", "aliases": ["old learned spelling"], "source": "post_edit", "active": True, "confidence": 0.95},
])
old = HotwordStore(old_path)
assert old.apply("old manual spelling", learned_corrections_enabled=False).text == "OldManual"
assert old.apply("old confirmed spelling", learned_corrections_enabled=False).text == "OldConfirmed"
assert old.apply("old learned spelling", learned_corrections_enabled=False).text == "old learned spelling"
assert old.apply("old learned spelling", learned_corrections_enabled=True).text == "OldLearned"
transfer = HotwordStore(run_dir / "transfer.json")
entry = manual.get_all()[0]
export_entry = {key: entry[key] for key in ("term", "aliases", "source", "confidence", "observations", "user_confirmed", "approved_aliases", "alias_confidences")}
export_entry.update(state="active", enabled=True)
assert transfer.import_manual([export_entry]) == 1
for key in export_entry:
    if key not in ("state", "enabled"):
        assert transfer.get_all()[0][key] == export_entry[key], key
assert transfer.apply("weak automatic spelling", learned_corrections_enabled=False).text == "ManualProject"
report["checks"].append("Old manual and explicitly confirmed JSON aliases migrate as approved, old automatic aliases remain conditional, and import preserves per-alias metadata")

before = transfer.get_all(include_deleted=True)
before_bytes = transfer._path.read_bytes()
for invalid in (
    {"term": "InvalidProject", "approved_aliases": False},
    {"term": "InvalidProject", "aliases": ["valid alias"], "approved_aliases": ["unknown alias"]},
    {"term": "InvalidProject", "aliases": ["valid alias"], "alias_confidences": {"unknown alias": 0.9}},
    {"term": "InvalidProject", "aliases": ["valid alias"], "alias_confidences": {"valid alias": True}},
    {"term": "InvalidProject", "aliases": ["valid alias"], "alias_confidences": {"valid alias": float("nan")}},
    {"term": "InvalidProject", "aliases": ["valid alias"], "state": "pending", "approved_aliases": ["valid alias"]},
):
    rejected = False
    try:
        transfer.import_manual([{"term": "FirstValidProject"}, invalid])
    except (ValueError, TypeError):
        rejected = True
    assert rejected and transfer.get_all(include_deleted=True) == before
    assert transfer._path.read_bytes() == before_bytes
report["checks"].append("Invalid approval/confidence metadata rejects the whole import before changing memory or the saved file")

destination = args.report or run_dir / "report.json"
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"REPORT {destination}")
