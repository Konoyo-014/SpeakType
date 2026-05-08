"""Tests for short post-insert edit observation helpers."""

import time
from types import SimpleNamespace

from speaktype.edit_observer import (
    PostInsertEditObserver,
    extract_edited_insert_text,
    locate_insert_span,
)
from speaktype.inserter import FocusedTextSnapshot


def test_locate_insert_span_uses_last_occurrence():
    assert locate_insert_span("hello hello", "hello") == (6, 11)


def test_extract_edited_insert_text_returns_span_revision():
    initial = "prefix cute three asr suffix"
    span = locate_insert_span(initial, "cute three asr")

    edited = extract_edited_insert_text(
        initial_value=initial,
        current_value="prefix Qwen3-ASR suffix",
        inserted_text="cute three asr",
        span_start=span[0],
        span_end=span[1],
    )

    assert edited == "Qwen3-ASR"


def test_extract_edited_insert_text_ignores_pure_append():
    initial = "prefix hello"
    span = locate_insert_span(initial, "hello")

    assert extract_edited_insert_text(
        initial_value=initial,
        current_value="prefix hello world",
        inserted_text="hello",
        span_start=span[0],
        span_end=span[1],
    ) is None


def test_observer_emits_stable_edit():
    values = iter([
        "prefix cute three asr suffix",
        "prefix Qwen3-ASR suffix",
        "prefix Qwen3-ASR suffix",
        "prefix Qwen3-ASR suffix",
    ])
    observed = []

    def capture():
        return FocusedTextSnapshot(has_focused_element=True, value=next(values))

    observer = PostInsertEditObserver(
        capture_snapshot=capture,
        active_app_getter=lambda: {"bundle_id": "com.openai.codex"},
        observation_seconds=2,
        stable_seconds=0.05,
        poll_interval=0.02,
    )
    started = observer.start(
        raw_text="cute three asr",
        inserted_text="cute three asr",
        app_info={"name": "Codex", "bundle_id": "com.openai.codex"},
        scene="code",
        language="en",
        on_edit=observed.append,
    )

    deadline = time.time() + 1
    while not observed and time.time() < deadline:
        time.sleep(0.02)

    assert started is True
    assert observed
    assert observed[0].edited_text == "Qwen3-ASR"
    assert observed[0].scene == "code"


def test_observer_configure_updates_timing():
    observer = PostInsertEditObserver(observation_seconds=18, stable_seconds=1.2)

    observer.configure(observation_seconds=6, stable_seconds=0.4)

    assert observer._observation_seconds == 6
    assert observer._stable_seconds == 0.4
