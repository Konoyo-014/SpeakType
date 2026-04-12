"""Streaming transcription pipeline.

Runs the ASR model on audio chunks while the user is still recording so
the unified status overlay can show partial results in real time. The
transcriber is intentionally UI-agnostic — it pushes partial text into
a callback supplied by the caller (typically StatusOverlay.update_partial_text).
"""

import logging
import threading
import time

logger = logging.getLogger("speaktype.streaming")

# Minimum seconds between transcription updates. Lower = snappier preview
# but more CPU. mlx-audio takes ~0.3-0.6s per call on M-series, so 0.9s
# leaves headroom and avoids piling up calls behind each other.
DEFAULT_INTERVAL = 0.6
# Minimum audio buffer length (seconds) before we attempt a transcription.
MIN_BUFFER_SECONDS = 0.25
# Sample rate the audio recorder uses.
DEFAULT_SAMPLE_RATE = 16000


class StreamingTranscriber:
    """Drives partial ASR transcription from a live audio buffer.

    Usage:
        transcriber = StreamingTranscriber(asr_engine, on_partial_text=callback)
        recorder.set_stream_callback(transcriber.feed_audio)
        transcriber.start(language="auto")
        ...
        final = transcriber.stop()
    """

    def __init__(
        self,
        asr_engine,
        on_partial_text=None,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        interval: float = DEFAULT_INTERVAL,
    ):
        self._asr = asr_engine
        self._on_partial_text = on_partial_text
        self._sample_rate = sample_rate
        self._interval = interval
        self._lock = threading.Lock()
        self._audio_buffer = []
        self._running = False
        self._thread = None
        self._accumulated_text = ""
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------ #
    # Lifecycle                                                          #
    # ------------------------------------------------------------------ #

    def start(self, language: str = "auto"):
        """Start the background streaming loop."""
        with self._lock:
            self._audio_buffer = []
            self._accumulated_text = ""
            self._running = True
            self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._stream_loop,
            args=(language,),
            daemon=True,
        )
        self._thread.start()

    def stop(self, wait: bool = True) -> str:
        """Stop the loop and return the most recent partial transcript."""
        self._running = False
        self._stop_event.set()
        self._on_partial_text = None
        thread = self._thread
        if wait and thread:
            thread.join(timeout=3)
        self._thread = None
        return self._accumulated_text

    def feed_audio(self, audio_chunk):
        """Feed an audio chunk (numpy array) into the streaming buffer."""
        if audio_chunk is None:
            return
        with self._lock:
            self._audio_buffer.append(audio_chunk.copy())

    @property
    def accumulated_text(self) -> str:
        return self._accumulated_text

    # ------------------------------------------------------------------ #
    # Internal loop                                                       #
    # ------------------------------------------------------------------ #

    def _stream_loop(self, language: str):
        """Background loop that runs partial transcriptions periodically."""
        try:
            import numpy as np  # local import; avoids module-load cost on cold paths
        except Exception as e:
            logger.error(f"numpy import failed in streaming loop: {e}")
            return

        if not getattr(self._asr, "_loaded", False):
            logger.debug("Streaming aborted: ASR engine not loaded")
            return

        model = getattr(self._asr, "model", None)
        has_native_stream = _should_use_native_stream(self._asr, model)

        last_run_at = 0.0
        min_samples = int(self._sample_rate * MIN_BUFFER_SECONDS)

        while self._running:
            if self._stop_event.wait(0.08):
                break
            now = time.time()
            if now - last_run_at < self._interval:
                continue

            with self._lock:
                if not self._audio_buffer:
                    continue
                audio_data = np.concatenate(self._audio_buffer, axis=0).flatten()

            if len(audio_data) < min_samples:
                continue

            last_run_at = now

            try:
                if has_native_stream:
                    self._run_native_stream(model, audio_data, language)
                else:
                    self._run_chunked(audio_data, language)
            except Exception as e:
                logger.debug(f"Partial transcription failed: {e}")

    def _run_native_stream(self, model, audio_data, language: str):
        """Use the model's own streaming API when available.

        mlx-audio's ``stream_transcribe`` yields one decoded token at a
        time as a delta, not a cumulative transcript. We accumulate the
        deltas locally so the UI sees a growing string instead of one
        character flashing in the bubble at a time.
        """
        kwargs = {"audio": audio_data, "max_tokens": 8192}
        if language and language != "auto":
            kwargs["language"] = language

        if not self._acquire_preview_slot():
            return
        try:
            accumulated_parts: list[str] = []
            for result in model.stream_transcribe(**kwargs):
                if not self._running:
                    return
                # The final marker for each chunk yields an empty text with
                # is_final=True; ignore those entirely.
                text = _extract_text(result)
                if not text:
                    continue
                accumulated_parts.append(text)
                self._emit_partial("".join(accumulated_parts))
        finally:
            self._release_preview_slot()

    def _run_chunked(self, audio_data, language: str):
        """Fallback path: re-run full transcription on the buffer so far."""
        if getattr(self._asr, "backend", "qwen") != "qwen":
            logger.debug(
                "Skipping chunked streaming preview for unsupported backend: %s",
                getattr(self._asr, "backend", "unknown"),
            )
            return

        try:
            from mlx_audio.stt.generate import generate_transcription
            from .asr import _cleanup_transcript_outputs, _make_temp_transcript_output_path
        except Exception as e:
            logger.debug(f"mlx_audio not available for chunked streaming: {e}")
            return

        if not self._acquire_preview_slot():
            return

        output_path = _make_temp_transcript_output_path()
        kwargs = {
            "model": self._asr.model,
            "audio": audio_data,
            "output_path": output_path,
            "verbose": False,
        }
        if language and language != "auto":
            kwargs["language"] = language

        try:
            result = generate_transcription(**kwargs)
        finally:
            _cleanup_transcript_outputs(output_path)
            self._release_preview_slot()
        text = _extract_text(result)
        if text:
            self._emit_partial(text)

    def _acquire_preview_slot(self) -> bool:
        acquire = getattr(self._asr, "acquire_inference", None)
        if not callable(acquire):
            return True
        if acquire(blocking=False):
            return True
        logger.debug("Skipping streaming preview pass because ASR inference is busy")
        return False

    def _release_preview_slot(self):
        release = getattr(self._asr, "release_inference", None)
        if callable(release):
            release()

    def _emit_partial(self, text: str):
        if not text:
            return
        text = text.strip()
        if not text:
            return
        # Anti-flicker: keep emitted text monotonically growing. Each
        # call to ``_run_native_stream`` decodes the entire audio buffer
        # from scratch, so the FIRST few tokens of every new pass are
        # shorter than what we already showed for the previous pass.
        # If we forwarded those, the bubble would briefly collapse back
        # to "Hi" / "Hello" before climbing back up. Drop them — once
        # the new pass exceeds the previous length we resume emitting.
        if self._accumulated_text and len(text) < len(self._accumulated_text):
            return
        self._accumulated_text = text
        if self._on_partial_text is not None:
            try:
                self._on_partial_text(text)
            except Exception as e:
                logger.debug(f"on_partial_text callback failed: {e}")


def _extract_text(result) -> str:
    """Best-effort extraction of a text payload from various result shapes."""
    if result is None:
        return ""
    text = getattr(result, "text", None)
    if isinstance(text, str):
        return text
    if isinstance(result, dict):
        return str(result.get("text", "") or "")
    if isinstance(result, str):
        return result
    return ""


def _should_use_native_stream(asr_engine, model) -> bool:
    """Return whether native token streaming is safe for preview display.

    Qwen/MLX final transcription decodes full text correctly, but its native
    token-delta stream can expose transient replacement glyphs for CJK text.
    Use chunked full-buffer preview for Qwen so the overlay sees the same
    Unicode decoding path as final transcription.
    """
    if not hasattr(model, "stream_transcribe"):
        return False
    return getattr(asr_engine, "backend", "qwen") != "qwen"
