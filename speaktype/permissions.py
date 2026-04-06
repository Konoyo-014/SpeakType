"""macOS input-control permission helpers."""

from dataclasses import dataclass

import Quartz
from ApplicationServices import (
    AXIsProcessTrusted,
    AXIsProcessTrustedWithOptions,
    kAXTrustedCheckOptionPrompt,
)


@dataclass(frozen=True)
class PermissionStatus:
    accessibility: bool
    listen_event: bool
    post_event: bool

    @property
    def all_granted(self) -> bool:
        return self.accessibility and self.listen_event and self.post_event


def get_permission_status() -> PermissionStatus:
    """Read current input-control permissions for this process."""
    return PermissionStatus(
        accessibility=_safe_bool(AXIsProcessTrusted),
        listen_event=_safe_bool(Quartz.CGPreflightListenEventAccess),
        post_event=_safe_bool(Quartz.CGPreflightPostEventAccess),
    )


def request_missing_permissions(status: PermissionStatus | None = None):
    """Trigger system permission prompts for any missing input-control access."""
    status = status or get_permission_status()

    if not status.accessibility:
        _safe_call(AXIsProcessTrustedWithOptions, {kAXTrustedCheckOptionPrompt: True})
    if not status.listen_event:
        _safe_call(Quartz.CGRequestListenEventAccess)
    if not status.post_event:
        _safe_call(Quartz.CGRequestPostEventAccess)


def _safe_bool(func):
    try:
        return bool(func())
    except Exception:
        return False


def _safe_call(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception:
        return None
