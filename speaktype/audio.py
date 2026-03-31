"""Audio recording module using sounddevice."""

import threading
import tempfile
import numpy as np
import sounddevice as sd
import soundfile as sf


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
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                callback=self._callback,
                blocksize=int(self.sample_rate * 0.1),  # 100ms blocks
            )
            self._stream.start()

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
                self._stream.stop()
                self._stream.close()
                self._stream = None
            # Copy frames under lock to avoid race with callback
            frames = list(self._frames)
            self._frames = []

        if not frames:
            return None

        audio_data = np.concatenate(frames, axis=0).flatten()

        # Skip if too short (< 0.3 seconds) or too quiet
        if len(audio_data) < self.sample_rate * 0.3:
            return None
        if np.max(np.abs(audio_data)) < 0.01:
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
