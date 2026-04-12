"""Audio recording module using sounddevice."""

import time
import threading
import tempfile
import logging
import numpy as np
from .sounddevice_compat import prepare_sounddevice_import
from .whisper_detect import WhisperDetector

prepare_sounddevice_import()
import sounddevice as sd
import soundfile as sf

logger = logging.getLogger("speaktype.audio")

MAX_RETRIES = 3
RETRY_DELAY = 0.3
# When whisper mode kicked in at any point during a recording, accept
# audio with a lower overall peak — the gain boost may not be enough to
# clear the normal threshold for very short whispers.
MIN_PEAK_NORMAL = 0.005
MIN_PEAK_WHISPER = 0.0015


class AudioRecorder:
    def __init__(self, sample_rate=16000, device=None, whisper_mode_enabled=True):
        self.sample_rate = sample_rate
        self.device = device  # None = system default, int = device index, str = device name
        self.whisper_mode_enabled = whisper_mode_enabled
        self.is_recording = False
        self._frames = []
        self._stream = None
        self._lock = threading.Lock()
        self._stream_callback = None  # Optional external callback for streaming preview
        self._whisper_detector = WhisperDetector()
        self._max_recording_seconds = None  # set per-recording via start()
        self._start_monotonic = 0.0
        self._on_max_duration_reached = None
        self._last_start_error = None

    def start(self, max_seconds: float | None = None, on_max_duration=None):
        """Begin recording.

        Args:
            max_seconds: When set, the recording auto-stops after this many
                seconds and ``on_max_duration`` is invoked. Useful for the
                config-driven hard limit (``max_recording_seconds``).
            on_max_duration: Callback fired when ``max_seconds`` is reached.
                Called from a background thread; the callback is responsible
                for any UI dispatch.
        """
        with self._lock:
            if self.is_recording:
                return True
            self._frames = []
            self._whisper_detector.reset()
            self._max_recording_seconds = max_seconds
            self._on_max_duration_reached = on_max_duration
            self._start_monotonic = time.monotonic()
            self.is_recording = True
            self._last_start_error = None

            for attempt in range(MAX_RETRIES):
                try:
                    # Reset PortAudio to pick up device changes
                    if attempt > 0:
                        try:
                            sd._terminate()
                            sd._initialize()
                        except Exception:
                            pass
                        time.sleep(RETRY_DELAY)

                    device_idx = self._resolve_device()
                    kwargs = {
                        "samplerate": self.sample_rate,
                        "channels": 1,
                        "dtype": "float32",
                        "callback": self._callback,
                        "blocksize": int(self.sample_rate * 0.1),
                    }
                    if device_idx is not None:
                        kwargs["device"] = device_idx

                    self._stream = sd.InputStream(**kwargs)
                    self._stream.start()
                    self._last_start_error = None
                    return True
                except Exception as e:
                    self._last_start_error = e
                    logger.warning(f"Audio open failed (attempt {attempt+1}/{MAX_RETRIES}): {e}")
                    if self._stream:
                        try:
                            self._stream.close()
                        except Exception:
                            pass
                        self._stream = None

            # All retries failed
            self.is_recording = False
            self._max_recording_seconds = None
            self._on_max_duration_reached = None
            self._start_monotonic = 0.0
            logger.error("Could not open microphone after retries")
            return False

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

    def _callback(self, indata, frames, time_info, status):
        if not self.is_recording:
            return
        chunk = indata.copy()

        # Adaptive whisper detection — feed RAW peak so the detector sees
        # the user's actual loudness, not the post-boost level.
        if self.whisper_mode_enabled:
            try:
                raw_peak = float(np.max(np.abs(chunk)))
                self._whisper_detector.feed_chunk(raw_peak)
                gain = self._whisper_detector.gain_factor()
                if gain > 1.0:
                    chunk = np.clip(chunk * gain, -1.0, 1.0)
            except Exception as e:
                logger.debug(f"Whisper detection failed in callback: {e}")

        self._frames.append(chunk)

        # Watchdog: enforce max_recording_seconds
        if self._max_recording_seconds is not None:
            if time.monotonic() - self._start_monotonic >= self._max_recording_seconds:
                cb = self._on_max_duration_reached
                # Disarm immediately so we only fire once.
                self._max_recording_seconds = None
                if cb is not None:
                    try:
                        cb()
                    except Exception as e:
                        logger.debug(f"max_duration callback failed: {e}")

        # Feed to streaming preview if registered
        if self._stream_callback:
            try:
                self._stream_callback(chunk)
            except Exception:
                pass

    def stop(self) -> str | None:
        """Stop recording and return path to WAV file, or None if no audio."""
        audio_data = self.stop_audio()
        if audio_data is None:
            return None

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        sf.write(tmp.name, audio_data, self.sample_rate)
        tmp.close()
        return tmp.name

    def stop_audio(self):
        """Stop recording and return validated audio data, or None if unusable."""
        frames = self._finish_recording()
        return self._finalize_audio(frames)

    def _finish_recording(self):
        with self._lock:
            if not self.is_recording:
                return None
            self.is_recording = False
            self._max_recording_seconds = None
            self._on_max_duration_reached = None
            if self._stream:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
            frames = list(self._frames)
            self._frames = []
        return frames

    def _finalize_audio(self, frames):
        if not frames:
            logger.warning("No audio frames captured at all")
            return None

        audio_data = np.concatenate(frames, axis=0).flatten()
        duration = len(audio_data) / self.sample_rate
        peak = float(np.max(np.abs(audio_data)))
        whisper_was_active = self._whisper_detector.was_active
        logger.info(
            f"Audio: {len(frames)} frames, {duration:.1f}s, peak={peak:.4f}, whisper={whisper_was_active}"
        )

        if len(audio_data) < self.sample_rate * 0.3:
            logger.warning(f"Audio too short: {duration:.2f}s < 0.3s")
            return None

        min_peak = MIN_PEAK_WHISPER if whisper_was_active else MIN_PEAK_NORMAL
        if peak < min_peak:
            logger.warning(f"Audio too quiet: peak={peak:.4f} < {min_peak}")
            return None

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
