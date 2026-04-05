"""Streaming transcription preview window.

Shows real-time transcription results in a floating overlay while the user
is recording, providing instant visual feedback before the final polish step.
"""

import math
import threading
import logging
import time
import AppKit
import objc
from Foundation import NSMakeRect, NSObject, NSTimer

logger = logging.getLogger("speaktype.streaming")

# Preview window dimensions
PREVIEW_WIDTH = 420
PREVIEW_HEIGHT = 64
PREVIEW_PADDING = 16
PREVIEW_CORNER_RADIUS = 12


class StreamingPreviewWindow:
    """Floating window that displays streaming transcription text."""

    def __init__(self):
        self._window = None
        self._text_field = None
        self._visible = False
        self._lock = threading.Lock()
        self._current_text = ""
        self._fade_timer = None

    def setup(self):
        """Create the preview window. Must be called from main thread."""
        screen = AppKit.NSScreen.mainScreen()
        if not screen:
            return
        screen_frame = screen.visibleFrame()

        # Position: top-center, below menubar
        x = screen_frame.origin.x + (screen_frame.size.width - PREVIEW_WIDTH) / 2
        y = screen_frame.origin.y + screen_frame.size.height - PREVIEW_HEIGHT - 60
        frame = NSMakeRect(x, y, PREVIEW_WIDTH, PREVIEW_HEIGHT)

        self._window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            AppKit.NSWindowStyleMaskBorderless,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        self._window.setLevel_(AppKit.NSStatusWindowLevel + 1)
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(AppKit.NSColor.clearColor())
        self._window.setIgnoresMouseEvents_(True)
        self._window.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorStationary
        )
        self._window.setTabbingMode_(AppKit.NSWindowTabbingModeDisallowed)
        self._window.setAlphaValue_(0.0)

        # Background view with rounded corners and blur effect
        content = self._window.contentView()
        bg_view = _RoundedBackgroundView.alloc().initWithFrame_(
            NSMakeRect(0, 0, PREVIEW_WIDTH, PREVIEW_HEIGHT)
        )
        content.addSubview_(bg_view)

        # Text field for transcription preview
        self._text_field = AppKit.NSTextField.alloc().initWithFrame_(
            NSMakeRect(
                PREVIEW_PADDING, 8,
                PREVIEW_WIDTH - 2 * PREVIEW_PADDING,
                PREVIEW_HEIGHT - 16,
            )
        )
        self._text_field.setBezeled_(False)
        self._text_field.setDrawsBackground_(False)
        self._text_field.setEditable_(False)
        self._text_field.setSelectable_(False)
        self._text_field.setTextColor_(AppKit.NSColor.whiteColor())
        self._text_field.setFont_(AppKit.NSFont.systemFontOfSize_(15))
        self._text_field.setLineBreakMode_(AppKit.NSLineBreakByTruncatingTail)
        self._text_field.setMaximumNumberOfLines_(2)
        self._text_field.setStringValue_("")
        content.addSubview_(self._text_field)

    def show(self):
        """Show the preview window with fade-in."""
        if not self._window:
            self.setup()
        if not self._window:
            return
        self._visible = True
        self._current_text = ""
        if self._text_field:
            self._text_field.setStringValue_("Listening...")
        self._window.orderFront_(None)
        AppKit.NSAnimationContext.beginGrouping()
        AppKit.NSAnimationContext.currentContext().setDuration_(0.15)
        self._window.animator().setAlphaValue_(0.92)
        AppKit.NSAnimationContext.endGrouping()

    def update_text(self, text: str):
        """Update the preview text. Thread-safe."""
        with self._lock:
            self._current_text = text
        # Schedule UI update on main thread
        self._schedule_ui_update(text)

    def _schedule_ui_update(self, text: str):
        """Update text field on main thread."""
        try:
            if self._text_field:
                self._text_field.performSelectorOnMainThread_withObject_waitUntilDone_(
                    b"setStringValue:", text, False
                )
                # Resize window height if text is long
                self._auto_resize(text)
        except Exception as e:
            logger.debug(f"UI update failed: {e}")

    def _auto_resize(self, text: str):
        """Grow the window vertically if text needs more space."""
        if not self._window:
            return
        lines = max(1, min(4, len(text) // 50 + 1))
        new_height = max(PREVIEW_HEIGHT, 28 + lines * 20)
        if self._window:
            frame = self._window.frame()
            if abs(frame.size.height - new_height) > 4:
                frame.origin.y += frame.size.height - new_height
                frame.size.height = new_height
                self._window.setFrame_display_animate_(frame, True, False)

    def hide(self, delay: float = 0.0):
        """Hide the preview window with optional delay and fade-out."""
        if not self._visible:
            return
        self._visible = False

        def _do_hide():
            if self._window:
                AppKit.NSAnimationContext.beginGrouping()
                AppKit.NSAnimationContext.currentContext().setDuration_(0.3)
                self._window.animator().setAlphaValue_(0.0)
                AppKit.NSAnimationContext.endGrouping()

        if delay > 0:
            threading.Timer(delay, lambda: AppKit.NSApp.performSelectorOnMainThread_withObject_waitUntilDone_(
                b"performSelector:", None, False
            ) if False else _do_hide()).start()
        else:
            _do_hide()

    def get_text(self) -> str:
        """Return the current preview text."""
        with self._lock:
            return self._current_text


class _RoundedBackgroundView(AppKit.NSView):
    """Custom view drawing a rounded semi-transparent dark background."""

    def drawRect_(self, rect):
        path = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            rect, PREVIEW_CORNER_RADIUS, PREVIEW_CORNER_RADIUS
        )
        bg_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
            0.1, 0.1, 0.12, 0.88
        )
        bg_color.set()
        path.fill()


class StreamingTranscriber:
    """Manages streaming transcription from audio chunks.

    Feeds audio data to the ASR model's stream_transcribe() and emits
    partial results to the preview window.
    """

    def __init__(self, asr_engine, preview_window: StreamingPreviewWindow):
        self._asr = asr_engine
        self._preview = preview_window
        self._audio_buffer = []
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self._accumulated_text = ""

    def start(self, language: str = "auto"):
        """Start the streaming transcription loop."""
        self._running = True
        self._audio_buffer = []
        self._accumulated_text = ""
        self._thread = threading.Thread(
            target=self._stream_loop,
            args=(language,),
            daemon=True,
        )
        self._thread.start()

    def feed_audio(self, audio_chunk):
        """Feed an audio chunk (numpy array) into the streaming buffer."""
        with self._lock:
            self._audio_buffer.append(audio_chunk.copy())

    def stop(self) -> str:
        """Stop streaming and return the accumulated text so far."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        return self._accumulated_text

    def _stream_loop(self, language: str):
        """Background loop that runs streaming transcription on buffered audio."""
        import numpy as np

        try:
            if not self._asr._loaded:
                return

            # Check if the model supports streaming
            model = self._asr.model
            has_stream = hasattr(model, "stream_transcribe")
            if not has_stream:
                logger.debug("Model does not support stream_transcribe, using chunked mode")
                self._chunked_fallback(language)
                return

            # Accumulate audio and run stream_transcribe periodically
            last_transcribe_time = time.time()
            min_interval = 1.0  # Minimum seconds between transcription updates

            while self._running:
                time.sleep(0.1)
                now = time.time()
                if now - last_transcribe_time < min_interval:
                    continue

                with self._lock:
                    if not self._audio_buffer:
                        continue
                    audio_data = np.concatenate(self._audio_buffer, axis=0).flatten()

                if len(audio_data) < 4800:  # Less than 0.3s at 16kHz
                    continue

                last_transcribe_time = now

                try:
                    kwargs = {"audio": audio_data, "max_tokens": 8192}
                    if language and language != "auto":
                        kwargs["language"] = language

                    for result in model.stream_transcribe(**kwargs):
                        if not self._running:
                            break
                        text = ""
                        if hasattr(result, "text"):
                            text = result.text
                        elif isinstance(result, dict):
                            text = result.get("text", "")
                        elif isinstance(result, str):
                            text = result

                        if text.strip():
                            self._accumulated_text = text.strip()
                            self._preview.update_text(self._accumulated_text)
                except Exception as e:
                    logger.debug(f"Stream transcription update failed: {e}")

        except Exception as e:
            logger.error(f"Streaming transcription loop error: {e}")

    def _chunked_fallback(self, language: str):
        """Fallback: periodically transcribe accumulated audio chunks."""
        import numpy as np
        from mlx_audio.stt.generate import generate_transcription

        last_transcribe_time = time.time()
        min_interval = 1.5

        while self._running:
            time.sleep(0.1)
            now = time.time()
            if now - last_transcribe_time < min_interval:
                continue

            with self._lock:
                if not self._audio_buffer:
                    continue
                audio_data = np.concatenate(self._audio_buffer, axis=0).flatten()

            if len(audio_data) < 4800:
                continue

            last_transcribe_time = now

            try:
                kwargs = {
                    "model": self._asr.model,
                    "audio": audio_data,
                    "verbose": False,
                }
                if language and language != "auto":
                    kwargs["language"] = language

                result = generate_transcription(**kwargs)
                text = ""
                if hasattr(result, "text"):
                    text = result.text
                elif isinstance(result, str):
                    text = result
                elif isinstance(result, dict):
                    text = result.get("text", "")

                if text.strip():
                    self._accumulated_text = text.strip()
                    self._preview.update_text(self._accumulated_text)
            except Exception as e:
                logger.debug(f"Chunked transcription update failed: {e}")
