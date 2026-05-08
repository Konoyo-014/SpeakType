"""Tests for adaptive hotword learning storage."""

from speaktype.hotwords import HotwordStore, extract_confident_corrections


def test_hotword_store_promotes_high_confidence_term(tmp_path):
    store = HotwordStore(path=tmp_path / "hotwords.json")

    entry = store.add_or_reinforce(
        "Qwen3-ASR",
        aliases=["cute three asr"],
        confidence=0.91,
        app_info={"name": "Codex", "bundle_id": "com.openai.codex"},
        scene="code",
        language="en",
        raw_fragment="cute three asr",
        edited_fragment="Qwen3-ASR",
    )

    assert entry is not None
    assert entry["active"] is True
    assert entry["term"] == "Qwen3-ASR"
    assert entry["aliases"] == ["cute three asr"]
    assert len(store) == 1


def test_hotword_context_filters_and_prioritizes_by_app(tmp_path):
    store = HotwordStore(path=tmp_path / "hotwords.json")
    store.add_or_reinforce(
        "PyObjC",
        confidence=0.9,
        app_info={"name": "Codex", "bundle_id": "com.openai.codex"},
        scene="code",
    )
    store.add_or_reinforce(
        "QuarterlyClose",
        confidence=0.9,
        app_info={"name": "Mail", "bundle_id": "com.apple.mail"},
        scene="email",
    )

    context = store.active_context(
        app_info={"name": "Codex", "bundle_id": "com.openai.codex"},
        scene="code",
        limit=1,
    )

    assert context.terms == ["PyObjC"]
    assert context.context == "PyObjC"


def test_learn_from_payload_persists_hotwords(tmp_path):
    store = HotwordStore(path=tmp_path / "hotwords.json")
    payload = {
        "learn": True,
        "hotwords": [
            {
                "term": "mlx-audio",
                "aliases": ["em el ex audio"],
                "confidence": 0.88,
            }
        ],
    }

    learned = store.learn_from_payload(payload, scene="code", raw_text="em el ex audio", edited_text="mlx-audio")

    assert [entry["term"] for entry in learned] == ["mlx-audio"]
    assert store.active_context(scene="code").context == "mlx-audio"


def test_extract_confident_corrections_filters_weak_pairs():
    payload = {
        "learn": True,
        "corrections": [
            {"wrong": "cute three asr", "right": "Qwen3-ASR", "confidence": 0.91},
            {"wrong": "hi", "right": "High", "confidence": 0.99},
            {"wrong": "maybe", "right": "May B", "confidence": 0.4},
        ],
    }

    assert extract_confident_corrections(payload) == [
        {"wrong": "cute three asr", "right": "Qwen3-ASR", "confidence": 0.91}
    ]
