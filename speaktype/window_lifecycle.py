def controller_window_is_visible(controller) -> bool:
    if controller is None:
        return False
    window = controller.window
    if window is None:
        return False
    return bool(window.isVisible())


def show_or_create_window_controller(current_controller, factory):
    if controller_window_is_visible(current_controller):
        current_controller.show()
        return current_controller
    controller = factory()
    controller.show()
    if controller.window is None or controller.window.isReleasedWhenClosed():
        raise RuntimeError("Native window controllers must retain their windows after closing")
    return controller
