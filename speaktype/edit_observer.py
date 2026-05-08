"""Short-lived observation of user edits to SpeakType's own insertion."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import threading
import time
from typing import Callable, Optional

from .context import get_active_app
from .inserter import FocusedTextSnapshot, capture_focused_text_snapshot

logger = logging.getLogger("speaktype.edit_observer")

DEFAULT_OBSERVATION_SECONDS = 18.0
DEFAULT_POLL_INTERVAL = 0.35
DEFAULT_STABLE_SECONDS = 1.2
MAX_EDITED_TEXT_CHARS = 2000


@dataclass(frozen=True)
class EditObservation:
    """A local edit made to the last SpeakType insertion."""

    raw_text: str
    inserted_text: str
    edited_text: str
    app_info: dict
    scene: str = ""
    language: str = "auto"


@dataclass(frozen=True)
class _Session:
    raw_text: str
    inserted_text: str
    app_info: dict
    scene: str
    language: str
    initial_value: str
    span_start: int
    span_end: int
    cancel: threading.Event


def locate_insert_span(container: str, inserted_text: str) -> tuple[int, int] | None:
    """Find the most likely span for the inserted text in an AXValue string."""
    if not container or not inserted_text:
        return None
    start = container.rfind(inserted_text)
    if start < 0:
        return None
    return start, start + len(inserted_text)


def extract_edited_insert_text(
    *,
    initial_value: str,
    current_value: str,
    inserted_text: str,
    span_start: int,
    span_end: int,
) -> str | None:
    """Return the revised inserted text when the edit touches the insert span.

    Pure appends before or after the insertion are ignored; they are normal
    continued typing, not evidence that SpeakType misrecognized a term.
    """
    if current_value == initial_value:
        return None
    if not inserted_text or span_start < 0 or span_end < span_start:
        return None
    if current_value.startswith(initial_value) or current_value.endswith(initial_value):
        return None

    prefix = initial_value[:span_start]
    suffix = initial_value[span_end:]
    if prefix and not current_value.startswith(prefix):
        return None
    if suffix and not current_value.endswith(suffix):
        return None

    middle_start = len(prefix)
    middle_end = len(current_value) - len(suffix) if suffix else len(current_value)
    if middle_end < middle_start:
        return None
    edited = current_value[middle_start:middle_end]
    if edited == inserted_text:
        return None
    if not edited.strip():
        return None
    if len(edited) > MAX_EDITED_TEXT_CHARS:
        return None

    # If the original inserted text still anchors the beginning or end and
    # the only change is extra typing around it, ignore the observation.
    if edited.startswith(inserted_text) or edited.endswith(inserted_text):
        return None
    return edited


class PostInsertEditObserver:
    """Watch only the short window after SpeakType inserts text."""

    def __init__(
        self,
        *,
        capture_snapshot: Callable[[], FocusedTextSnapshot] = capture_focused_text_snapshot,
        active_app_getter: Callable[[], dict] = get_active_app,
        observation_seconds: float = DEFAULT_OBSERVATION_SECONDS,
        stable_seconds: float = DEFAULT_STABLE_SECONDS,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ):
        self._capture_snapshot = capture_snapshot
        self._active_app_getter = active_app_getter
        self._observation_seconds = max(1.0, float(observation_seconds or DEFAULT_OBSERVATION_SECONDS))
        self._stable_seconds = max(0.2, float(stable_seconds or DEFAULT_STABLE_SECONDS))
        self._poll_interval = max(0.1, float(poll_interval or DEFAULT_POLL_INTERVAL))
        self._lock = threading.Lock()
        self._session: Optional[_Session] = None
        self._thread: Optional[threading.Thread] = None

    def cancel(self):
        with self._lock:
            session = self._session
            self._session = None
        if session is not None:
            session.cancel.set()

    def configure(
        self,
        *,
        observation_seconds: float | None = None,
        stable_seconds: float | None = None,
    ):
        """Update timing without replacing the observer instance."""
        if observation_seconds is not None:
            self._observation_seconds = max(
                1.0,
                float(observation_seconds or DEFAULT_OBSERVATION_SECONDS),
            )
        if stable_seconds is not None:
            self._stable_seconds = max(
                0.2,
                float(stable_seconds or DEFAULT_STABLE_SECONDS),
            )

    def start(
        self,
        *,
        raw_text: str,
        inserted_text: str,
        app_info: dict,
        scene: str = "",
        language: str = "auto",
        on_edit: Callable[[EditObservation], None],
    ) -> bool:
        """Start observing the focused field after a successful insertion."""
        self.cancel()
        if not inserted_text:
            return False
        snapshot = self._capture_snapshot()
        if not snapshot.has_focused_element or not isinstance(snapshot.value, str):
            return False
        span = locate_insert_span(snapshot.value, inserted_text)
        if span is None:
            return False

        session = _Session(
            raw_text=raw_text or "",
            inserted_text=inserted_text,
            app_info=dict(app_info or {}),
            scene=scene or "",
            language=language or "auto",
            initial_value=snapshot.value,
            span_start=span[0],
            span_end=span[1],
            cancel=threading.Event(),
        )
        thread = threading.Thread(
            target=self._observe_loop,
            args=(session, on_edit),
            daemon=True,
            name="SpeakTypeEditObserver",
        )
        with self._lock:
            self._session = session
            self._thread = thread
        thread.start()
        return True

    def _observe_loop(self, session: _Session, on_edit: Callable[[EditObservation], None]):
        deadline = time.monotonic() + self._observation_seconds
        last_candidate = None
        candidate_since = 0.0
        while time.monotonic() < deadline and not session.cancel.wait(self._poll_interval):
            if not self._same_frontmost_app(session.app_info):
                break
            snapshot = self._capture_snapshot()
            if not snapshot.has_focused_element or not isinstance(snapshot.value, str):
                break
            candidate = extract_edited_insert_text(
                initial_value=session.initial_value,
                current_value=snapshot.value,
                inserted_text=session.inserted_text,
                span_start=session.span_start,
                span_end=session.span_end,
            )
            if candidate is None:
                continue
            now = time.monotonic()
            if candidate != last_candidate:
                last_candidate = candidate
                candidate_since = now
                continue
            if now - candidate_since < self._stable_seconds:
                continue
            observation = EditObservation(
                raw_text=session.raw_text,
                inserted_text=session.inserted_text,
                edited_text=candidate,
                app_info=session.app_info,
                scene=session.scene,
                language=session.language,
            )
            try:
                on_edit(observation)
            except Exception as e:
                logger.debug("Post-insert edit callback failed: %s", e)
            break

        with self._lock:
            if self._session is session:
                self._session = None

    def _same_frontmost_app(self, original: dict) -> bool:
        original_bundle = str((original or {}).get("bundle_id", "") or "")
        if not original_bundle:
            return True
        try:
            current = self._active_app_getter()
        except Exception as e:
            logger.debug("Could not read active app during edit observation: %s", e)
            return False
        return str((current or {}).get("bundle_id", "") or "") == original_bundle
