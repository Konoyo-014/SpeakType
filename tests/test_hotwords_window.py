from speaktype import hotwords_window
from speaktype.hotwords_window import (
    HotwordsWindowController,
    active_hotword_context_copy_state,
    active_hotword_context_text,
    hotword_reveal_feedback,
    hotword_row_detail,
    hotword_row_metrics,
    hotword_rows_document_height,
    hotword_window_rows,
)


def test_hotword_window_rows_sort_active_terms_first():
    rows = hotword_window_rows(
        [
            {
                "term": "CandidateTerm",
                "active": False,
                "confidence": 0.95,
                "observations": 5,
                "updated_at": "2026-05-07T10:00:00+00:00",
            },
            {
                "term": "Qwen3-ASR",
                "active": True,
                "confidence": 0.81,
                "observations": 2,
                "aliases": ["cute three asr"],
                "apps": {"com.openai.codex": 2},
                "updated_at": "2026-05-06T10:00:00+00:00",
            },
        ]
    )

    assert [row["term"] for row in rows] == ["Qwen3-ASR", "CandidateTerm"]
    assert rows[0]["confidence"] == "81%"
    assert rows[0]["aliases"] == "cute three asr"
    assert rows[0]["apps"] == "com.openai.codex"
    assert rows[0]["updated"] == "2026-05-06"


def test_hotword_window_rows_skip_empty_terms():
    rows = hotword_window_rows([{"term": ""}, {"term": "mlx-audio", "confidence": 0.9}])

    assert [row["term"] for row in rows] == ["mlx-audio"]


def test_hotword_row_metrics_expand_for_long_detail():
    row = {
        "term": "TransformerEngineMetalPerformanceShadersLongIdentifier",
        "active": True,
        "confidence": "88%",
        "observations": 4,
        "updated": "2026-05-06",
        "aliases": "transformer engine metal performance shaders, te mps",
        "apps": "com.apple.Terminal, com.microsoft.VSCode",
    }

    detail = hotword_row_detail(row)
    metrics = hotword_row_metrics(row, width=652)

    assert "com.microsoft.VSCode" in detail
    assert metrics["row_height"] > 92
    assert metrics["detail_height"] >= 36


def test_active_hotword_context_text_copies_active_terms_only():
    text = active_hotword_context_text(
        [
            {"term": "Candidate", "active": False, "confidence": 0.99},
            {"term": "Qwen3-ASR", "active": True, "confidence": 0.9},
            {"term": "mlx-audio", "active": True, "confidence": 0.8},
        ]
    )

    assert text == "Qwen3-ASR mlx-audio"


def test_active_hotword_context_copy_state_skips_empty_clipboard_write():
    state = active_hotword_context_copy_state(
        [
            {"term": "Candidate", "active": False, "confidence": 0.99},
            {"term": "DraftOnly", "active": False, "confidence": 0.2},
        ]
    )

    assert state["should_copy"] is False
    assert state["text"] == ""
    assert state["count"] == 0
    assert state["feedback"]


def test_active_hotword_context_copy_state_copies_active_terms():
    state = active_hotword_context_copy_state(
        [
            {"term": "Candidate", "active": False, "confidence": 0.99},
            {"term": "Qwen3-ASR", "active": True, "confidence": 0.9},
            {"term": "mlx-audio", "active": True, "confidence": 0.8},
        ]
    )

    assert state["should_copy"] is True
    assert state["text"] == "Qwen3-ASR mlx-audio"
    assert state["count"] == 2


def test_hotword_rows_document_height_resets_for_empty_rows():
    rows = hotword_window_rows(
        {
            "term": f"LongActiveTerm{i}" * 8,
            "active": i % 2 == 0,
            "confidence": 0.91,
            "observations": 12 - i,
            "aliases": ["long alias" * 8],
            "apps": {"com.apple.Terminal": 10, "com.openai.codex": 7},
        }
        for i in range(6)
    )

    assert hotword_rows_document_height(rows) > 368
    assert hotword_rows_document_height([]) == 368


class _FakeFeedbackField:
    def __init__(self):
        self.value = "stale copy feedback"
        self.color = None

    def setStringValue_(self, value):
        self.value = value

    def setTextColor_(self, value):
        self.color = value


def test_hotwords_refresh_clears_stale_copy_feedback(monkeypatch):
    class EmptyStore:
        def get_all(self):
            return []

    controller = HotwordsWindowController(EmptyStore())
    controller._copy_feedback_field = _FakeFeedbackField()
    rendered = []
    controller._render = lambda: rendered.append(list(controller._last_entries))

    controller.refresh()

    assert controller._copy_feedback_field.value == ""
    assert controller._copy_feedback_field.color is not None
    assert rendered == [[]]


def test_hotword_reveal_feedback_distinguishes_file_and_folder():
    assert hotword_reveal_feedback(True) != hotword_reveal_feedback(False)
    assert hotword_reveal_feedback(True)
    assert hotword_reveal_feedback(False)


def test_hotwords_reveal_store_reports_config_folder_when_file_missing(monkeypatch, tmp_path):
    calls = []
    missing_file = tmp_path / "hotwords.json"

    monkeypatch.setattr(hotwords_window, "HOTWORDS_FILE", missing_file)
    monkeypatch.setattr(hotwords_window, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(hotwords_window, "ensure_config_dir", lambda: calls.append(("ensure",)))
    monkeypatch.setattr(hotwords_window.subprocess, "run", lambda cmd: calls.append(tuple(cmd)))

    controller = HotwordsWindowController()
    controller._copy_feedback_field = _FakeFeedbackField()

    controller.reveal_store()

    assert ("ensure",) in calls
    assert ("open", str(tmp_path)) in calls
    assert controller._copy_feedback_field.value == hotword_reveal_feedback(False)
