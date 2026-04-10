"""Tests for the GitHub Releases version-check helper."""

import json

import pytest

from speaktype import updates
from speaktype.updates import (
    UpdateCheckResult,
    check_for_update,
    is_newer,
    parse_version,
)


class TestParseVersion:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("2.1.0", (2, 1, 0)),
            ("v2.1.0", (2, 1, 0)),
            ("V2.1.0", (2, 1, 0)),
            ("2.1", (2, 1, 0)),
            ("2", (2, 0, 0)),
            ("2.0.1d3", (2, 0, 1)),
            ("2.0.1-beta.4", (2, 0, 1)),
            ("2.0.1+build5", (2, 0, 1)),
            ("3.10.0", (3, 10, 0)),
            ("", (0, 0, 0)),
            ("garbage", (0, 0, 0)),
        ],
    )
    def test_parse(self, raw, expected):
        assert parse_version(raw) == expected


class TestIsNewer:
    def test_is_newer_strict(self):
        assert is_newer("2.0.1", "2.1.0") is True
        assert is_newer("2.0.1", "2.0.2") is True
        assert is_newer("2.0.1", "3.0.0") is True

    def test_not_newer_for_equal(self):
        assert is_newer("2.0.1", "2.0.1") is False

    def test_not_newer_for_older(self):
        assert is_newer("2.1.0", "2.0.9") is False

    def test_v_prefix_ignored(self):
        assert is_newer("v2.0.1", "v2.1.0") is True

    def test_two_digit_minor_compares_numerically(self):
        assert is_newer("2.9.0", "2.10.0") is True


class TestCheckForUpdate:
    def _payload(self, tag="v2.1.0", asset_name="SpeakType-2.1.0.dmg"):
        return json.dumps(
            {
                "tag_name": tag,
                "html_url": "https://github.com/Konoyo-014/SpeakType/releases/tag/" + tag,
                "assets": [
                    {
                        "name": asset_name,
                        "browser_download_url": f"https://example.com/{asset_name}",
                    },
                    {
                        "name": "SpeakType-2.1.0-source.zip",
                        "browser_download_url": "https://example.com/source.zip",
                    },
                ],
            }
        )

    def test_returns_update_when_newer(self):
        def fetcher(url):
            assert "Konoyo-014" in url
            return 200, self._payload()

        result = check_for_update("2.0.1", fetcher=fetcher)
        assert isinstance(result, UpdateCheckResult)
        assert result.has_update
        assert result.latest_version == "v2.1.0"
        assert result.is_newer
        assert result.download_url == "https://example.com/SpeakType-2.1.0.dmg"
        assert "releases/tag/v2.1.0" in (result.release_url or "")
        assert result.error is None

    def test_returns_no_update_when_equal(self):
        def fetcher(url):
            return 200, self._payload(tag="v2.1.0")

        result = check_for_update("2.1.0", fetcher=fetcher)
        assert result.has_update is False
        assert result.latest_version == "v2.1.0"

    def test_handles_http_error(self):
        def fetcher(url):
            return 503, "<html>503</html>"

        result = check_for_update("2.0.1", fetcher=fetcher)
        assert result.has_update is False
        assert result.error and "503" in result.error
        assert result.latest_version is None

    def test_handles_network_exception(self):
        def fetcher(url):
            raise OSError("connection refused")

        result = check_for_update("2.0.1", fetcher=fetcher)
        assert result.has_update is False
        assert result.error == "connection refused"

    def test_handles_malformed_json(self):
        def fetcher(url):
            return 200, "not json{{"

        result = check_for_update("2.0.1", fetcher=fetcher)
        assert result.has_update is False
        assert result.error and "Malformed" in result.error

    def test_handles_missing_tag(self):
        def fetcher(url):
            return 200, json.dumps({"assets": []})

        result = check_for_update("2.0.1", fetcher=fetcher)
        assert result.latest_version is None
        assert result.error == "No tag in latest release"

    def test_no_dmg_asset_in_payload(self):
        def fetcher(url):
            return 200, json.dumps(
                {
                    "tag_name": "v2.1.0",
                    "html_url": "https://example.com/release",
                    "assets": [
                        {"name": "checksums.txt", "browser_download_url": "https://x"},
                    ],
                }
            )

        result = check_for_update("2.0.1", fetcher=fetcher)
        assert result.download_url is None
        assert result.release_url == "https://example.com/release"
        assert result.has_update
