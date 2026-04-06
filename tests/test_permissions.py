"""Tests for macOS permission helpers."""

from types import SimpleNamespace

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


def test_reset_permissions_resets_all_supported_services(monkeypatch):
    calls = []

    monkeypatch.setattr(
        permissions.subprocess,
        "run",
        lambda cmd, capture_output, text: calls.append((cmd, capture_output, text))
        or SimpleNamespace(returncode=0, stderr=""),
    )

    permissions.reset_permissions("com.speaktype.app")

    assert calls == [
        (["tccutil", "reset", "Accessibility", "com.speaktype.app"], True, True),
        (["tccutil", "reset", "ListenEvent", "com.speaktype.app"], True, True),
        (["tccutil", "reset", "PostEvent", "com.speaktype.app"], True, True),
    ]


def test_refresh_permissions_for_update_forces_clean_reprompt(monkeypatch):
    calls = []

    monkeypatch.setattr(
        permissions,
        "reset_permissions",
        lambda bundle_id: calls.append(("reset", bundle_id)),
    )
    monkeypatch.setattr(
        permissions,
        "request_missing_permissions",
        lambda status=None: calls.append(("request", status)),
    )

    permissions.refresh_permissions_for_update("com.speaktype.app")

    assert calls == [
        ("reset", "com.speaktype.app"),
        ("request", permissions.PermissionStatus(False, False, False)),
    ]
