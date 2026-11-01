from dataclasses import dataclass

from CoreFoundation import CFEqual

from .context import get_active_app
from .inserter import _copy_ax_attribute, _get_focused_element, _prepare_target_app, _selected_utf16_range


@dataclass(frozen=True)
class TargetField:
    app: dict
    element: object | None
    value: str | None
    selection: tuple[int, int] | None


def capture_target_field(app_info: dict) -> TargetField:
    current = get_active_app()
    if current.get("pid") != app_info.get("pid"):
        raise RuntimeError("The selected application changed before recording started")
    element = _get_focused_element()
    value = _copy_ax_attribute(element, "AXValue") if element is not None else None
    selection = _selected_utf16_range(element) if element is not None else None
    return TargetField(dict(app_info), element, value if isinstance(value, str) else None, selection)


def prepare_unchanged_target(target: TargetField) -> bool:
    app = target.app
    pid = _prepare_target_app(bundle_id=app.get("bundle_id", ""), app_name=app.get("name", ""),
                              target_pid=app.get("pid"))
    if pid is None:
        return False
    if target.element is None:
        return True
    current = _get_focused_element()
    if current is None or not CFEqual(current, target.element):
        return False
    if target.value is not None and _copy_ax_attribute(current, "AXValue") != target.value:
        return False
    if target.selection is not None and _selected_utf16_range(current) != target.selection:
        return False
    return True
