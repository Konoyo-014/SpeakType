from dataclasses import dataclass, field
from multiprocessing import Pipe
from multiprocessing.connection import Connection
import os
from pathlib import Path
import subprocess
import sys
import time
import threading
import tempfile
import logging
from uuid import uuid4
from typing import Callable
import numpy as np
from .sounddevice_compat import prepare_sounddevice_import
from .whisper_detect import WhisperDetector
from .config import get_temp_dir
from .runtime import get_running_bundle_path

prepare_sounddevice_import()
import sounddevice as sd
import soundfile as sf

logger = logging.getLogger("speaktype.audio")

START_TIMEOUT_SECONDS = 8.0
STOP_TIMEOUT_SECONDS = 3.0
_IGNORED_CAPTURE = object()
# When whisper mode kicked in at any point during a recording, accept
# audio with a lower overall peak — the gain boost may not be enough to
# clear the normal threshold for very short whispers.
MIN_PEAK_NORMAL = 0.005
MIN_PEAK_WHISPER = 0.0015
EDGE_TRIM_FRAME_SECONDS = 0.02
EDGE_TRIM_PADDING_SECONDS = 0.16
EDGE_TRIM_MIN_AUDIO_SECONDS = 0.8
EDGE_TRIM_MIN_SAVED_SECONDS = 0.2
EDGE_TRIM_RATIO_NORMAL = 0.035
EDGE_TRIM_RATIO_WHISPER = 0.018
EDGE_TRIM_FLOOR_NORMAL = 0.001
EDGE_TRIM_FLOOR_WHISPER = 0.0004
TAIL_QUIET_SECONDS = 0.35
# Keep final ASR on the full captured buffer. Short Mandarin phrases can lose
# enough acoustic context from edge trimming to bias Qwen toward near-homophones.
FINAL_ASR_EDGE_TRIM_ENABLED = False


@dataclass
class _CaptureSession:
    connection: Connection
    cancellation: threading.Event
    stop_event: threading.Event = field(default_factory=threading.Event)
    on_error: Callable[[Exception], None] | None = None
    ready: threading.Event = field(default_factory=threading.Event)
    stopped: threading.Event = field(default_factory=threading.Event)
    cleanup_lock: threading.Lock = field(default_factory=threading.Lock)
    process: subprocess.Popen | None = None
    reader: threading.Thread | None = None
    started: bool = False
    start_accepted: bool = False
    cancel_requested: bool = False
    stop_requested: bool = False
    clean_stop: bool = False
    error: Exception | None = None
    device_info: dict | None = None

    def is_cancelled(self):
        return self.cancellation.is_set() or self.stop_event.is_set()


def _capture_command(descriptor: int) -> list[str]:
    bundle = get_running_bundle_path()
    if bundle:
        executable = Path(bundle) / "Contents" / "MacOS" / "audio_capture_worker"
        if not executable.is_file():
            raise FileNotFoundError(f"Microphone worker is missing: {executable}")
        return [str(executable), "--connection-fd", str(descriptor)]
    return [sys.executable, str(Path(__file__).with_name("audio_capture_worker.py")),
            "--connection-fd", str(descriptor)]


class AudioRecorder:
    def __init__(self, sample_rate=16000, device=None, whisper_mode_enabled=True, *,
                 start_timeout_seconds=START_TIMEOUT_SECONDS, stop_timeout_seconds=STOP_TIMEOUT_SECONDS):
        self.sample_rate = sample_rate
        self.device = device  # None = system default, int = device index, str = device name
        self.whisper_mode_enabled = whisper_mode_enabled
        self.is_recording = False
        self._frames = []
        self._stream = None
        self._lock = threading.RLock()
        self._capture_session = None
        self.start_timeout_seconds = float(start_timeout_seconds)
        self.stop_timeout_seconds = float(stop_timeout_seconds)
        if not np.isfinite(self.start_timeout_seconds) or self.start_timeout_seconds <= 0:
            raise ValueError("Microphone start timeout must be a positive finite number")
        if not np.isfinite(self.stop_timeout_seconds) or self.stop_timeout_seconds <= 0:
            raise ValueError("Microphone stop timeout must be a positive finite number")
        self._capture_log_path = None
        self._stream_callback = None  # Optional external callback for streaming preview
        self._whisper_detector = WhisperDetector()
        self._max_recording_seconds = None  # set per-recording via start()
        self._start_monotonic = 0.0
        self._on_max_duration_reached = None
        self._last_start_error = None
        self._last_capture_error = None
        self._last_stop_reason = None
        self._last_stop_message = ""
        self._last_audio_original_samples = 0
        self._last_audio_trim_start = 0
        self._last_audio_trim_end = 0
        self._last_audio_tail_rms = 0.0
        self._last_audio_tail_quiet = False

    def start(self, max_seconds: float | None = None, on_max_duration=None, *, cancel_event=None, on_error=None):
        if on_error is not None and not callable(on_error):
            raise TypeError("Microphone error callback must be callable")
        cancellation = cancel_event if cancel_event is not None else threading.Event()
        if cancellation.is_set():
            return False
        with self._lock:
            existing = self._capture_session
            if existing is not None:
                if existing.started and self.is_recording:
                    return True
            else:
                parent_connection, child_connection = Pipe(duplex=True)
                session = _CaptureSession(parent_connection, cancellation, on_error=on_error)
                self._capture_session = session
        if existing is not None:
            return self._wait_for_start(existing)
        with self._lock:
            if session is not self._capture_session or cancellation.is_set():
                if session is self._capture_session:
                    self._capture_session = None
                    self.is_recording = False
                    self._last_stop_reason = "cancelled"
                    self._last_stop_message = "Microphone start was cancelled"
                child_connection.close()
                session.connection.close()
                session.ready.set()
                session.stopped.set()
                return False
            self._frames = []
            self._whisper_detector.reset()
            self._max_recording_seconds = max_seconds
            self._on_max_duration_reached = on_max_duration
            self._start_monotonic = 0.0
            self.is_recording = True
            self._last_start_error = None
            self._last_capture_error = None
            self._last_stop_reason = None
            self._last_stop_message = ""
            self._last_audio_original_samples = 0
            self._last_audio_trim_start = 0
            self._last_audio_trim_end = 0
            self._last_audio_tail_rms = 0.0
            self._last_audio_tail_quiet = False

        try:
            log_path = get_temp_dir() / f"audio-device-{uuid4().hex}.log"
            with self._lock:
                if session is self._capture_session:
                    self._capture_log_path = log_path
            with log_path.open("wb") as log:
                process = subprocess.Popen(_capture_command(child_connection.fileno()),
                                           pass_fds=(child_connection.fileno(),),
                                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log,
                                           env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                                                "SPEAKTYPE_AUDIO_CAPTURE_WORKER": "1"})
            session.process = process
            child_connection.close()
            if session.is_cancelled():
                self._cleanup_capture(session, terminate=True)
                return False
            session.connection.send({"sample_rate": self.sample_rate, "device": self.device,
                                     "max_seconds": max_seconds})
            session.reader = threading.Thread(target=self._read_capture, args=(session,),
                                              daemon=True, name="SpeakTypeMicrophoneFrames")
            session.reader.start()
            return self._wait_for_start(session)
        except Exception as error:
            with self._lock:
                if session is self._capture_session:
                    self._last_start_error = error
                    self._last_capture_error = error
                    self._last_stop_reason = "device_start_failed"
                    self._last_stop_message = str(error)
                    self.is_recording = False
                    self._capture_session = None
                    self._max_recording_seconds = None
                    self._on_max_duration_reached = None
                    self._start_monotonic = 0.0
            self._cleanup_capture(session, terminate=True)
            logger.error("Microphone device failed to start: %s", error)
            return False
        finally:
            child_connection.close()

    def _wait_for_start(self, session):
        deadline = time.monotonic() + self.start_timeout_seconds
        timed_out = False
        while not session.ready.wait(0.02):
            if session.is_cancelled():
                break
            if time.monotonic() >= deadline:
                timed_out = True
                break
        with self._lock:
            success = (session is self._capture_session and session.started
                       and not session.is_cancelled() and session.error is None)
            if success:
                session.start_accepted = True
                return True
            if session is self._capture_session:
                cancelled = session.cancellation.is_set() or session.cancel_requested
                if session.error is not None:
                    self._last_start_error = session.error
                elif cancelled:
                    self._last_start_error = RuntimeError("Microphone start was cancelled")
                elif timed_out:
                    self._last_start_error = TimeoutError(
                        f"Microphone device did not start within {self.start_timeout_seconds:g} seconds")
                else:
                    self._last_start_error = RuntimeError("Microphone device stopped before supplying audio")
                self._last_stop_reason = "cancelled" if cancelled else "device_start_failed"
                self._last_capture_error = self._last_start_error
                self._last_stop_message = str(self._last_start_error)
                self.is_recording = False
                self._capture_session = None
                self._max_recording_seconds = None
                self._on_max_duration_reached = None
        self._cleanup_capture(session, terminate=True)
        return False

    def _read_capture(self, session):
        try:
            while not session.is_cancelled():
                event, payload = session.connection.recv()
                if event == "opening":
                    session.device_info = payload
                    logger.info("Opening microphone device: %s", payload["name"])
                elif event == "ready":
                    with self._lock:
                        if session is self._capture_session and not session.is_cancelled():
                            session.started = True
                            self._start_monotonic = time.monotonic()
                    session.ready.set()
                elif event == "audio":
                    if not isinstance(payload, np.ndarray) or payload.dtype != np.float32 or payload.ndim != 2 or payload.shape[1] != 1:
                        raise ValueError("Microphone worker returned invalid audio samples")
                    self._callback(payload, len(payload), None, None, session=session)
                elif event == "limit":
                    with self._lock:
                        callback = None
                        if session is self._capture_session and self._max_recording_seconds is not None:
                            callback = self._on_max_duration_reached
                            self._max_recording_seconds = None
                        session.stop_requested = True
                    if callback is not None:
                        callback()
                elif event == "stopped":
                    session.clean_stop = True
                    break
                elif event == "error":
                    if not isinstance(payload, Exception):
                        raise TypeError("Microphone worker returned an invalid error")
                    raise payload
                else:
                    raise ValueError(f"Unknown microphone worker event: {event}")
        except (EOFError, OSError) as error:
            if not session.is_cancelled() and not session.clean_stop:
                session.error = RuntimeError(f"Microphone worker connection closed: {error}")
        except Exception as error:
            session.error = error
            logger.exception("Microphone frame processing failed")
        finally:
            session.ready.set()
            session.stopped.set()
            notify_error = None
            with self._lock:
                if session is self._capture_session and session.error is not None:
                    self._last_start_error = session.error
                    self._last_capture_error = session.error
                    self._last_stop_reason = "device_error"
                    self._last_stop_message = str(session.error)
                    if session.start_accepted and not session.is_cancelled() and not session.stop_requested:
                        self._capture_session = None
                        self.is_recording = False
                        self._frames = []
                        self._max_recording_seconds = None
                        self._on_max_duration_reached = None
                        notify_error = session.on_error
            if session.error is not None:
                try:
                    if notify_error is not None:
                        notify_error(session.error)
                finally:
                    self._cleanup_capture(session, terminate=True)

    @staticmethod
    def _signal_capture_termination(session):
        process = session.process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass

    def _cleanup_capture(self, session, *, terminate):
        with session.cleanup_lock:
            process = session.process
            if terminate:
                session.stop_event.set()
                self._signal_capture_termination(session)
            if process is not None:
                try:
                    process.wait(timeout=self.stop_timeout_seconds)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=self.stop_timeout_seconds)
            if session.reader is not None and session.reader is not threading.current_thread():
                session.reader.join(timeout=self.stop_timeout_seconds)
            session.connection.close()
            session.stopped.set()

    def cancel_start(self, *, cancel_event=None):
        with self._lock:
            session = self._capture_session
            if cancel_event is not None and (session is None or session.cancellation is not cancel_event):
                return
            self._capture_session = None
            self.is_recording = False
            self._frames = []
            self._max_recording_seconds = None
            self._on_max_duration_reached = None
            self._start_monotonic = 0.0
            self._last_stop_reason = "cancelled"
            self._last_stop_message = "Microphone capture was cancelled"
            if session is not None:
                session.cancel_requested = True
                session.stop_event.set()
        if session is not None:
            self._signal_capture_termination(session)
            threading.Thread(target=self._cleanup_capture, args=(session,), kwargs={"terminate": True},
                             daemon=True, name="SpeakTypeMicrophoneCancel").start()

    def _resolve_device(self):
        """Resolve the configured device to a device index."""
        if self.device is None:
            return None
        if isinstance(self.device, int):
            return self.device
        if isinstance(self.device, str):
            from .devices import get_device_by_name
            return get_device_by_name(self.device)
        return None

    def set_stream_callback(self, callback):
        """Set an external callback that receives each audio chunk for streaming preview."""
        self._stream_callback = callback

    def set_whisper_state_callback(self, callback):
        """Register a callback fired when the whisper detector changes state."""
        self._whisper_detector.set_state_callback(callback)

    @property
    def whisper_state(self) -> str:
        return self._whisper_detector.state

    @property
    def whisper_active(self) -> bool:
        return self._whisper_detector.is_whisper

    @property
    def whisper_was_active(self) -> bool:
        return self._whisper_detector.was_active

    @property
    def last_start_error(self):
        return self._last_start_error

    @property
    def last_error(self):
        return self._last_capture_error

    @property
    def last_stop_reason(self):
        return self._last_stop_reason

    @property
    def last_stop_message(self):
        return self._last_stop_message

    @property
    def last_audio_original_samples(self) -> int:
        return self._last_audio_original_samples

    @property
    def last_audio_trim_start(self) -> int:
        return self._last_audio_trim_start

    @property
    def last_audio_trim_end(self) -> int:
        return self._last_audio_trim_end

    @property
    def last_audio_tail_rms(self) -> float:
        return self._last_audio_tail_rms

    @property
    def last_audio_tail_quiet(self) -> bool:
        return self._last_audio_tail_quiet

    def _callback(self, indata, frames, time_info, status, *, session=None):
        with self._lock:
            if not self.is_recording or (session is not None and session is not self._capture_session):
                return
            chunk = indata.copy()
            if self.whisper_mode_enabled:
                raw_peak = float(np.max(np.abs(chunk)))
                self._whisper_detector.feed_chunk(raw_peak)
                gain = self._whisper_detector.gain_factor()
                if gain > 1.0:
                    chunk = np.clip(chunk * gain, -1.0, 1.0)
            self._frames.append(chunk)
            callback = None
            if self._max_recording_seconds is not None and time.monotonic() - self._start_monotonic >= self._max_recording_seconds:
                callback = self._on_max_duration_reached
                self._max_recording_seconds = None
            stream_callback = self._stream_callback
        if callback is not None:
            callback()
        if stream_callback is not None:
            stream_callback(chunk)

    def stop(self, *, cancel_event=None) -> str | None:
        """Stop recording and return path to WAV file, or None if no audio."""
        audio_data = self.stop_audio(cancel_event=cancel_event)
        if audio_data is None:
            return None

        tmp = tempfile.NamedTemporaryFile(dir=get_temp_dir(), suffix=".wav", delete=False)
        sf.write(tmp.name, audio_data, self.sample_rate)
        tmp.close()
        return tmp.name

    def stop_audio(self, *, cancel_event=None):
        """Stop recording and return validated audio data, or None if unusable."""
        frames = self._finish_recording(cancel_event=cancel_event)
        if frames is _IGNORED_CAPTURE:
            return None
        with self._lock:
            if self._capture_session is not None:
                return None
            return self._finalize_audio(frames)

    def _finish_recording(self, *, cancel_event=None):
        with self._lock:
            session = self._capture_session
            if cancel_event is not None and (session is None or session.cancellation is not cancel_event):
                return _IGNORED_CAPTURE
            if not self.is_recording:
                self._last_stop_reason = "not_recording"
                self._last_stop_message = "Recorder was not active when stop was requested"
                return None
            if session is None:
                self.is_recording = False
                self._last_stop_reason = "device_session_missing"
                self._last_stop_message = "Microphone capture session is unavailable"
                self._frames = []
                return None
            starting = not session.started
            first_stop = not session.stop_requested
            session.stop_requested = True
            self._max_recording_seconds = None
            self._on_max_duration_reached = None
        if starting:
            self.cancel_start(cancel_event=session.cancellation)
            return None
        if first_stop and not session.stopped.is_set():
            try:
                session.connection.send(("stop", None))
            except (BrokenPipeError, EOFError, OSError) as error:
                session.error = error
        if session.reader is not threading.current_thread():
            session.stopped.wait(timeout=self.stop_timeout_seconds)
        complete = session.clean_stop and session.error is None
        self._cleanup_capture(session, terminate=not complete)
        with self._lock:
            if session is not self._capture_session:
                return _IGNORED_CAPTURE
            self.is_recording = False
            self._capture_session = None
            frames = list(self._frames)
            self._frames = []
            if not complete:
                self._last_capture_error = session.error or TimeoutError(
                    "Microphone device did not finish stopping before the timeout")
                self._last_stop_reason = "device_stop_failed"
                self._last_stop_message = str(self._last_capture_error)
                return None
        return frames

    def _finalize_audio(self, frames):
        if not frames:
            logger.warning("No audio frames captured at all")
            if not self._last_stop_reason:
                self._last_stop_reason = "no_frames"
                self._last_stop_message = "No audio frames were captured"
            return None

        audio_data = np.concatenate(frames, axis=0).flatten()
        duration = len(audio_data) / self.sample_rate
        peak = float(np.max(np.abs(audio_data)))
        whisper_was_active = self._whisper_detector.was_active
        self._last_audio_original_samples = len(audio_data)
        self._last_audio_trim_start = 0
        self._last_audio_trim_end = len(audio_data)
        self._last_audio_tail_rms = _tail_rms(audio_data, self.sample_rate)
        self._last_audio_tail_quiet = _is_quiet_edge(
            self._last_audio_tail_rms,
            peak,
            whisper_was_active,
        )
        logger.info(
            f"Audio: {len(frames)} frames, {duration:.1f}s, peak={peak:.4f}, whisper={whisper_was_active}"
        )

        if len(audio_data) < self.sample_rate * 0.3:
            logger.warning(f"Audio too short: {duration:.2f}s < 0.3s")
            self._last_stop_reason = "too_short"
            self._last_stop_message = f"Recording was too short ({duration:.2f}s)"
            return None

        min_peak = MIN_PEAK_WHISPER if whisper_was_active else MIN_PEAK_NORMAL
        if peak < min_peak:
            logger.warning(f"Audio too quiet: peak={peak:.4f} < {min_peak}")
            self._last_stop_reason = "too_quiet"
            self._last_stop_message = f"Audio peak was too quiet ({peak:.4f})"
            return None

        self._last_stop_reason = None
        self._last_stop_message = ""
        if FINAL_ASR_EDGE_TRIM_ENABLED:
            trimmed, trim_start, trim_end = _trim_silence_edges(
                audio_data,
                self.sample_rate,
                peak,
                whisper_was_active,
            )
            self._last_audio_trim_start = trim_start
            self._last_audio_trim_end = trim_end
            if len(trimmed) != len(audio_data):
                logger.info(
                    "Trimmed quiet recording edges: %.3fs -> %.3fs (start=%.3fs end=%.3fs)",
                    duration,
                    len(trimmed) / self.sample_rate,
                    trim_start / self.sample_rate,
                    (len(audio_data) - trim_end) / self.sample_rate,
                )
            return trimmed

        return audio_data

    def get_level(self) -> float:
        """Get current audio level (0.0 to 1.0) for visual feedback."""
        try:
            if self._frames:
                last = self._frames[-1]
                return float(np.clip(np.max(np.abs(last)) * 5, 0, 1))
        except (IndexError, ValueError):
            pass
        return 0.0


def _edge_trim_threshold(peak: float, whisper_was_active: bool) -> float:
    ratio = EDGE_TRIM_RATIO_WHISPER if whisper_was_active else EDGE_TRIM_RATIO_NORMAL
    floor = EDGE_TRIM_FLOOR_WHISPER if whisper_was_active else EDGE_TRIM_FLOOR_NORMAL
    return max(float(peak) * ratio, floor)


def _is_quiet_edge(rms: float, peak: float, whisper_was_active: bool) -> bool:
    return float(rms) <= _edge_trim_threshold(peak, whisper_was_active)


def _tail_rms(audio_data, sample_rate: int) -> float:
    samples = int(sample_rate * TAIL_QUIET_SECONDS)
    if samples <= 0 or len(audio_data) == 0:
        return 0.0
    tail = audio_data[-min(samples, len(audio_data)):]
    return float(np.sqrt(np.mean(np.square(tail)))) if len(tail) else 0.0


def _trim_silence_edges(audio_data, sample_rate: int, peak: float, whisper_was_active: bool):
    if len(audio_data) < int(sample_rate * EDGE_TRIM_MIN_AUDIO_SECONDS):
        return audio_data, 0, len(audio_data)

    frame_size = max(1, int(sample_rate * EDGE_TRIM_FRAME_SECONDS))
    threshold = _edge_trim_threshold(peak, whisper_was_active)
    active_frames = []
    for start in range(0, len(audio_data), frame_size):
        frame = audio_data[start:start + frame_size]
        if len(frame) == 0:
            continue
        rms = float(np.sqrt(np.mean(np.square(frame))))
        if rms > threshold:
            active_frames.append((start, min(start + frame_size, len(audio_data))))

    if not active_frames:
        return audio_data, 0, len(audio_data)

    padding = int(sample_rate * EDGE_TRIM_PADDING_SECONDS)
    trim_start = max(0, active_frames[0][0] - padding)
    trim_end = min(len(audio_data), active_frames[-1][1] + padding)
    if len(audio_data) - (trim_end - trim_start) < int(sample_rate * EDGE_TRIM_MIN_SAVED_SECONDS):
        return audio_data, 0, len(audio_data)
    if trim_end - trim_start < int(sample_rate * 0.3):
        return audio_data, 0, len(audio_data)
    return audio_data[trim_start:trim_end], trim_start, trim_end
