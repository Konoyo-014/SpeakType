"""Unified floating status overlay — 'Fluid Native' redesign for SpeakType.

Designed as a continuous-curve squircle HUD with:

- NSVisualEffectView popover material (adapts to light/dark mode, lets
  the OS pick perfect text contrast via ``labelColor``).
- A 20x20 state indicator at the top-left that morphs between:
    recording    -> animated waveform bars (tinted red)
    transcribing -> spinning arc         (tinted orange)
    polishing    -> spinning arc         (tinted blue)
    done         -> SF Symbol checkmark  (tinted green)
    error        -> SF Symbol warning    (tinted red)
- An SF Symbol ``moon.stars.fill`` whisper indicator (no more emoji clipping).
- No numeric timer — the waveform itself IS the "recording is active" cue.
- Word-wrapped transcription with fluid top-anchored window growth: the
  pill expands vertically as new text arrives, capped at 200pt.
- Subtle slide-up + fade-out hide animation.

All public methods are safe to call from any thread — UI work dispatches
to the main thread via an ``NSObject`` bridge.
"""

from __future__ import annotations

import logging
import math
import re
import threading
import unicodedata

import AppKit
import objc
from Foundation import NSMakeRect, NSMakePoint, NSMakeSize, NSObject, NSTimer

try:
    import Quartz
    _QUARTZ_OK = True
except Exception:  # pragma: no cover — Quartz ships with macOS
    _QUARTZ_OK = False

logger = logging.getLogger("speaktype.status_overlay")

# -------------------------------------------------------------------- #
# Geometry                                                              #
# -------------------------------------------------------------------- #

WINDOW_WIDTH = 380
WINDOW_HEIGHT_MIN = 48
WINDOW_HEIGHT_MAX = 200
CORNER_RADIUS = 24
TOP_OFFSET = 64  # distance from top of visible screen

# Internal padding
TEXT_V_PADDING = 14  # from top AND from bottom
LEFT_PADDING = 16
RIGHT_PADDING = 16
INDICATOR_TO_TEXT_GAP = 12

# State indicator (top-left)
INDICATOR_SIZE = 20

# Whisper indicator (top-right, top-aligned with first line of text)
WHISPER_SIZE = 16
WHISPER_TEXT_GAP = 8  # reserved between text's right edge and whisper icon

# Text
TEXT_FONT_SIZE = 15
TEXT_LINE_HEIGHT = 20
TEXT_LEFT = LEFT_PADDING + INDICATOR_SIZE + INDICATOR_TO_TEXT_GAP  # 48

# Animations
SHOW_DURATION = 0.15
HIDE_DURATION = 0.25
HIDE_SLIDE_DISTANCE = 10.0
RESIZE_DURATION = 0.35

STATE_LABELS = {
    "recording": "Listening\u2026",
    "transcribing": "Transcribing\u2026",
    "polishing": "Polishing\u2026",
    "done": "",
    "error": "Error",
}

_ASR_SPECIAL_TOKEN_RE = re.compile(r"<\|[^|\r\n]{0,80}\|>")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def _sanitize_display_text(text) -> str:
    """Normalize text for overlay display without changing inserted output."""
    if text is None:
        return ""
    clean = str(text)
    clean = clean.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    clean = _ASR_SPECIAL_TOKEN_RE.sub("", clean)
    clean = _CONTROL_CHARS_RE.sub("", clean)
    return unicodedata.normalize("NFC", clean)


def _state_color(state: str):
    """Return the system NSColor that represents a given state."""
    if state == "recording":
        return AppKit.NSColor.systemRedColor()
    if state == "transcribing":
        return AppKit.NSColor.systemOrangeColor()
    if state == "polishing":
        return AppKit.NSColor.systemBlueColor()
    if state == "done":
        return AppKit.NSColor.systemGreenColor()
    if state == "error":
        return AppKit.NSColor.systemRedColor()
    return AppKit.NSColor.secondaryLabelColor()


def _format_duration(seconds: float) -> str:
    """Format a duration as ``m:ss``. Kept for test compatibility."""
    total = max(0, int(seconds))
    minutes = total // 60
    secs = total % 60
    return f"{minutes}:{secs:02d}"


def _safe_cgcolor(color):
    """Return a CGColor for the given NSColor, or None on failure."""
    try:
        return color.CGColor()
    except Exception:
        return None


def _create_sf_symbol_view(name, point_size, tint_color, frame):
    """Create an NSImageView rendering an SF Symbol with the given tint."""
    try:
        img = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(
            name, None
        )
        if img is None:
            return None
        try:
            config = AppKit.NSImageSymbolConfiguration.configurationWithPointSize_weight_scale_(
                point_size, AppKit.NSFontWeightMedium, 2  # NSImageSymbolScaleMedium
            )
            if config is not None:
                cfg_img = img.imageWithSymbolConfiguration_(config)
                if cfg_img is not None:
                    img = cfg_img
        except Exception:
            pass
        img.setTemplate_(True)
        view = AppKit.NSImageView.alloc().initWithFrame_(frame)
        view.setImage_(img)
        view.setImageScaling_(1)  # NSImageScaleProportionallyDown
        view.setImageAlignment_(AppKit.NSImageAlignCenter)
        try:
            view.setContentTintColor_(tint_color)
        except Exception:
            pass
        return view
    except Exception as e:
        logger.debug(f"Failed to build SF Symbol view {name!r}: {e}")
        return None


# -------------------------------------------------------------------- #
# Subviews                                                              #
# -------------------------------------------------------------------- #


class _WaveformView(AppKit.NSView):
    """Four animated bars driven by audio level and a sinusoidal phase."""

    def initWithFrame_(self, frame):
        self = objc.super(_WaveformView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._level = 0.0
        self._phase = 0.0
        self._tint = AppKit.NSColor.systemRedColor()
        self._anim_timer = None
        return self

    def set_level(self, level):
        try:
            self._level = max(0.0, min(1.0, float(level)))
        except Exception:
            self._level = 0.0

    def set_tint(self, color):
        if color is not None:
            self._tint = color
            self.setNeedsDisplay_(True)

    def start_animating(self):
        if self._anim_timer is not None:
            return
        self._anim_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0 / 24, self, b"tickAnim:", None, True
        )

    def stop_animating(self):
        if self._anim_timer is not None:
            try:
                self._anim_timer.invalidate()
            except Exception:
                pass
            self._anim_timer = None

    def tickAnim_(self, timer):
        self._phase += 0.18
        if self._phase > 2 * math.pi:
            self._phase -= 2 * math.pi
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        bounds = self.bounds()
        bar_count = 4
        bar_width = 2.6
        gap = 2.0
        total_w = bar_count * bar_width + (bar_count - 1) * gap
        start_x = (bounds.size.width - total_w) / 2.0
        center_y = bounds.size.height / 2.0
        max_bar_h = bounds.size.height - 4.0

        # Baseline amplitude keeps the bars visible in silence; scale up with level.
        amplitude = 0.28 + 0.72 * self._level

        self._tint.setFill()
        for i in range(bar_count):
            wave = (math.sin(self._phase + i * 0.9) + 1.0) / 2.0  # 0..1
            bar_h = max(3.0, max_bar_h * amplitude * (0.35 + 0.65 * wave))
            x = start_x + i * (bar_width + gap)
            y = center_y - bar_h / 2.0
            bar_rect = NSMakeRect(x, y, bar_width, bar_h)
            path = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                bar_rect, bar_width / 2.0, bar_width / 2.0
            )
            path.fill()


class _SpinnerView(AppKit.NSView):
    """A rotating 3/4 arc implemented with CAShapeLayer.

    Falls back to a static drawn arc when Quartz is unavailable — which
    shouldn't happen on real macOS, but keeps the code importable in
    test environments that stub PyObjC.
    """

    def initWithFrame_(self, frame):
        self = objc.super(_SpinnerView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._tint = AppKit.NSColor.systemOrangeColor()
        self._arc_layer = None
        self.setWantsLayer_(True)
        if _QUARTZ_OK:
            self._build_layer(frame)
        return self

    def _build_layer(self, frame):
        try:
            size = frame.size.width
            radius = size / 2.0 - 2.5
            arc = Quartz.CAShapeLayer.layer()
            arc.setBounds_(NSMakeRect(0, 0, size, size))
            arc.setPosition_(NSMakePoint(size / 2.0, size / 2.0))
            arc.setAnchorPoint_(NSMakePoint(0.5, 0.5))

            # Path in local coordinates, centered at (size/2, size/2).
            path = Quartz.CGPathCreateMutable()
            Quartz.CGPathAddArc(
                path, None, size / 2.0, size / 2.0, radius,
                -math.pi / 2, math.pi, False,
            )
            arc.setPath_(path)
            arc.setFillColor_(AppKit.NSColor.clearColor().CGColor())
            cg = _safe_cgcolor(self._tint)
            if cg is not None:
                arc.setStrokeColor_(cg)
            arc.setLineWidth_(2.2)
            arc.setLineCap_("round")

            host = self.layer()
            if host is not None:
                host.addSublayer_(arc)
                self._arc_layer = arc
        except Exception as e:
            logger.debug(f"Spinner layer init failed: {e}")
            self._arc_layer = None

    def set_tint(self, color):
        if color is None:
            return
        self._tint = color
        if self._arc_layer is not None:
            cg = _safe_cgcolor(color)
            if cg is not None:
                self._arc_layer.setStrokeColor_(cg)
        else:
            self.setNeedsDisplay_(True)

    def start_animating(self):
        if self._arc_layer is None or not _QUARTZ_OK:
            return
        try:
            rotation = Quartz.CABasicAnimation.animationWithKeyPath_(
                "transform.rotation.z"
            )
            rotation.setFromValue_(0.0)
            rotation.setToValue_(-2 * math.pi)
            rotation.setDuration_(1.0)
            rotation.setRepeatCount_(1e9)
            self._arc_layer.addAnimation_forKey_(rotation, "rotation")
        except Exception as e:
            logger.debug(f"Spinner start_animating failed: {e}")

    def stop_animating(self):
        if self._arc_layer is not None:
            try:
                self._arc_layer.removeAnimationForKey_("rotation")
            except Exception:
                pass

    def drawRect_(self, rect):
        # Fallback when CAShapeLayer is unavailable — draw a static arc.
        if self._arc_layer is not None:
            return
        bounds = self.bounds()
        cx = bounds.size.width / 2.0
        cy = bounds.size.height / 2.0
        radius = min(bounds.size.width, bounds.size.height) / 2.0 - 2.5
        path = AppKit.NSBezierPath.bezierPath()
        path.setLineWidth_(2.2)
        path.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_(
            NSMakePoint(cx, cy), radius, 90.0, 360.0
        )
        self._tint.set()
        path.stroke()


class _StateIndicatorView(AppKit.NSView):
    """20x20 container that swaps between waveform, spinner, and checkmark."""

    def initWithFrame_(self, frame):
        self = objc.super(_StateIndicatorView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.setWantsLayer_(True)

        inner = NSMakeRect(0, 0, frame.size.width, frame.size.height)

        self._waveform = _WaveformView.alloc().initWithFrame_(inner)
        self.addSubview_(self._waveform)

        self._spinner = _SpinnerView.alloc().initWithFrame_(inner)
        self._spinner.setHidden_(True)
        self.addSubview_(self._spinner)

        self._check_view = _create_sf_symbol_view(
            "checkmark.circle.fill",
            17,
            AppKit.NSColor.systemGreenColor(),
            inner,
        )
        if self._check_view is not None:
            self._check_view.setHidden_(True)
            self.addSubview_(self._check_view)

        self._error_view = _create_sf_symbol_view(
            "exclamationmark.triangle.fill",
            17,
            AppKit.NSColor.systemRedColor(),
            inner,
        )
        if self._error_view is not None:
            self._error_view.setHidden_(True)
            self.addSubview_(self._error_view)

        self._state = "idle"
        return self

    def set_state(self, state: str):
        """Swap to the right content + tint for the given state."""
        color = _state_color(state)

        if state == "recording":
            self._waveform.set_tint(color)
            self._waveform.setHidden_(False)
            self._waveform.start_animating()
            self._spinner.stop_animating()
            self._spinner.setHidden_(True)
            if self._check_view is not None:
                self._check_view.setHidden_(True)
            if self._error_view is not None:
                self._error_view.setHidden_(True)
        elif state in ("transcribing", "polishing"):
            self._waveform.stop_animating()
            self._waveform.setHidden_(True)
            self._spinner.set_tint(color)
            self._spinner.setHidden_(False)
            self._spinner.start_animating()
            if self._check_view is not None:
                self._check_view.setHidden_(True)
            if self._error_view is not None:
                self._error_view.setHidden_(True)
        elif state == "done":
            self._waveform.stop_animating()
            self._waveform.setHidden_(True)
            self._spinner.stop_animating()
            self._spinner.setHidden_(True)
            if self._check_view is not None:
                try:
                    self._check_view.setContentTintColor_(color)
                except Exception:
                    pass
                self._check_view.setHidden_(False)
            if self._error_view is not None:
                self._error_view.setHidden_(True)
        elif state == "error":
            self._waveform.stop_animating()
            self._waveform.setHidden_(True)
            self._spinner.stop_animating()
            self._spinner.setHidden_(True)
            if self._check_view is not None:
                self._check_view.setHidden_(True)
            if self._error_view is not None:
                try:
                    self._error_view.setContentTintColor_(color)
                except Exception:
                    pass
                self._error_view.setHidden_(False)
        else:  # idle
            self._waveform.stop_animating()
            self._waveform.setHidden_(True)
            self._spinner.stop_animating()
            self._spinner.setHidden_(True)
            if self._check_view is not None:
                self._check_view.setHidden_(True)
            if self._error_view is not None:
                self._error_view.setHidden_(True)

        self._state = state

    def update_level(self, level: float):
        if self._state == "recording":
            self._waveform.set_level(level)

    def stop_all_animations(self):
        self._waveform.stop_animating()
        self._spinner.stop_animating()


# -------------------------------------------------------------------- #
# Main overlay                                                          #
# -------------------------------------------------------------------- #


class _OverlayBridge(NSObject):
    """ObjC bridge to dispatch overlay updates onto the main thread."""

    def initWithOverlay_(self, overlay):
        self = objc.super(_OverlayBridge, self).init()
        if self is not None:
            self._overlay = overlay
        return self

    def showMain_(self, _):
        self._overlay._show_main()

    def hideMain_(self, _):
        self._overlay._hide_main()

    def refreshMain_(self, _):
        self._overlay._refresh_main()

    def updateLevelMain_(self, _):
        self._overlay._update_level_main()

    def resetAfterHide_(self, _):
        self._overlay._reset_after_hide_main()


class StatusOverlay:
    """A floating window showing recording state + streamed transcription."""

    def __init__(self):
        self._bridge = _OverlayBridge.alloc().initWithOverlay_(self)
        self._window = None
        self._effect_view = None
        self._indicator = None
        self._text_field = None
        self._whisper_view = None

        self._lock = threading.Lock()
        self._state = "idle"
        self._text = ""
        self._level = 0.0
        self._whisper_mode = False
        self._is_visible = False
        self._auto_hide_timer = None
        self._setup_done = False
        # Kept only for test compatibility — the new design has no numeric timer.
        self._start_time = 0.0

    # ------------------------------------------------------------------ #
    # Public API — safe to call from any thread                          #
    # ------------------------------------------------------------------ #

    def show_recording(self):
        """Switch to recording state and reveal the overlay."""
        import time as _time

        with self._lock:
            self._state = "recording"
            self._text = ""
            self._level = 0.0
            self._whisper_mode = False
            self._start_time = _time.time()
        self._cancel_auto_hide()
        self._dispatch_main(b"showMain:")

    def show_transcribing(self):
        """Switch to transcribing state. Keeps any current text."""
        with self._lock:
            self._state = "transcribing"
        self._dispatch_main(b"refreshMain:")

    def show_polishing(self, text: str = ""):
        """Switch to polishing state, optionally replacing the shown text."""
        with self._lock:
            self._state = "polishing"
            if text:
                self._text = _sanitize_display_text(text)
        self._dispatch_main(b"refreshMain:")

    def show_done(self, text: str = "", auto_hide_after: float = 0.6):
        """Switch to done state with the final text, then auto-hide."""
        with self._lock:
            self._state = "done"
            if text:
                self._text = _sanitize_display_text(text)
        self._dispatch_main(b"refreshMain:")
        if auto_hide_after > 0:
            self._schedule_auto_hide(auto_hide_after)

    def show_error(self, text: str = "", auto_hide_after: float = 3.0):
        """Switch to error state with a visible message, then auto-hide."""
        with self._lock:
            self._state = "error"
            if text:
                self._text = _sanitize_display_text(text)
        self._dispatch_main(b"refreshMain:")
        if auto_hide_after > 0:
            self._schedule_auto_hide(auto_hide_after)

    def update_partial_text(self, text):
        """Replace the displayed text with a partial transcription."""
        if text is None:
            return
        with self._lock:
            self._text = _sanitize_display_text(text)
        self._dispatch_main(b"refreshMain:")

    def update_audio_level(self, level: float):
        """Update the audio level driving the waveform bars (0.0-1.0)."""
        with self._lock:
            try:
                self._level = max(0.0, min(1.0, float(level)))
            except Exception:
                self._level = 0.0
        self._dispatch_main(b"updateLevelMain:")

    def set_whisper_mode(self, active: bool):
        """Toggle the subtle whisper-mode indicator on the overlay."""
        changed = False
        with self._lock:
            if self._whisper_mode != bool(active):
                self._whisper_mode = bool(active)
                changed = True
        if changed:
            self._dispatch_main(b"refreshMain:")

    @property
    def whisper_mode(self) -> bool:
        return self._whisper_mode

    def hide(self, delay: float = 0.0):
        """Hide the overlay, optionally after ``delay`` seconds."""
        if delay > 0:
            self._schedule_auto_hide(delay)
            return
        self._dispatch_main(b"hideMain:")

    @property
    def state(self) -> str:
        return self._state

    # ------------------------------------------------------------------ #
    # Main-thread implementations                                         #
    # ------------------------------------------------------------------ #

    def _setup_main(self):
        if self._setup_done:
            return
        screen = AppKit.NSScreen.mainScreen()
        if screen is None:
            return

        initial_frame = self._compute_base_frame(
            screen.visibleFrame(), WINDOW_HEIGHT_MIN
        )

        self._window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            initial_frame,
            AppKit.NSWindowStyleMaskBorderless,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        self._window.setLevel_(AppKit.NSStatusWindowLevel + 1)
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(AppKit.NSColor.clearColor())
        self._window.setHasShadow_(True)
        self._window.setIgnoresMouseEvents_(True)
        self._window.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorStationary
        )
        self._window.setTabbingMode_(AppKit.NSWindowTabbingModeDisallowed)
        self._window.setAlphaValue_(0.0)
        self._window.setReleasedWhenClosed_(False)

        content = self._window.contentView()
        content.setWantsLayer_(True)
        root_layer = content.layer()
        if root_layer is not None:
            root_layer.setCornerRadius_(CORNER_RADIUS)
            try:
                root_layer.setCornerCurve_("continuous")
            except Exception:
                pass
            root_layer.setMasksToBounds_(True)

        # Frosted-glass background — the popover material adapts to dark/light.
        self._effect_view = AppKit.NSVisualEffectView.alloc().initWithFrame_(
            NSMakeRect(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT_MIN)
        )
        try:
            self._effect_view.setMaterial_(AppKit.NSVisualEffectMaterialPopover)
        except Exception:
            self._effect_view.setMaterial_(AppKit.NSVisualEffectMaterialHUDWindow)
        self._effect_view.setBlendingMode_(
            AppKit.NSVisualEffectBlendingModeBehindWindow
        )
        self._effect_view.setState_(AppKit.NSVisualEffectStateActive)
        self._effect_view.setAutoresizingMask_(
            AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable
        )
        effect_layer = self._effect_view.layer()
        if effect_layer is not None:
            effect_layer.setCornerRadius_(CORNER_RADIUS)
            try:
                effect_layer.setCornerCurve_("continuous")
            except Exception:
                pass
            effect_layer.setMasksToBounds_(True)
        content.addSubview_(self._effect_view)

        # State indicator — top-left, aligned with first text line
        indicator_y = WINDOW_HEIGHT_MIN - TEXT_V_PADDING - INDICATOR_SIZE
        self._indicator = _StateIndicatorView.alloc().initWithFrame_(
            NSMakeRect(LEFT_PADDING, indicator_y, INDICATOR_SIZE, INDICATOR_SIZE)
        )
        content.addSubview_(self._indicator)

        # Text field — character-wrapped so CJK, paths, and long tokens do not overflow.
        text_width = WINDOW_WIDTH - TEXT_LEFT - RIGHT_PADDING
        self._text_field = AppKit.NSTextField.alloc().initWithFrame_(
            NSMakeRect(
                TEXT_LEFT,
                TEXT_V_PADDING,
                text_width,
                WINDOW_HEIGHT_MIN - TEXT_V_PADDING * 2,
            )
        )
        self._text_field.setBezeled_(False)
        self._text_field.setDrawsBackground_(False)
        self._text_field.setEditable_(False)
        self._text_field.setSelectable_(False)
        try:
            self._text_field.setTextColor_(AppKit.NSColor.labelColor())
        except Exception:
            self._text_field.setTextColor_(AppKit.NSColor.whiteColor())
        self._text_field.setFont_(
            AppKit.NSFont.systemFontOfSize_weight_(
                TEXT_FONT_SIZE, AppKit.NSFontWeightMedium
            )
        )
        self._text_field.setAlignment_(AppKit.NSTextAlignmentLeft)
        self._text_field.setStringValue_("")
        cell = self._text_field.cell()
        if cell is not None:
            try:
                cell.setUsesSingleLineMode_(False)
                cell.setWraps_(True)
                cell.setTruncatesLastVisibleLine_(False)
                cell.setLineBreakMode_(AppKit.NSLineBreakByCharWrapping)
                cell.setScrollable_(False)
            except Exception:
                pass
        content.addSubview_(self._text_field)

        # Whisper indicator — right side, aligned with first text line
        whisper_y = (
            WINDOW_HEIGHT_MIN
            - TEXT_V_PADDING
            - (TEXT_LINE_HEIGHT + WHISPER_SIZE) / 2
        )
        self._whisper_view = _create_sf_symbol_view(
            "moon.stars.fill",
            13,
            AppKit.NSColor.secondaryLabelColor(),
            NSMakeRect(
                WINDOW_WIDTH - RIGHT_PADDING - WHISPER_SIZE,
                whisper_y,
                WHISPER_SIZE,
                WHISPER_SIZE,
            ),
        )
        if self._whisper_view is not None:
            self._whisper_view.setHidden_(True)
            content.addSubview_(self._whisper_view)

        self._setup_done = True

    def _compute_base_frame(self, screen_frame, height):
        x = screen_frame.origin.x + (screen_frame.size.width - WINDOW_WIDTH) / 2
        y = (
            screen_frame.origin.y
            + screen_frame.size.height
            - height
            - TOP_OFFSET
        )
        return NSMakeRect(x, y, WINDOW_WIDTH, height)

    def _show_main(self):
        if not self._setup_done:
            self._setup_main()
        if self._window is None:
            return

        # Reset to base position so a previous hide-slide doesn't linger.
        screen = AppKit.NSScreen.mainScreen()
        if screen is not None:
            base = self._compute_base_frame(
                screen.visibleFrame(), WINDOW_HEIGHT_MIN
            )
            self._window.setFrame_display_(base, False)
        self._window.setAlphaValue_(0.0)

        # Apply the current state + text WITHOUT animating the resize on
        # the first pass — we want the window to open at whatever height
        # the current text needs from the start, not grow visibly into it.
        self._refresh_main(animate_resize=False)

        self._window.orderFront_(None)
        self._is_visible = True

        AppKit.NSAnimationContext.beginGrouping()
        AppKit.NSAnimationContext.currentContext().setDuration_(SHOW_DURATION)
        self._window.animator().setAlphaValue_(0.95)
        AppKit.NSAnimationContext.endGrouping()

    def _hide_main(self):
        self._cancel_auto_hide()
        with self._lock:
            self._state = "idle"

        if self._indicator is not None:
            self._indicator.stop_all_animations()

        if self._window is None:
            return

        # Slide up + fade out
        frame = self._window.frame()
        slid = NSMakeRect(
            frame.origin.x,
            frame.origin.y + HIDE_SLIDE_DISTANCE,
            frame.size.width,
            frame.size.height,
        )

        AppKit.NSAnimationContext.beginGrouping()
        AppKit.NSAnimationContext.currentContext().setDuration_(HIDE_DURATION)
        self._window.animator().setFrame_display_(slid, True)
        self._window.animator().setAlphaValue_(0.0)
        AppKit.NSAnimationContext.endGrouping()

        self._is_visible = False

        # Clean up indicator content shortly after the fade completes.
        try:
            self._bridge.performSelector_withObject_afterDelay_(
                b"resetAfterHide:", None, HIDE_DURATION + 0.05
            )
        except Exception:
            pass

    def _reset_after_hide_main(self):
        with self._lock:
            if self._is_visible or self._state != "idle":
                return
        if self._indicator is not None:
            self._indicator.set_state("idle")
        if self._text_field is not None:
            self._text_field.setStringValue_("")
        if self._whisper_view is not None:
            self._whisper_view.setHidden_(True)

    def _refresh_main(self, animate_resize: bool = True):
        if not self._setup_done:
            self._setup_main()
        if self._window is None:
            return

        with self._lock:
            state = self._state
            text = self._text
            whisper = self._whisper_mode

        display_text = text if text else STATE_LABELS.get(state, "")

        if self._text_field is not None:
            self._text_field.setStringValue_(display_text)

        has_whisper = state == "recording" and whisper
        if self._whisper_view is not None:
            self._whisper_view.setHidden_(not has_whisper)

        # Recompute text area width (whisper eats into the right side).
        text_right_pad = RIGHT_PADDING + (
            WHISPER_SIZE + WHISPER_TEXT_GAP if has_whisper else 0
        )
        text_width = WINDOW_WIDTH - TEXT_LEFT - text_right_pad

        # Measure how tall the text needs to be at this width.
        text_height = self._measure_text_height(display_text, text_width)
        required_h = int(math.ceil(text_height)) + TEXT_V_PADDING * 2
        new_height = max(
            WINDOW_HEIGHT_MIN,
            min(WINDOW_HEIGHT_MAX, required_h),
        )

        # Resize window (top-anchored) and reposition subviews.
        self._resize_window_main(new_height, animate_resize and self._is_visible)
        self._relayout_main(new_height, text_width, has_whisper)

        # Apply state to the indicator (color + visible child swap).
        if self._indicator is not None:
            self._indicator.set_state(state)

    def _measure_text_height(self, text: str, width: float) -> float:
        if not text or width <= 0:
            return TEXT_LINE_HEIGHT
        try:
            font = AppKit.NSFont.systemFontOfSize_weight_(
                TEXT_FONT_SIZE, AppKit.NSFontWeightMedium
            )
            paragraph = AppKit.NSMutableParagraphStyle.alloc().init()
            paragraph.setLineBreakMode_(AppKit.NSLineBreakByCharWrapping)
            attrs = {
                AppKit.NSFontAttributeName: font,
                AppKit.NSParagraphStyleAttributeName: paragraph,
            }
            attr_str = AppKit.NSAttributedString.alloc().initWithString_attributes_(
                text, attrs
            )
            rect = attr_str.boundingRectWithSize_options_(
                NSMakeSize(width, 10000.0),
                AppKit.NSStringDrawingUsesLineFragmentOrigin
                | AppKit.NSStringDrawingUsesFontLeading,
            )
            return max(TEXT_LINE_HEIGHT, rect.size.height)
        except Exception as e:
            logger.debug(f"Text measure failed: {e}")
            return TEXT_LINE_HEIGHT

    def _resize_window_main(self, new_height: float, animated: bool):
        if self._window is None:
            return
        frame = self._window.frame()
        delta = new_height - frame.size.height
        if abs(delta) < 0.5:
            return
        new_frame = NSMakeRect(
            frame.origin.x,
            frame.origin.y - delta,  # bottom moves down, top stays fixed
            frame.size.width,
            new_height,
        )
        if animated:
            AppKit.NSAnimationContext.beginGrouping()
            AppKit.NSAnimationContext.currentContext().setDuration_(RESIZE_DURATION)
            if _QUARTZ_OK:
                try:
                    timing = Quartz.CAMediaTimingFunction.functionWithName_(
                        Quartz.kCAMediaTimingFunctionEaseInEaseOut
                    )
                    AppKit.NSAnimationContext.currentContext().setTimingFunction_(timing)
                except Exception:
                    pass
            self._window.animator().setFrame_display_(new_frame, True)
            AppKit.NSAnimationContext.endGrouping()
        else:
            self._window.setFrame_display_(new_frame, False)

    def _relayout_main(self, window_height: float, text_width: float, has_whisper: bool):
        # Text field — top-aligned, 14pt from top, full remaining height.
        text_field_h = window_height - TEXT_V_PADDING * 2
        if self._text_field is not None:
            self._text_field.setFrame_(
                NSMakeRect(
                    TEXT_LEFT,
                    TEXT_V_PADDING,
                    text_width,
                    text_field_h,
                )
            )

        # State indicator — pinned at the top so it aligns with the first line.
        indicator_y = window_height - TEXT_V_PADDING - INDICATOR_SIZE
        if self._indicator is not None:
            self._indicator.setFrame_(
                NSMakeRect(
                    LEFT_PADDING,
                    indicator_y,
                    INDICATOR_SIZE,
                    INDICATOR_SIZE,
                )
            )

        # Whisper indicator — right side, centered on the first line.
        if self._whisper_view is not None:
            whisper_y = (
                window_height
                - TEXT_V_PADDING
                - (TEXT_LINE_HEIGHT + WHISPER_SIZE) / 2
            )
            self._whisper_view.setFrame_(
                NSMakeRect(
                    WINDOW_WIDTH - RIGHT_PADDING - WHISPER_SIZE,
                    whisper_y,
                    WHISPER_SIZE,
                    WHISPER_SIZE,
                )
            )

    def _update_level_main(self):
        if self._indicator is None:
            return
        with self._lock:
            level = self._level
        self._indicator.update_level(level)

    # ------------------------------------------------------------------ #
    # Auto-hide                                                           #
    # ------------------------------------------------------------------ #

    def _schedule_auto_hide(self, delay: float):
        self._cancel_auto_hide()
        self._auto_hide_timer = threading.Timer(
            delay, lambda: self._dispatch_main(b"hideMain:")
        )
        self._auto_hide_timer.daemon = True
        self._auto_hide_timer.start()

    def _cancel_auto_hide(self):
        if self._auto_hide_timer is not None:
            try:
                self._auto_hide_timer.cancel()
            except Exception:
                pass
            self._auto_hide_timer = None

    # ------------------------------------------------------------------ #
    # Main-thread dispatch helper                                         #
    # ------------------------------------------------------------------ #

    def _dispatch_main(self, selector: bytes):
        try:
            self._bridge.performSelectorOnMainThread_withObject_waitUntilDone_(
                selector, None, False
            )
        except Exception as e:
            logger.debug(f"Main-thread dispatch failed for {selector!r}: {e}")
