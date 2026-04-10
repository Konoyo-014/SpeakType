"""GitHub Releases version check.

Hits the public GitHub Releases API to discover the latest published tag,
compares it against the running app version, and returns a small dataclass
the menubar handler can present to the user. Designed to fail closed —
network errors and rate limits surface as a non-fatal "no info available".
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger("speaktype.updates")

GITHUB_OWNER = "Konoyo-014"
GITHUB_REPO = "SpeakType"
RELEASES_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
HTTP_TIMEOUT = 6  # seconds; menubar UX should not block forever


@dataclass(frozen=True)
class UpdateCheckResult:
    """Outcome of an update check."""

    current_version: str
    latest_version: Optional[str]
    is_newer: bool
    download_url: Optional[str]
    release_url: Optional[str]
    error: Optional[str]

    @property
    def has_update(self) -> bool:
        return self.is_newer and bool(self.latest_version)


def parse_version(version: str) -> tuple[int, ...]:
    """Parse a SemVer-ish string into a comparable tuple.

    Strips a leading 'v' and any '+build' / pre-release suffix the GitHub
    tag may carry. Missing pieces default to 0 so '2.1' compares the same
    as '2.1.0'. Non-numeric segments collapse to 0 (best-effort).
    """
    if not version:
        return (0, 0, 0)
    cleaned = version.strip().lstrip("vV")
    # Drop a build suffix like '2.1.0d1' or '2.1.0-beta.2'
    cleaned = re.split(r"[-+]", cleaned, maxsplit=1)[0]
    # Strip py2app-style debug markers ('2.0.1d1' -> '2.0.1')
    cleaned = re.sub(r"(?<=\d)([abdfc])\d+$", "", cleaned)
    parts = cleaned.split(".")
    numeric: list[int] = []
    for part in parts:
        match = re.match(r"^(\d+)", part)
        numeric.append(int(match.group(1)) if match else 0)
    while len(numeric) < 3:
        numeric.append(0)
    return tuple(numeric)


def is_newer(current: str, candidate: str) -> bool:
    """Return True when candidate is strictly newer than current."""
    return parse_version(candidate) > parse_version(current)


def check_for_update(current_version: str, *, fetcher=None) -> UpdateCheckResult:
    """Look up the latest GitHub release for SpeakType.

    Args:
        current_version: The version this app is reporting (typically
            ``speaktype.__version__`` or the bundled CFBundleVersion).
        fetcher: Optional injection point for tests. Should accept a URL
            and return ``(status_code, body_text)``. Defaults to ``requests.get``.
    """
    if fetcher is None:
        fetcher = _default_fetcher

    try:
        status_code, body = fetcher(RELEASES_URL)
    except Exception as e:
        logger.info(f"Update check failed: {e}")
        return UpdateCheckResult(
            current_version=current_version,
            latest_version=None,
            is_newer=False,
            download_url=None,
            release_url=None,
            error=str(e),
        )

    if status_code != 200:
        return UpdateCheckResult(
            current_version=current_version,
            latest_version=None,
            is_newer=False,
            download_url=None,
            release_url=None,
            error=f"GitHub API returned HTTP {status_code}",
        )

    try:
        payload = json.loads(body) if isinstance(body, str) else body
    except Exception as e:
        return UpdateCheckResult(
            current_version=current_version,
            latest_version=None,
            is_newer=False,
            download_url=None,
            release_url=None,
            error=f"Malformed release payload: {e}",
        )

    latest = payload.get("tag_name") or payload.get("name") or ""
    release_url = payload.get("html_url")
    download_url = _pick_dmg_asset(payload.get("assets") or [])

    if not latest:
        return UpdateCheckResult(
            current_version=current_version,
            latest_version=None,
            is_newer=False,
            download_url=download_url,
            release_url=release_url,
            error="No tag in latest release",
        )

    return UpdateCheckResult(
        current_version=current_version,
        latest_version=latest,
        is_newer=is_newer(current_version, latest),
        download_url=download_url,
        release_url=release_url,
        error=None,
    )


def _pick_dmg_asset(assets: list) -> Optional[str]:
    for asset in assets:
        name = asset.get("name") or ""
        if name.lower().endswith(".dmg"):
            return asset.get("browser_download_url")
    return None


def _default_fetcher(url: str) -> tuple[int, str]:
    resp = requests.get(
        url,
        timeout=HTTP_TIMEOUT,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "SpeakType-update-check",
        },
    )
    return resp.status_code, resp.text
