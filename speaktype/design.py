import AppKit
import objc
import Quartz
from Foundation import NSMakeRect


_COLORS = {
    "background": AppKit.NSColor.windowBackgroundColor,
    "surface": AppKit.NSColor.textBackgroundColor,
    "sidebar": AppKit.NSColor.windowBackgroundColor,
    "text": AppKit.NSColor.labelColor,
    "muted": AppKit.NSColor.secondaryLabelColor,
    "accent": AppKit.NSColor.controlAccentColor,
    "accent_soft": AppKit.NSColor.unemphasizedSelectedContentBackgroundColor,
    "sidebar_text": AppKit.NSColor.labelColor,
    "sidebar_muted": AppKit.NSColor.secondaryLabelColor,
    "line": AppKit.NSColor.separatorColor,
}

_PALETTE = {
    "background": ((0.965, 0.961, 0.945), (0.105, 0.125, 0.121)),
    "surface": ((1.0, 0.997, 0.985), (0.145, 0.169, 0.161)),
    "sidebar": ((0.075, 0.161, 0.145), (0.060, 0.105, 0.095)),
    "sidebar_selected": ((0.16, 0.29, 0.25), (0.15, 0.26, 0.22)),
    "sidebar_text": ((0.94, 0.96, 0.92), (0.94, 0.96, 0.92)),
    "sidebar_muted": ((0.65, 0.74, 0.69), (0.65, 0.74, 0.69)),
    "text": ((0.12, 0.19, 0.17), (0.92, 0.94, 0.90)),
    "muted": ((0.39, 0.45, 0.41), (0.65, 0.73, 0.68)),
    "accent": ((0.10, 0.39, 0.31), (0.36, 0.75, 0.61)),
    "accent_soft": ((0.88, 0.93, 0.88), (0.16, 0.27, 0.22)),
    "line": ((0.85, 0.88, 0.83), (0.25, 0.32, 0.28)),
}


def color(name):
    if name in _PALETTE:
        def resolve(appearance):
            match = appearance.bestMatchFromAppearancesWithNames_(
                [AppKit.NSAppearanceNameAqua, AppKit.NSAppearanceNameDarkAqua])
            values = _PALETTE[name][int(match == AppKit.NSAppearanceNameDarkAqua)]
            return AppKit.NSColor.colorWithSRGBRed_green_blue_alpha_(*values, 1.0)
        return AppKit.NSColor.colorWithName_dynamicProvider_("SpeakType." + name, resolve)
    return _COLORS[name]()


def apply_window(window):
    window.setAppearance_(None)
    window.setBackgroundColor_(color("background"))
    window.setTitlebarAppearsTransparent_(True)
    window.setToolbarStyle_(AppKit.NSWindowToolbarStyleUnifiedCompact)


def material_view(frame, material="sidebar", radius=0):
    backgrounds = {"sidebar": "sidebar", "popover": "surface", "content": "surface", "background": "background"}
    view = AppKit.NSView.alloc().initWithFrame_(frame)
    style_panel(view, backgrounds[material], radius=radius)
    return view


class _PanelBackground(AppKit.NSView):
    def initWithFrame_(self, frame):
        self = objc.super(_PanelBackground, self).initWithFrame_(frame)
        if self is not None:
            self.background = "surface"
            self.radius = 0
            self.border = False
        return self

    def hitTest_(self, point):
        return None

    def viewDidChangeEffectiveAppearance(self):
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        bounds = self.bounds()
        path = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            bounds, self.radius, self.radius)
        color(self.background).setFill()
        path.fill()
        if self.border:
            color("line").setStroke()
            path.setLineWidth_(1)
            path.stroke()


def style_panel(view, background="surface", radius=0, border=False):
    panel = next((child for child in view.subviews() if isinstance(child, _PanelBackground)), None)
    if panel is None:
        panel = _PanelBackground.alloc().initWithFrame_(NSMakeRect(
            0, 0, view.bounds().size.width, view.bounds().size.height))
        panel.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
        view.addSubview_positioned_relativeTo_(panel, AppKit.NSWindowBelow, None)
    panel.background = background
    panel.radius = radius
    panel.border = border
    panel.setNeedsDisplay_(True)
    return view


def style_button(button, primary=False, sidebar=False, selected=False):
    button.setFont_(AppKit.NSFont.systemFontOfSize_(13))
    button.setImageHugsTitle_(True)
    button.setFocusRingType_(AppKit.NSFocusRingTypeExterior)
    if sidebar:
        button.setBordered_(False)
        button.setAlignment_(AppKit.NSTextAlignmentLeft)
        button.setContentTintColor_(color("sidebar_text"))
        button.setWantsLayer_(True)
        button.layer().setCornerRadius_(8)
        button.layer().setBackgroundColor_((color("sidebar_selected") if selected else AppKit.NSColor.clearColor()).CGColor())
    else:
        button.setBordered_(True)
        button.setBezelStyle_(AppKit.NSBezelStyleRounded)
        button.setBezelColor_(color("accent") if primary else None)
        button.setContentTintColor_(None)
    return button


def style_field(field):
    field.setFont_(AppKit.NSFont.systemFontOfSize_(13))
    field.setTextColor_(color("text"))
    field.setFocusRingType_(AppKit.NSFocusRingTypeExterior)
    return field


def symbol(name, description, size=16):
    image = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, description)
    if image is None:
        raise ValueError(f"Unknown SF Symbol: {name}")
    configuration = AppKit.NSImageSymbolConfiguration.configurationWithPointSize_weight_(size, AppKit.NSFontWeightMedium)
    return image.imageWithSymbolConfiguration_(configuration)
