"""Floating recording indicator overlay for SpeakType."""

import math
import threading
import logging
import AppKit
import objc
import Quartz
from Foundation import NSMakeRect, NSTimer, NSObject

logger = logging.getLogger("speaktype.overlay")

# Colors
COLOR_RECORDING = (0.92, 0.26, 0.21, 0.95)   # Red
COLOR_PROCESSING = (1.0, 0.76, 0.03, 0.95)    # Amber
COLOR_IDLE = (0.3, 0.69, 0.31, 0.85)          # Green

OVERLAY_SIZE = 48
PULSE_INTERVAL = 0.05


class RecordingOverlay:
    """A small floating indicator that shows recording/processing state."""

    def __init__(self):
        self._window = None
        self._dot_view = None
        self._pulse_timer = None
        self._state = "idle"  # idle, recording, processing
        self._level = 0.0
        self._visible = False

    def setup(self):
        """Create the overlay window. Must be called from main thread."""
        screen = AppKit.NSScreen.mainScreen()
        if not screen:
            return
        screen_frame = screen.visibleFrame()

        # Position: top-right corner
        x = screen_frame.origin.x + screen_frame.size.width - OVERLAY_SIZE - 20
        y = screen_frame.origin.y + screen_frame.size.height - OVERLAY_SIZE - 10
        frame = NSMakeRect(x, y, OVERLAY_SIZE, OVERLAY_SIZE)

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
        # Disable window tabbing to prevent crash on macOS 13+
        self._window.setTabbingMode_(AppKit.NSWindowTabbingModeDisallowed)
        self._window.setAlphaValue_(0.0)

        # Create the dot view
        self._dot_view = DotView.alloc().initWithFrame_(NSMakeRect(0, 0, OVERLAY_SIZE, OVERLAY_SIZE))
        self._window.contentView().addSubview_(self._dot_view)

    def show_recording(self):
        self._state = "recording"
        self._show()

    def show_processing(self):
        self._state = "processing"
        self._update_dot()

    def update_level(self, level: float):
        self._level = level
        if self._state == "recording" and self._dot_view:
            self._dot_view.audioLevel = max(0.0, min(1.0, level))
            self._dot_view.setNeedsDisplay_(True)

    def hide(self):
        self._state = "idle"
        self._stop_pulse()
        if self._window:
            AppKit.NSAnimationContext.beginGrouping()
            AppKit.NSAnimationContext.currentContext().setDuration_(0.2)
            self._window.animator().setAlphaValue_(0.0)
            AppKit.NSAnimationContext.endGrouping()
        self._visible = False

    def _show(self):
        if not self._window:
            self.setup()
        if not self._window:
            return
        self._visible = True
        self._update_dot()
        self._window.orderFront_(None)
        AppKit.NSAnimationContext.beginGrouping()
        AppKit.NSAnimationContext.currentContext().setDuration_(0.15)
        self._window.animator().setAlphaValue_(1.0)
        AppKit.NSAnimationContext.endGrouping()
        self._start_pulse()

    def _update_dot(self):
        if not self._dot_view:
            return
        if self._state == "recording":
            r, g, b, a = COLOR_RECORDING
        elif self._state == "processing":
            r, g, b, a = COLOR_PROCESSING
        else:
            r, g, b, a = COLOR_IDLE
        self._dot_view.colorR = r
        self._dot_view.colorG = g
        self._dot_view.colorB = b
        self._dot_view.colorA = a
        self._dot_view.setNeedsDisplay_(True)

    def _start_pulse(self):
        if self._pulse_timer:
            return
        self._pulse_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            PULSE_INTERVAL, self._dot_view, b"pulse:", None, True
        )

    def _stop_pulse(self):
        if self._pulse_timer:
            self._pulse_timer.invalidate()
            self._pulse_timer = None


class DotView(AppKit.NSView):
    """Custom view that draws a colored pulsing circle."""

    # Use ivar-style attributes that PyObjC won't try to map to ObjC selectors
    colorR = objc.ivar.double()
    colorG = objc.ivar.double()
    colorB = objc.ivar.double()
    colorA = objc.ivar.double()
    audioLevel = objc.ivar.double()
    pulsePhase = objc.ivar.double()

    def initWithFrame_(self, frame):
        self = objc.super(DotView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.colorR = 0.92
        self.colorG = 0.26
        self.colorB = 0.21
        self.colorA = 0.95
        self.audioLevel = 0.0
        self.pulsePhase = 0.0
        return self

    def drawRect_(self, rect):
        AppKit.NSColor.clearColor().set()
        AppKit.NSBezierPath.fillRect_(rect)

        # Outer glow based on audio level
        glow_size = self.audioLevel * 6
        if glow_size > 0.5:
            glow_rect = AppKit.NSInsetRect(rect, -glow_size, -glow_size)
            glow_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                self.colorR, self.colorG, self.colorB, 0.3 * self.audioLevel
            )
            glow_color.set()
            path = AppKit.NSBezierPath.bezierPathWithOvalInRect_(glow_rect)
            path.fill()

        # Pulse effect
        pulse = 0.85 + 0.15 * math.sin(self.pulsePhase)
        inset = OVERLAY_SIZE * (1 - pulse) / 2

        dot_rect = AppKit.NSInsetRect(rect, inset + 4, inset + 4)
        color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
            self.colorR, self.colorG, self.colorB, self.colorA
        )
        color.set()
        path = AppKit.NSBezierPath.bezierPathWithOvalInRect_(dot_rect)
        path.fill()

        # Inner highlight
        highlight_rect = AppKit.NSInsetRect(dot_rect, 8, 8)
        highlight_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
            1.0, 1.0, 1.0, 0.25
        )
        highlight_color.set()
        highlight_path = AppKit.NSBezierPath.bezierPathWithOvalInRect_(highlight_rect)
        highlight_path.fill()

    def pulse_(self, timer):
        self.pulsePhase += 0.15
        if self.pulsePhase > math.pi * 2:
            self.pulsePhase -= math.pi * 2
        self.setNeedsDisplay_(True)
