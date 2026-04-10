"""Adaptive whisper detection.

Real-time analysis of incoming audio chunks to decide whether the user is
speaking at a normal volume or whispering. Designed to live in the audio
callback path: it must be cheap, lock-free on the hot path, and resilient
to brief noise spikes.

Design notes
------------
* The detector consumes peak amplitudes (one per audio block, typically
  100 ms). Computing the peak is the caller's responsibility — the detector
  itself never touches numpy arrays.
* State transitions use *hysteresis*: it takes a sustained quiet stretch to
  enter whisper mode and a sustained loud stretch to leave it. This avoids
  flapping between states on isolated quiet/loud frames.
* A noise floor cutoff treats very low peaks (< NOISE_FLOOR) as silence
  rather than whisper, so background hiss alone never trips the detector.
* When in whisper state, ``gain_factor()`` returns a multiplier the audio
  recorder applies to incoming chunks before they reach the buffer.

The class is intentionally UI-agnostic. State changes are surfaced via an
optional ``on_state_change`` callback that takes the new state string.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger("speaktype.whisper_detect")

# --- Tuning constants ---
# Below this peak the audio is treated as silence, not whisper.
NOISE_FLOOR = 0.0015
# Enter whisper mode when peak stays below this for a while.
WHISPER_ENTER_THRESHOLD = 0.025
# Leave whisper mode when peak rises above this for a while.
WHISPER_EXIT_THRESHOLD = 0.06
# How many consecutive qualifying frames trigger an enter / exit.
# At 100 ms per block these mean ~600 ms / ~400 ms.
WHISPER_ENTER_FRAMES = 6
WHISPER_EXIT_FRAMES = 4
# Multiplier applied to incoming audio while in whisper mode.
WHISPER_GAIN = 5.0

STATE_NORMAL = "normal"
STATE_WHISPER = "whisper"


class WhisperDetector:
    """Stateful whisper-vs-normal classifier driven by chunk peak amplitudes."""

    def __init__(
        self,
        enter_threshold: float = WHISPER_ENTER_THRESHOLD,
        exit_threshold: float = WHISPER_EXIT_THRESHOLD,
        enter_frames: int = WHISPER_ENTER_FRAMES,
        exit_frames: int = WHISPER_EXIT_FRAMES,
        noise_floor: float = NOISE_FLOOR,
        gain: float = WHISPER_GAIN,
        on_state_change=None,
    ):
        self._enter_threshold = enter_threshold
        self._exit_threshold = exit_threshold
        self._enter_frames = enter_frames
        self._exit_frames = exit_frames
        self._noise_floor = noise_floor
        self._gain = gain

        self._state = STATE_NORMAL
        self._consecutive_quiet = 0
        self._consecutive_loud = 0
        self._on_state_change = on_state_change
        self._lock = threading.Lock()
        self._was_active = False  # latched flag — true if we ever entered whisper

    # ------------------------------------------------------------------ #
    # Public API                                                          #
    # ------------------------------------------------------------------ #

    def feed_chunk(self, chunk_peak: float) -> str:
        """Feed the peak amplitude of one audio block.

        Returns the new state (``"normal"`` or ``"whisper"``). Safe to call
        from any thread; the underlying state machine is guarded by a lock.
        """
        new_state = None
        with self._lock:
            if chunk_peak < self._noise_floor:
                # Silence should break both streaks. Otherwise a quiet run
                # can survive a gap and incorrectly trip whisper mode later.
                self._consecutive_quiet = 0
                self._consecutive_loud = 0
                return self._state

            if self._state == STATE_NORMAL:
                if chunk_peak < self._enter_threshold:
                    self._consecutive_quiet += 1
                    self._consecutive_loud = 0
                    if self._consecutive_quiet >= self._enter_frames:
                        self._state = STATE_WHISPER
                        self._was_active = True
                        new_state = STATE_WHISPER
                        self._consecutive_quiet = 0
                else:
                    self._consecutive_quiet = 0
            else:  # STATE_WHISPER
                if chunk_peak > self._exit_threshold:
                    self._consecutive_loud += 1
                    self._consecutive_quiet = 0
                    if self._consecutive_loud >= self._exit_frames:
                        self._state = STATE_NORMAL
                        new_state = STATE_NORMAL
                        self._consecutive_loud = 0
                else:
                    self._consecutive_loud = 0

        # Fire callback outside the lock to avoid deadlocks if the callback
        # turns around and calls back into the detector.
        if new_state is not None and self._on_state_change is not None:
            try:
                self._on_state_change(new_state)
            except Exception as e:
                logger.debug(f"WhisperDetector state-change callback failed: {e}")

        return self._state

    def gain_factor(self) -> float:
        """Return the gain to apply to incoming audio for the current state."""
        return self._gain if self._state == STATE_WHISPER else 1.0

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_whisper(self) -> bool:
        return self._state == STATE_WHISPER

    @property
    def was_active(self) -> bool:
        """True if whisper mode was triggered at any point since the last reset."""
        return self._was_active

    def reset(self):
        """Reset the detector back to its initial idle state."""
        with self._lock:
            self._state = STATE_NORMAL
            self._consecutive_quiet = 0
            self._consecutive_loud = 0
            self._was_active = False

    def set_state_callback(self, callback):
        """Replace the on_state_change callback."""
        self._on_state_change = callback
