"""Audio recording module using sounddevice."""

import time
import threading
import tempfile
import logging
import numpy as np
import sounddevice as sd
import soundfile as sf

logger = logging.getLogger("speaktype.audio")

MAX_RETRIES = 3
RETRY_DELAY = 0.3


class AudioRecorder:
    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate
        self.is_recording = False
        self._frames = []
        self._stream = None
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self.is_recording:
                return
            self._frames = []
            self.is_recording = True

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

                    self._stream = sd.InputStream(
                        samplerate=self.sample_rate,
                        channels=1,
                        dtype="float32",
                        callback=self._callback,
                        blocksize=int(self.sample_rate * 0.1),
                    )
                    self._stream.start()
                    return  # success
                except Exception as e:
                    logger.warning(f"Audio open failed (attempt {attempt+1}/{MAX_RETRIES}): {e}")
                    if self._stream:
                        try:
                            self._stream.close()
                        except Exception:
                            pass
                        self._stream = None

            # All retries failed
            self.is_recording = False
            logger.error("Could not open microphone after retries")

    def _callback(self, indata, frames, time_info, status):
        if self.is_recording:
            self._frames.append(indata.copy())

    def stop(self) -> str | None:
        """Stop recording and return path to WAV file, or None if no audio."""
        with self._lock:
            if not self.is_recording:
                return None
            self.is_recording = False
            if self._stream:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
            frames = list(self._frames)
            self._frames = []

        if not frames:
            logger.warning("No audio frames captured at all")
            return None

        audio_data = np.concatenate(frames, axis=0).flatten()
        duration = len(audio_data) / self.sample_rate
        peak = float(np.max(np.abs(audio_data)))
        logger.info(f"Audio: {len(frames)} frames, {duration:.1f}s, peak={peak:.4f}")

        if len(audio_data) < self.sample_rate * 0.3:
            logger.warning(f"Audio too short: {duration:.2f}s < 0.3s")
            return None
        if peak < 0.005:
            logger.warning(f"Audio too quiet: peak={peak:.4f} < 0.005")
            return None

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        sf.write(tmp.name, audio_data, self.sample_rate)
        tmp.close()
        return tmp.name

    def get_level(self) -> float:
        """Get current audio level (0.0 to 1.0) for visual feedback."""
        try:
            if self._frames:
                last = self._frames[-1]
                return float(np.clip(np.max(np.abs(last)) * 5, 0, 1))
        except (IndexError, ValueError):
            pass
        return 0.0
