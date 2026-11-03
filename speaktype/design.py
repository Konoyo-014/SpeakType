import AppKit
import objc
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


def color(name):
    return _COLORS[name]()


def apply_window(window):
    window.setAppearance_(None)
    window.setBackgroundColor_(color("background"))
    window.setTitlebarAppearsTransparent_(True)
    window.setToolbarStyle_(AppKit.NSWindowToolbarStyleUnifiedCompact)


def material_view(frame, material="sidebar", radius=0):
    materials = {
        "sidebar": AppKit.NSVisualEffectMaterialSidebar,
        "popover": AppKit.NSVisualEffectMaterialPopover,
        "content": AppKit.NSVisualEffectMaterialUnderWindowBackground,
    }
    view = AppKit.NSVisualEffectView.alloc().initWithFrame_(frame)
    view.setMaterial_(materials[material])
    view.setBlendingMode_(AppKit.NSVisualEffectBlendingModeBehindWindow)
    view.setState_(AppKit.NSVisualEffectStateFollowsWindowActiveState)
    if radius:
        view.setWantsLayer_(True)
        view.layer().setCornerRadius_(radius)
        view.layer().setCornerCurve_("continuous")
        view.layer().setMasksToBounds_(True)
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
        style_panel(button, "accent_soft" if selected else "sidebar", radius=7, border=False)
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
