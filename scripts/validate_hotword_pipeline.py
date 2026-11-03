import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4
from unittest import TestCase

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--asr", action="store_true")
parser.add_argument("--report", type=Path)
args = parser.parse_args()
run_dir = root / "work" / f"hotword-validation-{uuid4().hex[:10]}"
run_dir.mkdir(parents=True)
os.environ["SPEAKTYPE_CONFIG_DIR"] = str(run_dir / "config")
bundle = os.environ.get("SPEAKTYPE_TEST_BUNDLE")
if not bundle:
    sys.path.insert(0, str(root))

from speaktype.asr import ASREngine, hotword_generation_kwargs
from speaktype.corrections import CorrectionStore
from speaktype.hotwords import HotwordStore
from speaktype.streaming import StreamingTranscriber

if bundle:
    bundle_path = Path(bundle).resolve()
    assert Path(sys.prefix).resolve().is_relative_to(bundle_path)
    for module_name in ("speaktype.asr", "speaktype.hotwords", "speaktype.corrections"):
        assert Path(sys.modules[module_name].__file__).resolve().is_relative_to(bundle_path), module_name

report = {"run_dir": str(run_dir), "runtime": bundle or "source", "cases": [], "asr": []}
store = HotwordStore(path=run_dir / "hotwords.json")
entry = store.upsert_manual("PyObjC", ["pie object see"], scope_app="com.openai.codex", scope_scene="code")
assert entry["active"] and entry["source"] == "manual"
app = {"name": "Codex", "bundle_id": "com.openai.codex"}
assert store.active_context(app_info=app, scene="code").terms == ["PyObjC"]
assert store.active_context(app_info={"name": "Mail"}, scene="email").terms == []
assert store.active_context(app_info=app, scene="email").terms == []
applied = store.apply("使用pyobjc和pie object see。", app_info=app, scene="code")
assert applied.text == "使用PyObjC和PyObjC。", applied
assert len(applied.changes) == 2
assert store.apply("pyobjctools", app_info=app, scene="code").text == "pyobjctools"
report["cases"].append({"name": "manual_scopes_and_chinese_boundaries", "result": asdict(applied)})

assert store.set_active("PyObjC", False)
store.add_or_reinforce("PyObjC", confidence=1.0, app_info=app, scene="code")
assert not store.get_all()[0]["active"]
assert store.active_context(app_info=app, scene="code", dictionary=["PyObjC"]).terms == []
reloaded = HotwordStore(path=run_dir / "hotwords.json")
assert reloaded.get_all()[0]["user_disabled"]
assert reloaded.set_active("PyObjC", True)
assert reloaded.active_context(app_info=app, scene="code").terms == ["PyObjC"]
renamed = reloaded.upsert_manual("PyObjC-12", ["pie object see twelve"], original_term="PyObjC")
assert renamed["term"] == "PyObjC-12" and len(reloaded) == 1
assert reloaded.remove("PyObjC-12") and len(reloaded) == 0
assert len(HotwordStore(path=run_dir / "hotwords.json")) == 0
report["cases"].append({"name": "pause_learning_persistence_rename_delete", "passed": True})

imports = HotwordStore(path=run_dir / "imports.json")
assert imports.import_manual([{"term": "NumPy", "aliases": ["num pie"]},
                              {"term": "SciPy", "active": False}]) == 2
snapshot = imports.get_all()
for payload, error in (([{"term": "ValidTerm"}, {"term": "x"}], ValueError),
                       ([{"term": "NumPy", "enabled": "false"}], TypeError),
                       ([{"term": "A" * 81}], ValueError),
                       ([{"term": "ValidTerm", "scope_app": False}], TypeError),
                       ([{"term": "ValidTerm", "aliases": [False]}], ValueError),
                       ([{"term": "NumPy", "state": "pending", "enabled": True}], ValueError),
                       ([{"term": "NumPy", "state": "invalid"}], ValueError),
                       ([{"term": "NumPy", "state": "pending", "enabled": None}], TypeError),
                       ([{"term": "NumPy", "confidence": float("nan")}], ValueError),
                       ([{"term": "NumPy", "observations": True}], ValueError),
                       ([{"term": "NumPy", "state": "pending", "source": "manual"}], ValueError),
                       ([{"term": "NumPy", "user_confirmed": "true"}], TypeError),
                       ([{"term": "NumPy", "state": "pending", "user_confirmed": True}], ValueError),
                       ([{"term": "NumPy"}, {"term": "numpy"}], ValueError)):
    with TestCase().assertRaises(error):
        imports.import_manual(payload)
    assert imports.get_all() == snapshot
    assert HotwordStore(path=run_dir / "imports.json").get_all() == snapshot
report["cases"].append({"name": "atomic_import_strict_fields", "passed": True})

pending_store = HotwordStore(path=run_dir / "pending.json")
pending_store.add_or_reinforce("PendingTerm", ["pending term"], confidence=0.72)
assert pending_store.import_manual([{"term": "PendingTerm", "aliases": ["pending term"],
                                     "enabled": False, "state": "pending"}]) == 1
pending_entry = pending_store.get_all()[0]
assert not pending_entry["active"] and not pending_entry["user_disabled"]
assert pending_entry["source"] == "post_edit" and pending_entry["confidence"] == 0.72
pending_store.add_or_reinforce("PendingTerm", confidence=0.72)
assert pending_store.get_all()[0]["active"]
assert pending_store.apply("pending term").text == "pending term"
assert pending_store.import_manual([{"term": "NewCandidate", "aliases": ["new candidate"],
                                     "state": "pending"}]) == 1
new_candidate = next(entry for entry in pending_store.get_all() if entry["term"] == "NewCandidate")
assert not new_candidate["active"] and not new_candidate["user_disabled"]
assert new_candidate["source"] == "imported" and new_candidate["confidence"] == 0.5
transfer = HotwordStore(path=run_dir / "transferred.json")
assert transfer.import_manual([{"term": "SavedCandidate", "aliases": ["saved candidate"],
                                "enabled": False, "state": "pending", "source": "post_edit",
                                "confidence": 0.73, "observations": 1}]) == 1
transferred = transfer.get_all()[0]
assert transferred["source"] == "post_edit" and transferred["confidence"] == 0.73
assert transferred["observations"] == 1 and not transferred["user_disabled"]
assert HotwordStore(path=run_dir / "transferred.json").get_all() == transfer.get_all()
report["cases"].append({"name": "pending_import_preserves_learning_state", "passed": True})

approval = HotwordStore(path=run_dir / "approval.json")
approval.add_or_reinforce("ApprovedTerm", ["approved term"], confidence=0.72)
before_approval = approval.get_all()[0]
assert not before_approval["active"] and not before_approval["user_confirmed"]
assert approval.set_active("ApprovedTerm", True)
approved = approval.get_all()[0]
assert approved["user_confirmed"] and approved["source"] == before_approval["source"]
assert approved["confidence"] == before_approval["confidence"]
assert approval.apply("approved term", learned_corrections_enabled=False).text == "ApprovedTerm"
assert approval.set_active("ApprovedTerm", False)
approval.add_or_reinforce("ApprovedTerm", confidence=0.79)
paused_approval = approval.get_all()[0]
assert not paused_approval["active"] and paused_approval["user_confirmed"]
assert approval.apply("approved term").text == "approved term"
assert HotwordStore(path=run_dir / "approval.json").get_all() == approval.get_all()
assert approval.import_manual([{"term": "ApprovedTerm", "aliases": ["approved term"],
                                "state": "disabled", "source": "post_edit", "confidence": 0.79,
                                "observations": 2, "user_confirmed": True}]) == 1
assert approval.get_all()[0]["user_confirmed"] and not approval.get_all()[0]["active"]
assert approval.set_active("ApprovedTerm", True)
assert approval.apply("approved term", learned_corrections_enabled=False).text == "ApprovedTerm"
report["cases"].append({"name": "explicit_candidate_approval_preserves_confidence_and_source", "passed": True})

store = HotwordStore(path=run_dir / "replacements.json")
store.upsert_manual("Qwen3", ["cute three"])
store.upsert_manual("Qwen3-ASR", ["cute three asr"])
store.upsert_manual("OmniEcho", ["omni echo", "shared name"])
store.upsert_manual("OmniTalk", ["shared name"])
result = store.apply("使用cute three asr与cute three；shared name；qwen3 - asr。")
assert result.text == "使用Qwen3-ASR与Qwen3；shared name；Qwen3-ASR。", result
assert store.apply("qwen3_asr_extra").text == "qwen3_asr_extra"
chain = HotwordStore(path=run_dir / "chain.json")
chain.upsert_manual("Beta", ["Alpha"])
chain.upsert_manual("Gamma", ["Beta"])
assert chain.apply("Alpha").text == "Beta"
assert chain.apply("Beta").text == "Beta"
report["cases"].append({"name": "longest_alias_conflicts_nonrecursive", "result": asdict(result)})

learned = HotwordStore(path=run_dir / "learned.json")
learned.add_or_reinforce("OmniEcho", ["omni echo"], confidence=0.91, app_info=app, scene="code")
assert learned.apply("omni echo").text == "OmniEcho"
assert learned.apply("omni echo", learned_corrections_enabled=False).text == "omni echo"
assert learned.apply("omniecho", learned_corrections_enabled=False).text == "OmniEcho"
learned.add_or_reinforce("LowConfidence", ["low confidence"], confidence=0.72)
learned.add_or_reinforce("LowConfidence", ["low confidence"], confidence=0.72)
assert learned.apply("low confidence").text == "low confidence"
assert learned.set_active("OmniEcho", False)
assert learned.apply("omni echo", dictionary=["OmniEcho"]).text == "omni echo"
assert learned.active_context(dictionary=["OmniEcho", "NewManualName"]).terms == ["NewManualName", "LowConfidence"]
assert learned.apply("newmanualname", dictionary=["NewManualName"]).text == "NewManualName"
learned.upsert_manual("OmniEcho", ["omni echo"], enabled=True)
assert learned.apply("omni echo", learned_corrections_enabled=False).text == "OmniEcho"
learned.add_or_reinforce("Python", ["PI thon"], confidence=0.9)
assert learned.apply("使用PI thon").text == "使用Python"
assert learned.apply("PI thon", learned_corrections_enabled=False).text == "PI thon"
report["cases"].append({"name": "learned_alias_switch_confidence_and_dictionary_pause", "passed": True})

budget = HotwordStore(path=run_dir / "budget.json")
budget.add_or_reinforce("LearnedLongProjectName", confidence=0.99)
budget.upsert_manual("AReallyLongManualProjectName")
budget.upsert_manual("MLX")
context = budget.active_context(limit=3, max_chars=23, dictionary=["NumPy", "NumPy", "MLX"])
assert context.terms == ["MLX", "NumPy"], context
assert context.context == "Vocabulary: MLX, NumPy."
assert len(context.context) == 23 and len(context.entries) == 2
assert budget.active_context(limit=3, max_chars=15, dictionary=["NumPy"]).terms == []
assert budget.active_context(limit=3, max_chars=16, dictionary=["NumPy"]).context == "Vocabulary: MLX."
assert budget.active_context(limit=0).terms == []
assert budget.active_context(max_chars=0).terms == []
report["cases"].append({"name": "dictionary_priority_deduplication_budget", "context": asdict(context)})

corrections = CorrectionStore(path=run_dir / "corrections.json")
corrections.add("秋文", "Qwen")
corrections.add("PI thon", "Python")
corrections.add("Python", "OtherName")
assert corrections.apply("使用秋文和PI thon；PI thoner") == "使用Qwen和Python；PI thoner"
report["cases"].append({"name": "correction_chinese_boundaries_literal_nonrecursive", "passed": True})

contractions = HotwordStore(path=run_dir / "contractions.json")
contractions.upsert_manual("Dawn", ["Don"])
sentence = "don't Don't DON’T don't测试 Don's Don’s Don"
expected = "don't Don't DON’T don't测试 Dawn's Dawn’s Dawn"
assert contractions.apply(sentence).text == expected
contraction_corrections = CorrectionStore(path=run_dir / "contraction-corrections.json")
contraction_corrections.add("Don", "Dawn")
assert contraction_corrections.apply(sentence) == expected
contractions.upsert_manual("DoNot", ["don't"])
assert contractions.apply("don't").text == "DoNot"
report["cases"].append({"name": "contractions_and_possessives", "passed": True})

if args.asr:
    import numpy as np
    import soundfile as sf

    engine = ASREngine()
    engine.load()
    if engine._warmup_thread is not None:
        engine._warmup_thread.join(timeout=120)
        assert not engine._warmup_thread.is_alive()
    terms = ["SpeakType", "Qwen3-ASR", "OmniEcho", "NeurIPS"]
    context = "Vocabulary: " + ", ".join(terms) + "."
    bare_context = " ".join(terms)
    kwargs = hotword_generation_kwargs(engine.model, context)
    assert kwargs == {"system_prompt": context}, kwargs
    assert hotword_generation_kwargs(engine.model, context, "stream_transcribe") == kwargs
    with TestCase().assertRaises(RuntimeError):
        hotword_generation_kwargs(engine.model, context, "parameters")
    prompt_ids = engine.model._build_prompt(2, "English", kwargs["system_prompt"])
    decoded = engine.model._tokenizer.decode(np.asarray(prompt_ids)[0].tolist(), skip_special_tokens=False)
    assert context in decoded, decoded
    report["prompt"] = {"parameter": "system_prompt", "terms_present_in_actual_model_prompt": True}
    cases = (
        ("ordinary", "Samantha", "Please send the meeting notes tomorrow morning.", "en"),
        ("english", "Samantha", "Please save the Speak Type project and Omni Echo notes.", "en"),
        ("chinese", "Tingting", "请保存秋文三的识别结果，然后打开 Speak Type 项目。", "zh"),
    )
    for name, voice, sentence, language in cases:
        audio_path = run_dir / f"{name}.wav"
        subprocess.run(["say", "-v", voice, "--file-format=WAVE", "--data-format=LEI16@16000",
                        "--channels=1", "-o", str(audio_path), sentence], check=True)
        digest = hashlib.sha256(audio_path.read_bytes()).hexdigest()
        started = time.monotonic()
        baseline = engine.transcribe(audio_path, language=language)
        bare_result = engine.transcribe(audio_path, language=language, hotword_context=bare_context)
        contextual = engine.transcribe(audio_path, language=language, hotword_context=context)
        assert baseline and contextual, (baseline, contextual)
        if name == "ordinary":
            assert all(word in contextual.lower() for word in ("meeting", "notes", "tomorrow")), contextual
            assert not any(term.casefold() in contextual.casefold() for term in terms), contextual
        assert hashlib.sha256(audio_path.read_bytes()).hexdigest() == digest
        report["asr"].append({"name": name, "audio_source": "macOS built-in speech synthesis",
                              "input": sentence, "sha256": digest, "baseline": baseline,
                              "with_bare_terms": bare_result, "with_hotwords": contextual,
                              "seconds": round(time.monotonic() - started, 3)})
        samples, rate = sf.read(audio_path, dtype="float32")
        assert rate == 16000
        in_memory = engine.transcribe(samples, language=language, hotword_context=context)
        assert in_memory == contextual, (in_memory, contextual)
        report["asr"][-1]["in_memory"] = in_memory
        if name == "english":
            partials = []
            preview = StreamingTranscriber(engine, on_partial_text=partials.append)
            preview.start(language=language, hotword_context=context)
            try:
                preview._run_chunked(samples, language, context)
                assert engine.acquire_inference(blocking=False), "Preview retained the inference lock"
                engine.release_inference()
                assert partials and partials[-1] == contextual, partials
            finally:
                preview.stop(wait=True)
            report["asr"].append({"name": "actual_chunked_preview", "output": partials[-1],
                                  "inference_lock_released": True})
    silent = engine.transcribe(np.zeros(32000, dtype=np.float32), hotword_context=context)
    assert not silent.strip(), silent
    report["asr"].append({"name": "silence_with_hotwords", "output": silent})
    assert not list((run_dir / "config" / "temp").glob("speaktype-transcript-*"))
    report["prompt"]["unsupported_method_rejected"] = True
    report["prompt"]["transcript_outputs_cleaned"] = True

destination = args.report or run_dir / "report.json"
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
print(f"REPORT {destination}")
