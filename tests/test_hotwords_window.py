import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from speaktype.hotwords_window import (
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


def test_hotword_window_rows_filter_learning_state_and_alias():
    entries = [{"term": "CandidateTerm", "active": False, "aliases": ["candidate term"]},
               {"term": "DisabledTerm", "active": False, "user_disabled": True}]
    rows = hotword_window_rows(entries, query="candidate term", filter_id="pending")

    assert [row["term"] for row in rows] == ["CandidateTerm"]
    assert hotword_window_rows(entries, filter_id="disabled")[0]["term"] == "DisabledTerm"


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

    assert text == "mlx-audio Qwen3-ASR"


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
    assert state["text"] == "mlx-audio Qwen3-ASR"
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


def test_hotword_reveal_feedback_distinguishes_file_and_folder():
    assert hotword_reveal_feedback(True) != hotword_reveal_feedback(False)
    assert hotword_reveal_feedback(True)
    assert hotword_reveal_feedback(False)


def test_native_vocabulary_workspace_uses_real_controls_and_persistence():
    root = Path(__file__).resolve().parents[1]
    run_dir = root / "work" / "pytest-vocabulary" / uuid4().hex
    temporary = run_dir / "temporary"
    temporary.mkdir(parents=True)
    environment = {**os.environ, "SPEAKTYPE_CONFIG_DIR": str(run_dir / "config"),
                   "TMPDIR": str(temporary), "PYTHONDONTWRITEBYTECODE": "1"}
    subprocess.run([sys.executable, str(root / "scripts" / "validate_vocabulary_workspace.py")],
                   cwd=root, env=environment, check=True, capture_output=True, text=True, timeout=180)
    report_path = root / "work" / "vocabulary-validation" / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["runtime"] == "source"
    assert report["callback_count"] > 0
    assert report["checks"]
    assert all(Path(path).is_file() for path in report["artifacts"])
