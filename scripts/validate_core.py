import argparse
import csv
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from unittest import TestCase
from uuid import uuid4


REPO = Path(__file__).resolve().parents[1]
BUNDLE = os.environ.get("SPEAKTYPE_TEST_BUNDLE")
SUITE_NAMES = ("commands", "config", "corrections", "snippets", "hotwords", "history")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def validate_commands(run_dir):
    from speaktype.commands import (
        build_edit_prompt,
        detect_action_command,
        detect_edit_command,
        process_punctuation_commands,
    )
    from speaktype.context import get_scene_for_app, get_tone_for_app

    for phrase in ("undo that", " Undo last. ", "scratch that", "撤销刚才", "撤回。"):
        assert detect_action_command(phrase) == "undo_last", phrase
    for phrase in ("I said undo that yesterday", "undo that and continue", "撤回以后继续", ""):
        assert detect_action_command(phrase) is None, phrase
    for phrase in (
        "make this shorter", "Make it more professional.", "translate this into Chinese",
        "fix the grammar", "bullet list this", "改成要点", "翻译成英语。", "润色一下",
    ):
        detected, command = detect_edit_command(phrase)
        assert detected and command == phrase.strip(), phrase
    for phrase in ("I want to make this shorter tomorrow", "hello world", "缩短一些时间", ""):
        assert detect_edit_command(phrase) == (False, ""), phrase
    assert process_punctuation_commands("hello world period") == "hello world."
    assert process_punctuation_commands("你好 句号") == "你好。"
    for spoken, expected in (
        ("hello close quote period", 'hello".'),
        ("open quote hello close quote period", '"hello".'),
        ("He said open double quote hello close double quote period", 'He said "hello".'),
        ("open quote a period of time close quote period", '"a period of time".'),
        ("open quote hello comma close quote period", '"hello,".'),
        ("hello open parenthesis world close parenthesis period", "hello (world)."),
        ("open quote hello open parenthesis world close parenthesis close quote period", '"hello (world)".'),
        ("left open square bracket value close square bracket colon", "left [value]:"),
        ("open single quote café close single quote semicolon", "'café';"),
        ("open   quote hello close   quote period", '"hello".'),
        ("他说左引号你好右引号句号", "他说“你好”。"),
        ("左双引号内容逗号右双引号句号", "“内容，”。"),
        ("说明左括号补充右括号句号", "说明（补充）。"),
        ("左引号内容左括号补充右括号右引号问号", "“内容（补充）”？"),
        ("左单引号你好右单引号感叹号", "‘你好’！"),
        ("左书名号书名右书名号句号", "《书名》。"),
        ("hello close quote period new line next comma", 'hello".\nnext,'),
        ("第一行句号新段落第二行问号", "第一行。\n\n第二行？"),
    ):
        actual = process_punctuation_commands(spoken)
        assert actual == expected, (spoken, actual, expected)
    for phrase in ("the period of time was long", "a comma appears here", "tabletop",
                   "we need to close quote handling before release",
                   "open bracket and close bracket describe formatting",
                   "这个句号用于结束句子", "左括号和右括号是标点", "他在解释右引号的用法"):
        assert process_punctuation_commands(phrase) == phrase
    assert process_punctuation_commands("hello new line world").count("\n") == 1
    assert process_punctuation_commands("hello new paragraph world").count("\n") == 2
    assert process_punctuation_commands("第一段新段落第二段").count("\n") == 2
    assert "\t" in process_punctuation_commands("left tab right")
    assert process_punctuation_commands("") == ""
    selected = "引用内容：α、中文与 emoji 🧪\n第二行"
    prompt = build_edit_prompt("改成列表", selected, tone="formal")
    assert selected in prompt and "改成列表" in prompt and "formal" in prompt
    for bundle, tone, scene in (
        ("com.apple.mail", "formal", "email"),
        ("com.tencent.xinWeChat", "casual", "chat"),
        ("com.microsoft.VSCode", "technical", "code"),
        ("md.obsidian", "neutral", "notes"),
        ("unknown.application", "neutral", "default"),
    ):
        assert get_tone_for_app({"bundle_id": bundle}) == tone
        assert get_scene_for_app({"bundle_id": bundle}) == scene


def validate_config(run_dir):
    from speaktype import config

    assert config.CONFIG_DIR == run_dir / "config"
    assert config.CONFIG_DIR.is_relative_to(run_dir)
    defaults = config.load_config()
    temporary_directory = config.get_temp_dir()
    assert temporary_directory == config.CONFIG_DIR / "temp"
    assert temporary_directory.is_dir()
    assert temporary_directory.stat().st_mode & 0o077 == 0
    assert defaults["asr_backend"] == "qwen"
    assert defaults["dictation_mode"] == "push_to_talk"
    assert defaults["hotkey"] == "right_cmd"
    saved = {**defaults, "hotkey": "f5", "ui_language": "en", "language": "ja",
             "asr_backend": "whisper", "asr_model": "", "whisper_model": "",
             "scene_prompts": {"notes": "保存中文、日文と emoji 🧪"}}
    config.save_config(saved)
    loaded = config.load_config()
    assert loaded["hotkey"] == "f5"
    assert loaded["asr_backend"] == "qwen"
    assert loaded["asr_model"] == config.DEFAULT_CONFIG["asr_model"]
    assert loaded["whisper_model"] == config.DEFAULT_CONFIG["whisper_model"]
    assert loaded["scene_prompts"]["notes"] == "保存中文、日文と emoji 🧪"
    assert loaded == json.loads(config.CONFIG_FILE.read_text(encoding="utf-8"))
    write_json(config.CONFIG_FILE, {"hotkey": "f6"})
    merged = config.load_config()
    assert merged["hotkey"] == "f6" and "history_max_entries" in merged
    for malformed in ("not-json{{", "[", "{\"hotkey\":"):
        config.CONFIG_FILE.write_text(malformed, encoding="utf-8")
        damaged = config.CONFIG_FILE.read_bytes()
        with TestCase().assertRaises(json.JSONDecodeError):
            config.load_config()
        assert config.CONFIG_FILE.read_bytes() == damaged
    for wrong_shape in (None, [], "text", 42, False):
        write_json(config.CONFIG_FILE, wrong_shape)
        with TestCase().assertRaises(ValueError):
            config.load_config()
    for key, invalid_values in {
        "polish_enabled": ("yes", 1, None),
        "hotkey": ([], 8, None),
        "sample_rate": (0, -1, True, "16000", 1.5),
        "history_max_entries": (0, -1, False, "1000", 1.5),
        "hotword_max_context_terms": (0, -1, True, "30", 1.5),
        "max_recording_seconds": (-1, True, "360", float("nan"), float("inf")),
        "hotword_observation_seconds": (-1, True, "18", float("nan"), float("inf")),
        "hotword_observation_stable_seconds": (-1, True, "1.2", float("nan"), float("inf")),
        "dictation_mode": ("unknown", ""),
        "insert_method": ("unknown", ""),
        "ui_language": ("unknown", ""),
        "audio_device": ({}, [], True, -1),
        "scene_prompts": ([], "bad", None, {"notes": []}, {"notes": 1}),
    }.items():
        for invalid in invalid_values:
            write_json(config.CONFIG_FILE, {key: invalid})
            with TestCase().assertRaises(ValueError):
                config.load_config()
    config.save_config(defaults)
    before = config.CONFIG_FILE.read_bytes()
    with TestCase().assertRaises(TypeError):
        config.write_json_file(config.CONFIG_FILE, {"unserializable": object()})
    assert config.CONFIG_FILE.read_bytes() == before
    assert not list(config.CONFIG_DIR.glob(".config.json.*.tmp"))
    for device in (None, 0, "Built-in Microphone"):
        config.save_config({**defaults, "audio_device": device})
        assert config.load_config()["audio_device"] == device
    config.save_config({**defaults, "dictation_mode": "toggle", "insert_method": "type"})
    assert config.load_config()["dictation_mode"] == "toggle"
    assert config.load_config()["insert_method"] == "type"
    for limit in (0, None, 360):
        config.save_config({**defaults, "max_recording_seconds": limit})
        assert config.load_config()["max_recording_seconds"] == limit
    for key in ("hotword_observation_seconds", "hotword_observation_stable_seconds"):
        config.save_config({**defaults, key: 0})
        assert config.load_config()[key] == 0
    words = ["Qwen3-ASR", "北京大学", "café", "模型🧪"]
    config.save_custom_dictionary(words)
    assert config.load_custom_dictionary() == words
    for malformed in ("broken{", "["):
        config.CUSTOM_DICT_FILE.write_text(malformed, encoding="utf-8")
        with TestCase().assertRaises(json.JSONDecodeError):
            config.load_custom_dictionary()
    for wrong_shape in (None, {}, "word", 123, False):
        write_json(config.CUSTOM_DICT_FILE, wrong_shape)
        with TestCase().assertRaises(ValueError):
            config.load_custom_dictionary()
    for invalid in (None, {}, [], 42, False):
        write_json(config.CUSTOM_DICT_FILE, ["valid", invalid])
        with TestCase().assertRaises(ValueError):
            config.load_custom_dictionary()
    config.save_custom_dictionary(words)
    assert not list(config.CONFIG_DIR.glob(".*.tmp"))


def validate_corrections(run_dir):
    from speaktype.corrections import CorrectionStore

    path = run_dir / "corrections.json"
    store = CorrectionStore(path=path)
    assert store.get_all() == [] and store.apply("") == ""
    store.add("PI thon", "Python")
    store.add("我 sql", "MySQL")
    store.add("api", "API")
    assert store.apply("I use pi THON and 我 sql.") == "I use Python and MySQL."
    assert store.apply("happy APIs rapid") == "happy APIs rapid"
    store.add("API", "Application API")
    assert len(store) == 3
    assert store.apply("api") == "Application API"
    store.add("path token", r"C:\Users\name\1\new")
    assert store.apply("path token") == r"C:\Users\name\1\new"
    store.add("pattern token", r"\g<name>\1")
    assert store.apply("pattern token") == r"\g<name>\1"
    store.add("c++", "C Plus Plus")
    assert store.apply("Use C++!") == "Use C Plus Plus!"
    store.add("blank token", "")
    assert store.apply("blank token") == ""
    store.add("", "ignored")
    copied = store.get_all()
    copied[0]["right"] = "External mutation"
    assert store.apply("PI thon") == "Python"
    reopened = CorrectionStore(path=path)
    assert reopened.get_all() == store.get_all()
    assert reopened.apply("path token") == r"C:\Users\name\1\new"
    reopened.remove("PI THON")
    assert reopened.apply("PI thon") == "PI thon"
    reopened.replace_all([{"wrong": "pi", "right": "π"},
                          {"wrong": "pi thon", "right": "Python"}])
    assert reopened.apply("pi thon plus pi") == "Python plus π"
    reopened.clear()
    assert CorrectionStore(path=path).get_all() == []
    for malformed in ("{broken", "["):
        path.write_text(malformed, encoding="utf-8")
        damaged = path.read_bytes()
        with TestCase().assertRaises(json.JSONDecodeError):
            CorrectionStore(path=path)
        assert path.read_bytes() == damaged
    for wrong_shape in (None, {}, "rules", 42):
        write_json(path, wrong_shape)
        with TestCase().assertRaises(ValueError):
            CorrectionStore(path=path)
    for invalid in (None, False, 4, "bad", [], {}, {"wrong": []},
                    {"wrong": "valid", "right": 7}):
        write_json(path, [{"wrong": "valid", "right": "有效🧪"}, invalid])
        with TestCase().assertRaises(ValueError):
            CorrectionStore(path=path)
    write_json(path, [{"wrong": "valid", "right": "有效🧪"}])
    assert CorrectionStore(path=path).apply("valid!") == "有效🧪!"
    concurrent = CorrectionStore(path=run_dir / "corrections-concurrent.json")
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda index: concurrent.add(f"word{index}", f"Term{index}"), range(30)))
    assert len(concurrent) == 30
    assert CorrectionStore(path=concurrent._path).get_all() == concurrent.get_all()


def validate_snippets(run_dir):
    from speaktype.snippets import (
        DEFAULT_SNIPPETS, SNIPPETS_FILE, SnippetLibrary, _expand_variables,
    )

    assert SNIPPETS_FILE.parent == run_dir / "config"
    library = SnippetLibrary()
    assert library.get_all() == DEFAULT_SNIPPETS
    library.add("我的邮箱", "validation@example.invalid", "中文触发短语")
    library.add("project note", "第一行🧪\n第二行 café", "Unicode 和换行")
    library.add("my marker", "value: {env:SPEAKTYPE_VALIDATION_MARKER}")
    assert library.match("我的邮箱。") == "validation@example.invalid"
    assert library.match("我邮箱") == "validation@example.invalid"
    assert library.match("我邮箱", fuzzy=False) is None
    assert library.match("PROJECT NOTE") == "第一行🧪\n第二行 café"
    assert library.match("project, note!") == "第一行🧪\n第二行 café"
    assert library.match("my marker") == "value: real-process-environment-🧪"
    assert library.match("my, marker!") is None
    assert library.match("my marke") is None
    assert library.match("") is None
    assert library.match("I would like my email inserted in this sentence") is None
    long_trigger = "a sufficiently long trigger phrase for ordinary dictation protection"
    library.add(long_trigger, "LONG_BODY")
    assert library.match(long_trigger) == "LONG_BODY"
    assert library.match(long_trigger.replace("sufficiently", "suficiently")) is None
    fixed_time = datetime(2026, 11, 1, 17, 8)
    assert _expand_variables("{date}|{time}|{datetime}", now=fixed_time) == (
        "2026-11-01|17:08|2026-11-01 17:08")
    assert _expand_variables("{clipboard}|{clipboard}", clipboard="剪贴板🧪") == "剪贴板🧪|剪贴板🧪"
    assert _expand_variables("before {unknown_key} after") == "before {unknown_key} after"
    assert _expand_variables("{env:SPEAKTYPE_VALIDATION_MISSING_VARIABLE}") == ""
    snapshot = library.get_all()
    snapshot[0]["text"] = "External mutation"
    assert library.get_all()[0]["text"] == ""
    reopened = SnippetLibrary()
    assert reopened.match("project note") == "第一行🧪\n第二行 café"
    index = next(i for i, item in enumerate(reopened.get_all()) if item["trigger"] == "project note")
    reopened.update(index, "project note", "已更新🧪", "更新说明")
    assert SnippetLibrary().match("project note") == "已更新🧪"
    reopened.remove(index)
    assert SnippetLibrary().match("project note", fuzzy=False) is None
    for malformed in ("invalid-json{", "["):
        SNIPPETS_FILE.write_text(malformed, encoding="utf-8")
        damaged = SNIPPETS_FILE.read_bytes()
        with TestCase().assertRaises(json.JSONDecodeError):
            SnippetLibrary()
        assert SNIPPETS_FILE.read_bytes() == damaged
    for wrong_shape in (None, {}, "snippets", 42):
        write_json(SNIPPETS_FILE, wrong_shape)
        with TestCase().assertRaises(ValueError):
            SnippetLibrary()
    for invalid in (None, [], "bad", 8, {}, {"trigger": []},
                    {"trigger": "valid", "text": 4},
                    {"trigger": "valid", "text": "body", "description": []}):
        write_json(SNIPPETS_FILE, [invalid])
        with TestCase().assertRaises(ValueError):
            SnippetLibrary()
    write_json(SNIPPETS_FILE, [{"trigger": "有效短语", "text": "真实文件🧪", "description": "说明"}])
    assert SnippetLibrary().match("有效短语") == "真实文件🧪"


def validate_hotwords(run_dir):
    from speaktype.hotwords import HotwordStore, extract_confident_corrections

    path = run_dir / "hotwords.json"
    store = HotwordStore(path=path)
    codex = {"name": "Codex", "bundle_id": "com.openai.codex"}
    mail = {"name": "Mail", "bundle_id": "com.apple.mail"}
    candidate = store.add_or_reinforce("Qwen3-ASR", ["cute three asr", "QWEN3-ASR"],
                                       confidence=0.6, app_info=codex, scene="code", language="en")
    assert candidate and candidate["active"] is False
    assert candidate["aliases"] == ["cute three asr"]
    assert store.active_context().terms == []
    candidate = store.add_or_reinforce("Qwen3-ASR", ["q wen asr"], confidence=0.7,
                                       app_info=codex, scene="code", language="en")
    assert candidate["active"] and candidate["observations"] == 2
    assert candidate["apps"]["com.openai.codex"] == 2
    store.add_or_reinforce("PyObjC", confidence=0.95, app_info=codex, scene="code", language="en")
    store.add_or_reinforce("QuarterlyClose", confidence=0.9, app_info=mail, scene="email", language="en")
    assert store.active_context(app_info=codex, scene="code", limit=1).terms == ["PyObjC"]
    assert store.active_context(app_info=mail, scene="email", limit=1).terms == ["QuarterlyClose"]
    assert store.active_context(limit=0).terms == []
    context = store.active_context(max_chars=12)
    assert len(context.context) <= 12 and context.context == " ".join(context.terms)
    for term in ("", "a", "这是完整句子。", "some sentence, with punctuation"):
        assert store.add_or_reinforce(term, confidence=1) is None, term
    payload = {"learn": True, "hotwords": [{"term": "mlx-audio", "aliases": ["em el ex audio"],
                                             "confidence": 0.91}]}
    learned = store.learn_from_payload(payload, raw_text="em el ex audio", edited_text="使用 mlx-audio。")
    assert len(learned) == 1 and learned[0]["term"] == "mlx-audio"
    assert store.learn_from_payload(payload, raw_text="em el ex audio", edited_text="删除这个词") == []
    assert store.learn_from_payload({**payload, "learn": False}, edited_text="mlx-audio") == []
    copied = store.get_all()
    copied[0]["aliases"].append("EXTERNAL_MUTATION")
    copied[0]["apps"]["external.app"] = 999
    assert "EXTERNAL_MUTATION" not in store.get_all()[0]["aliases"]
    assert "external.app" not in store.get_all()[0]["apps"]
    assert HotwordStore(path=path).get_all() == store.get_all()
    correction_payload = {"learn": True, "corrections": [
        {"wrong": "cute three asr", "right": "Qwen3-ASR", "confidence": 0.91},
        {"wrong": "Pro 点 txt", "right": "Pro.txt", "confidence": 0.95},
        {"wrong": "测试仪", "right": "测试", "confidence": 0.95},
        {"wrong": "maybe", "right": "MaybeAPI", "confidence": 0.2},
        {"wrong": "cute three asr", "right": "Qwen3-ASR", "confidence": 0.98},
        {"wrong": "invented token", "right": "ImaginaryAPI", "confidence": 0.99},
    ]}
    corrections = extract_confident_corrections(correction_payload,
        raw_text="cute three asr Pro 点 txt 测试仪 maybe", inserted_text="",
        edited_text="Qwen3-ASR Pro.txt 测试 MaybeAPI")
    assert corrections == [
        {"wrong": "cute three asr", "right": "Qwen3-ASR", "confidence": 0.91},
        {"wrong": "Pro 点 txt", "right": "Pro.txt", "confidence": 0.95},
    ]
    assert extract_confident_corrections(correction_payload, raw_text="nothing related",
                                         edited_text="Qwen3-ASR Pro.txt") == []
    assert extract_confident_corrections(correction_payload, raw_text="cute three asr",
                                         edited_text="removed") == []
    for malformed in ("invalid{", "["):
        path.write_text(malformed, encoding="utf-8")
        damaged = path.read_bytes()
        with TestCase().assertRaises(json.JSONDecodeError):
            HotwordStore(path=path)
        assert path.read_bytes() == damaged
    for wrong_shape in (None, {}, "hotwords", 42):
        write_json(path, wrong_shape)
        with TestCase().assertRaises(ValueError):
            HotwordStore(path=path)
    for invalid in (None, [], "bad", 8):
        write_json(path, [invalid])
        with TestCase().assertRaises(ValueError):
            HotwordStore(path=path)
    valid_entry = store.get_all()[0]
    for field, invalid in (("observations", "broken"), ("aliases", 4), ("apps", "broken"),
                           ("scenes", []), ("languages", None), ("evidence", 4),
                           ("term", []), ("active", "true")):
        write_json(path, [{**valid_entry, field: invalid}])
        with TestCase().assertRaises(ValueError):
            HotwordStore(path=path)
    write_json(path, [valid_entry])
    assert HotwordStore(path=path).active_context().terms == ["Qwen3-ASR"]
    concurrent_path = run_dir / "hotwords-concurrent.json"
    concurrent = HotwordStore(path=concurrent_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda index: concurrent.add_or_reinforce(f"TermAPI{index}", confidence=0.9), range(30)))
    assert len(concurrent) == 30
    assert HotwordStore(path=concurrent_path).get_all() == concurrent.get_all()


def validate_history(run_dir):
    from speaktype.history import DictationHistory, EXPORT_FORMATS, INSERTION_OUTCOMES

    path = run_dir / "history" / "dictation.json"
    history = DictationHistory(max_entries=3, path=path)
    assert history.snapshot() == [] and history.get_recent(0) == []
    first = history.add("原始识别🧪", "整理之后 café\n第二行", "编辑器", 1.26, outcome="pending")
    assert isinstance(first, str) and first
    original = history.snapshot()[0]
    assert history.update_text(first, "更新后的 café\n第二行🧪")
    updated = DictationHistory(max_entries=3, path=path).snapshot()[0]
    assert updated["polished"] == "更新后的 café\n第二行🧪"
    assert all(updated[key] == original[key] for key in original if key != "polished")
    assert history.update_text("missing-id", "unused") is False
    with TestCase().assertRaises(ValueError):
        history.update_text(first, None)
    assert history.update_text(first, "整理之后 café\n第二行")
    assert history.set_outcome(first, "inserted")
    second = history.add('quoted, "raw"\n中文', 'quoted, "final"\n日本語', "App, Name", 2.25,
                         outcome="failed")
    third = history.add("sent text", "sent text", "终端", 3.0, outcome="sent")
    assert len({first, second, third}) == 3
    assert history.get_recent(2)[0]["id"] == second
    assert history.get_recent(1)[0]["outcome"] == "sent"
    assert history.set_outcome("missing-id", "failed") is False
    with TestCase().assertRaises(ValueError):
        history.add("bad", "bad", outcome="invented")
    with TestCase().assertRaises(ValueError):
        history.set_outcome(first, "invented")
    assert set(INSERTION_OUTCOMES) == {"pending", "saved", "inserted", "sent", "failed", "cancelled"}
    entries = history.snapshot()
    entries[0]["polished"] = "External mutation"
    assert history.snapshot()[0]["polished"] == "整理之后 café\n第二行"
    recent = history.get_recent(1)
    recent[0]["raw"] = "External mutation"
    assert history.get_recent(1)[0]["raw"] == "sent text"
    assert DictationHistory(max_entries=3, path=path).snapshot() == history.snapshot()
    assert history.get_stats()["total_entries"] == 3
    assert history.get_stats()["total_words"] == sum(len(e["polished"].split()) for e in history.snapshot())
    exports = run_dir / "exports"
    for fmt in EXPORT_FORMATS:
        output = history.export(exports / f"history.{fmt}")
        assert output == (exports / f"history.{fmt}").resolve()
        content = output.read_text(encoding="utf-8")
        assert "中文" in content or "整理之后" in content
        if fmt == "json":
            assert json.loads(content) == history.snapshot()
        elif fmt == "csv":
            rows = list(csv.DictReader(io.StringIO(content)))
            assert len(rows) == 3
            assert rows[1]["raw"] == 'quoted, "raw"\n中文'
            assert rows[1]["polished"] == 'quoted, "final"\n日本語'
            assert rows[1]["app"] == "App, Name"
        elif fmt == "md":
            assert "# SpeakType Dictation History" in content
            assert "原始识别🧪" in content and "整理之后 café" in content
        elif fmt == "txt":
            assert "整理之后 café" in content
    explicit = history.export(exports / "explicit.data", fmt="JSON")
    assert json.loads(explicit.read_text(encoding="utf-8")) == history.snapshot()
    with TestCase().assertRaises(ValueError):
        history.export(exports / "unsupported.pdf")
    assert not (exports / "unsupported.pdf").exists()
    fourth = history.add("fourth", "fourth", duration_sec=1)
    assert [e["id"] for e in history.snapshot()] == [second, third, fourth]
    assert len(json.loads(path.read_text(encoding="utf-8"))) == 3
    history.clear()
    assert DictationHistory(path=path).snapshot() == []
    worker = history.add_async("异步🧪", "保存成功", outcome="pending")
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert DictationHistory(path=path).snapshot()[0]["raw"] == "异步🧪"
    concurrent_path = run_dir / "history" / "concurrent.json"
    concurrent = DictationHistory(max_entries=100, path=concurrent_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(lambda index: concurrent.add(f"raw {index}", f"final {index}"), range(40)))
    assert len(set(ids)) == 40
    assert len(DictationHistory(path=concurrent_path).snapshot()) == 40
    legacy = [{"timestamp": "2026-10-31T09:00:00", "raw": "旧记录", "polished": "旧记录",
               "duration": 1.5, "app": "Notes"}]
    write_json(path, legacy)
    migrated = DictationHistory(path=path)
    assert migrated.snapshot()[0]["id"] and migrated.snapshot()[0]["outcome"] == "sent"
    for malformed in ("not-json{", "["):
        path.write_text(malformed, encoding="utf-8")
        damaged = path.read_bytes()
        with TestCase().assertRaises(json.JSONDecodeError):
            DictationHistory(path=path)
        assert path.read_bytes() == damaged
    for wrong_shape in (None, {}, "history", 42):
        write_json(path, wrong_shape)
        with TestCase().assertRaises(ValueError):
            DictationHistory(path=path)
    for invalid in (None, [], "bad", 4):
        write_json(path, [invalid])
        with TestCase().assertRaises(ValueError):
            DictationHistory(path=path)
    valid_entry = {**legacy[0], "id": "valid-id", "outcome": "inserted"}
    for field, invalid in (("raw", 4), ("polished", None), ("app", []), ("timestamp", 42),
                           ("id", ""), ("id", False), ("outcome", "unknown")):
        write_json(path, [{**valid_entry, field: invalid}])
        with TestCase().assertRaises(ValueError):
            DictationHistory(path=path)
    for duration in ("broken", True, -1, float("nan"), float("inf"), float("-inf")):
        write_json(path, [{**valid_entry, "duration": duration}])
        with TestCase().assertRaises(ValueError):
            DictationHistory(path=path)
        with TestCase().assertRaises(ValueError):
            history.add("raw", "final", duration_sec=duration)
    write_json(path, [valid_entry, valid_entry])
    with TestCase().assertRaises(ValueError):
        DictationHistory(path=path)
    for max_entries in (0, -1, True, 1.5, "2"):
        with TestCase().assertRaises(ValueError):
            DictationHistory(max_entries=max_entries, path=run_dir / "history" / "invalid-cap.json")


def run_worker(run_dir, suites):
    from speaktype import __version__

    assert run_dir.is_relative_to(REPO / "work")
    assert os.environ["SPEAKTYPE_CONFIG_DIR"] == str(run_dir / "config")
    if BUNDLE:
        assert Path(sys.prefix).resolve().is_relative_to(Path(BUNDLE).resolve())
    started = datetime.now(timezone.utc).isoformat()
    passed = []
    available = {name: globals()[f"validate_{name}"] for name in SUITE_NAMES}
    for name in suites:
        available[name](run_dir)
        passed.append(name)
        print(f"PASS {name}", flush=True)
    module_paths = {name: Path(sys.modules[f"speaktype.{name}"].__file__).resolve()
                    for name in ("context", *suites) if f"speaktype.{name}" in sys.modules}
    if BUNDLE:
        assert all(path.is_relative_to(Path(BUNDLE).resolve()) for path in module_paths.values())
    report = {"started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
              "python": sys.version, "executable": sys.executable,
              "runtime": BUNDLE or "source", "prefix": sys.prefix,
              "app_version": __version__,
              "config_dir": os.environ["SPEAKTYPE_CONFIG_DIR"],
              "suites_passed": passed, "suite_count": len(passed),
              "module_paths": {name: str(path) for name, path in module_paths.items()},
              "source_sha256": {str(path): sha256(path.read_bytes()).hexdigest()
                                for path in [Path(__file__).resolve(), *module_paths.values()]},
              "method": "real isolated files and production functions; no mocks or monkeypatches"}
    write_json(run_dir / "report.json", report)
    print(f"REPORT {run_dir / 'report.json'}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Validate real SpeakType core logic with isolated files.")
    parser.add_argument("--suite", choices=SUITE_NAMES, action="append")
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    suites = args.suite or SUITE_NAMES
    if args.worker is not None:
        run_worker(args.worker.resolve(), suites)
        return
    if BUNDLE:
        parser.error("Bundled validation requires --worker and an isolated SPEAKTYPE_CONFIG_DIR")
    run_dir = REPO / "work" / "core-validation" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    run_dir.mkdir(parents=True)
    scratch = run_dir / "scratch"
    scratch.mkdir()
    environment = {**os.environ, "SPEAKTYPE_CONFIG_DIR": str(run_dir / "config"),
                   "SPEAKTYPE_VALIDATION_MARKER": "real-process-environment-🧪",
                   "TMPDIR": str(scratch), "PYTHONPATH": str(REPO)}
    environment.pop("SPEAKTYPE_VALIDATION_MISSING_VARIABLE", None)
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", str(run_dir)]
    for suite in suites:
        command.extend(["--suite", suite])
    print(f"RUN {run_dir}", flush=True)
    subprocess.run(command, cwd=REPO, env=environment, check=True)


if __name__ == "__main__":
    main()
