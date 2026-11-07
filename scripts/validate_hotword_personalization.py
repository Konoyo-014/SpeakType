import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest import TestCase
from uuid import uuid4

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--asr", action="store_true")
parser.add_argument("--report", type=Path)
args = parser.parse_args()
run_dir = root / "work" / f"hotword-personalization-{uuid4().hex[:10]}"
run_dir.mkdir(parents=True)
os.environ["SPEAKTYPE_CONFIG_DIR"] = str(run_dir / "config")
bundle = os.environ.get("SPEAKTYPE_TEST_BUNDLE")
if not bundle:
    sys.path.insert(0, str(root))

from speaktype.hotwords import HotwordStore, _compiled_replacements

if bundle:
    assert Path(sys.prefix).resolve().is_relative_to(Path(bundle).resolve())
    assert Path(sys.modules["speaktype.hotwords"].__file__).resolve().is_relative_to(Path(bundle).resolve())

report = {"runtime": bundle or "source", "run_dir": str(run_dir), "cases": [], "asr": []}
code_app = {"name": "Codex", "bundle_id": "com.openai.codex"}
mail_app = {"name": "Mail", "bundle_id": "com.apple.mail"}
store = HotwordStore(run_dir / "personal.json")
store.upsert_manual("SpeakType", ["speak type"])
store.upsert_manual("PyObjC", ["pie object see"], scope_app="com.openai.codex")
store.upsert_manual("OmniEcho", pinned=True)
context = store.active_context(app_info=code_app, limit=1)
assert context.terms == ["OmniEcho"]
assert context.eligible_count == 3 and len(context.omitted_terms) == 2
assert context.selection_reasons == {"OmniEcho": "pinned"}
assert store.active_context(app_info=mail_app).eligible_count == 2
store.upsert_manual("OmniEcho", ["omni echo"])
assert next(entry for entry in store.get_all() if entry["term"] == "OmniEcho")["pinned"]
store.import_manual([{"term": "OmniEcho", "aliases": ["omni echo"]}])
assert next(entry for entry in store.get_all() if entry["term"] == "OmniEcho")["pinned"]
store.set_active("OmniEcho", False)
assert "OmniEcho" not in store.active_context(app_info=code_app).terms
assert "OmniEcho" not in store.record_usage("OmniEcho", app_info=code_app)
store.set_active("OmniEcho", True)
store.upsert_manual("OmniEcho", ["omni echo"], pinned=False)
report["cases"].append({"name": "priority_pause_scopes_and_selection_explanation", "passed": True})

assert store.record_usage("使用SpeakType和SpeakType；PyObjC。", app_info=code_app, scene="code", language="zh") == ["SpeakType", "PyObjC"]
assert store.record_usage("SpeakTypes pyobjctools omni echo", app_info=code_app) == []
assert store.record_usage("PyObjC", app_info=mail_app) == []
entry = next(item for item in store.get_all() if item["term"] == "SpeakType")
assert entry["usage_count"] == 1 and entry["observations"] == 0
assert entry["usage_apps"] == {"com.openai.codex": 1}
assert datetime.fromisoformat(entry["last_used_at"]).tzinfo is not None
store.upsert_manual("Qwen3")
store.upsert_manual("Qwen3-ASR")
assert store.record_usage("Qwen3-ASR") == ["Qwen3-ASR"]
assert next(item for item in store.get_all() if item["term"] == "Qwen3")["usage_count"] == 0
assert store.record_usage("NumPy", dictionary=["NumPy"]) == ["NumPy"]
legacy = next(item for item in store.get_all() if item["term"] == "NumPy")
assert legacy["source"] == "dictionary" and legacy["usage_count"] == 1
assert HotwordStore(store._path).get_all() == store.get_all()
report["cases"].append({"name": "actual_text_usage_once_per_dictation_boundaries_and_legacy", "passed": True})

ranking = HotwordStore(run_dir / "ranking.json")
ranking.upsert_manual("ProjectAlpha")
ranking.upsert_manual("ProjectBeta")
for _ in range(5):
    ranking.record_usage("ProjectAlpha", app_info=code_app)
    ranking.record_usage("ProjectBeta", app_info=mail_app)
assert ranking.active_context(app_info=code_app, limit=1).terms == ["ProjectAlpha"]
assert ranking.active_context(app_info=mail_app, limit=1).terms == ["ProjectBeta"]
assert ranking.active_context(app_info=code_app).selection_reasons["ProjectAlpha"] == "app_usage"
with ThreadPoolExecutor(max_workers=6) as executor:
    assert all(executor.map(lambda _: ranking.record_usage("ProjectAlpha", app_info=code_app), range(24)))
entry = next(item for item in ranking.get_all() if item["term"] == "ProjectAlpha")
assert entry["usage_count"] == 29
assert HotwordStore(ranking._path).get_all() == ranking.get_all()
report["cases"].append({"name": "application_usage_ranking_and_concurrent_persistence", "passed": True})

snapshot = store.get_all()
for payload in (
    {"term": "BadTerm", "pinned": "true"},
    {"term": "BadTerm", "usage_count": True},
    {"term": "BadTerm", "usage_count": -1},
    {"term": "BadTerm", "last_used_at": "yesterday"},
    {"term": "BadTerm", "last_used_at": "2026-11-07T00:00:00"},
    {"term": "BadTerm", "usage_apps": {"Codex": -1}},
):
    with TestCase().assertRaises((TypeError, ValueError)):
        store.import_manual([{"term": "ValidTerm"}, payload])
    assert store.get_all() == snapshot
    assert HotwordStore(store._path).get_all() == snapshot
transfer = HotwordStore(run_dir / "transfer.json")
transfer.import_manual([{
    "term": entry["term"], "aliases": entry["aliases"], "pinned": entry["pinned"],
    "usage_count": entry["usage_count"], "last_used_at": entry["last_used_at"],
    "usage_apps": entry["usage_apps"], "enabled": entry["active"],
} for entry in snapshot])
for original in snapshot:
    restored = next(entry for entry in transfer.get_all() if entry["term"] == original["term"])
    for key in ("pinned", "usage_count", "last_used_at", "usage_apps"):
        assert original[key] == restored[key], key
report["cases"].append({"name": "strict_atomic_import_and_usage_round_trip", "passed": True})
transfer.import_manual([{"term": "ZuluDate", "last_used_at": "2026-11-07T05:00:00Z"}])
assert next(entry for entry in transfer.get_all() if entry["term"] == "ZuluDate")["last_used_at"] == "2026-11-07T05:00:00+00:00"

directory = run_dir / "denied"
directory.mkdir()
denied = HotwordStore(directory / "hotwords.json")
denied.upsert_manual("OriginalTerm")
before = denied.get_all()
before_bytes = denied._path.read_bytes()
directory.chmod(0o500)
try:
    with TestCase().assertRaises(OSError):
        denied.record_usage("OriginalTerm")
finally:
    directory.chmod(0o700)
assert denied.get_all() == before and denied._path.read_bytes() == before_bytes
report["cases"].append({"name": "usage_write_failure_preserves_memory_and_file", "passed": True})

matching = HotwordStore(run_dir / "matching.json")
matching.upsert_manual("Qwen3-ASR", ["cute three asr"])
matching.upsert_manual("Qwen3", ["cute three"])
matching.upsert_manual("SpeakType", ["speak type"])
matching.upsert_manual("SciPy")
matching.upsert_manual("Keras")
matching.upsert_manual("Mistral")
matching.upsert_manual("TensorFlow", ["shared alias"])
matching.upsert_manual("PyTorch", ["shared alias"])
for original, expected in (
    ("用qwen3 \t- ASR和cute\tthree\nasr。", "用Qwen3-ASR和Qwen3-ASR。"),
    ("speak\n\ttype", "SpeakType"),
    ("qwen3_asr_extra; speak types", "qwen3_asr_extra; speak types"),
    ("shared\talias", "shared\talias"),
    ("ſciPy Keras Mıstral MİSTRAL", "SciPy Keras Mistral Mistral"),
):
    assert matching.apply(original).text == expected, (original, matching.apply(original))
assert set(matching.record_usage("ſciPy Keras Mıstral")) == {"SciPy", "Keras", "Mistral"}
report["cases"].append({"name": "candidate_filter_preserves_longest_match_boundaries_conflicts_and_unicode_case", "passed": True})

large = HotwordStore(run_dir / "large.json")
large.import_manual([{"term": f"Project{index:05d}", "aliases": [f"project number {index}"]}
                     for index in range(10020)])
start = time.perf_counter()
first = large.apply("project number 10019")
assert first.text == "Project10019"
first_seconds = time.perf_counter() - start
start = time.perf_counter()
assert large.apply("project number 10019").text == "Project10019"
repeat_seconds = time.perf_counter() - start
context = large.active_context(limit=30)
assert len(context.terms) == 30 and context.eligible_count == 10020 and len(context.omitted_terms) == 9990
assert len(context.context) <= 800
start = time.perf_counter()
assert large.record_usage("Project10019") == ["Project10019"]
usage_seconds = time.perf_counter() - start
misses = _compiled_replacements.cache_info().misses
assert large.record_usage("Project10019") == ["Project10019"]
assert large.apply("project number 10019").text == "Project10019"
assert _compiled_replacements.cache_info().misses == misses
large.upsert_manual("Project10019", ["project number 10019"], pinned=True)
assert large.active_context(limit=1).terms == ["Project10019"]
large.set_active("Project10019", False)
assert large.apply("project number 10019").text == "project number 10019"
report["cases"].append({"name": "ten_thousand_term_dictionary_full_corrections_and_bounded_prompt",
                         "terms": 10020, "first_seconds": first_seconds, "repeat_seconds": repeat_seconds,
                         "usage_seconds": usage_seconds, "usage_preserves_compiled_rules": True})

if args.asr:
    import numpy as np
    from speaktype.asr import ASREngine

    vocabulary = HotwordStore(run_dir / "asr.json")
    vocabulary.upsert_manual("SpeakType", ["Speak Type"])
    vocabulary.upsert_manual("OmniEcho", ["Omni Echo"])
    vocabulary.import_manual([{"term": term} for term in (
        "NumPy", "SciPy", "PyTorch", "TensorFlow", "JAX", "CUDA", "cuDNN", "Metal", "CoreML", "OpenCL",
        "scikit-learn", "Pandas", "Matplotlib", "Seaborn", "Polars", "DuckDB", "PostgreSQL", "SQLite", "Redis", "MongoDB",
        "Kubernetes", "Docker", "Podman", "Terraform", "Ansible", "Nginx", "Apache", "Caddy", "FastAPI", "Django",
        "Flask", "Starlette", "Uvicorn", "Gunicorn", "PyObjC", "SwiftUI", "AppKit", "UIKit", "WebKit", "Electron",
        "React", "Vue", "Svelte", "Angular", "Next.js", "TypeScript", "JavaScript", "Rust", "Golang", "Python",
        "Ruby", "Haskell", "Elixir", "Erlang", "Julia", "Fortran", "OpenMP", "OpenMPI", "NCCL", "Gloo",
    )])
    before = vocabulary.active_context()
    assert "SpeakType" not in before.terms and "OmniEcho" not in before.terms
    vocabulary.upsert_manual("SpeakType", ["Speak Type"], pinned=True)
    vocabulary.upsert_manual("OmniEcho", ["Omni Echo"], pinned=True)
    selected = vocabulary.active_context()
    assert {"SpeakType", "OmniEcho"}.issubset(selected.terms)
    engine = ASREngine()
    engine.load()
    if engine._warmup_thread is not None:
        engine._warmup_thread.join(timeout=120)
        assert not engine._warmup_thread.is_alive()
    for name, voice, sentence, language in (
        ("terms", "Samantha", "Please save the Speak Type project and Omni Echo notes.", "en"),
        ("ordinary", "Samantha", "Please send the meeting notes tomorrow morning.", "en"),
        ("chinese", "Tingting", "请保存今天的会议记录，明天上午发给同事。", "zh"),
    ):
        path = run_dir / f"{name}.wav"
        subprocess.run(["say", "-v", voice, "--file-format=WAVE", "--data-format=LEI16@16000",
                        "--channels=1", "-o", str(path), sentence], check=True)
        baseline = engine.transcribe(path, language=language, hotword_context=before.context)
        prioritized = engine.transcribe(path, language=language, hotword_context=selected.context)
        corrected = vocabulary.apply(prioritized)
        if name == "terms":
            targets = ("SpeakType", "OmniEcho")
            baseline_hits = sum(term in baseline for term in targets)
            priority_hits = sum(term in prioritized for term in targets)
            assert priority_hits > baseline_hits, (baseline, prioritized)
            assert all(term in corrected.text for term in targets), corrected
        else:
            assert baseline and prioritized
            assert not vocabulary.record_usage(baseline)
            assert not vocabulary.record_usage(prioritized)
            if name == "ordinary":
                assert all(word in prioritized.casefold() for word in ("meeting", "notes", "tomorrow"))
            else:
                assert all(word in prioritized for word in ("会议", "明天", "同事"))
        report["asr"].append({"name": name, "audio_source": "macOS speech synthesis", "input": sentence,
                              "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                              "without_priority": baseline, "with_priority": prioritized,
                              "after_explicit_aliases": asdict(corrected)})
    for name, context in (("ordinary_selection", before), ("priority_selection", selected)):
        silent = engine.transcribe(np.zeros(32000, dtype=np.float32), hotword_context=context.context)
        assert not silent.strip(), silent
        report["asr"].append({"name": f"silence_{name}", "output": silent})
    report["selection"] = {"before": asdict(before), "prioritized": asdict(selected)}

destination = args.report or run_dir / "report.json"
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"report": str(destination), "cases": report["cases"], "asr": report["asr"]}, ensure_ascii=False, indent=2))
