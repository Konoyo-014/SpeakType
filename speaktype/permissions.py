"""macOS input-control permission helpers."""

from dataclasses import dataclass
import logging
import subprocess

import Quartz
from ApplicationServices import (
    AXIsProcessTrusted,
    AXIsProcessTrustedWithOptions,
    kAXTrustedCheckOptionPrompt,
)

logger = logging.getLogger("speaktype")
RESETTABLE_PERMISSION_SERVICES = ("Accessibility", "ListenEvent", "PostEvent")


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


def reset_permissions(bundle_id: str, services: tuple[str, ...] = RESETTABLE_PERMISSION_SERVICES):
    """Clear TCC grants for the bundled app so the next request re-prompts the user."""
    for service in services:
        result = subprocess.run(
            ["tccutil", "reset", service, bundle_id],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning(
                "Failed to reset %s permission for %s: %s",
                service,
                bundle_id,
                (result.stderr or "").strip() or f"exit {result.returncode}",
            )


def refresh_permissions_for_update(bundle_id: str):
    """Force a clean permission re-request after a bundled app update."""
    reset_permissions(bundle_id)
    request_missing_permissions(PermissionStatus(False, False, False))


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
