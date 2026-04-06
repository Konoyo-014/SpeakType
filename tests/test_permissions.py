"""Tests for macOS permission helpers."""

from speaktype import permissions


def test_get_permission_status_reads_all_three_checks(monkeypatch):
    monkeypatch.setattr(permissions, "AXIsProcessTrusted", lambda: True)
    monkeypatch.setattr(permissions.Quartz, "CGPreflightListenEventAccess", lambda: False)
    monkeypatch.setattr(permissions.Quartz, "CGPreflightPostEventAccess", lambda: True)

    status = permissions.get_permission_status()

    assert status.accessibility is True
    assert status.listen_event is False
    assert status.post_event is True
    assert status.all_granted is False


def test_request_missing_permissions_only_requests_missing(monkeypatch):
    calls = []

    monkeypatch.setattr(
        permissions,
        "AXIsProcessTrustedWithOptions",
        lambda options: calls.append(("ax", options)),
    )
    monkeypatch.setattr(
        permissions.Quartz,
        "CGRequestListenEventAccess",
        lambda: calls.append(("listen", None)),
    )
    monkeypatch.setattr(
        permissions.Quartz,
        "CGRequestPostEventAccess",
        lambda: calls.append(("post", None)),
    )

    permissions.request_missing_permissions(
        permissions.PermissionStatus(
            accessibility=False,
            listen_event=True,
            post_event=False,
        )
    )

    assert calls == [
        ("ax", {permissions.kAXTrustedCheckOptionPrompt: True}),
        ("post", None),
    ]
