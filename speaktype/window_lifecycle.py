"""Shared helpers for native utility-window lifecycle management."""


def controller_window_is_visible(controller) -> bool:
    window = getattr(controller, "window", None)
    if window is None:
        return False
    is_visible = getattr(window, "isVisible", None)
    if not callable(is_visible):
        return False
    try:
        return bool(is_visible())
    except Exception:
        return False


def show_or_create_window_controller(current_controller, factory):
    if controller_window_is_visible(current_controller):
        current_controller.show()
        return current_controller
    controller = factory()
    controller.show()
    return controller
