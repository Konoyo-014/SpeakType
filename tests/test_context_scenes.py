"""Tests for the context module's app -> scene/tone mapping."""

import pytest

from speaktype.context import (
    CASUAL_APPS,
    CODE_APPS,
    FORMAL_APPS,
    NOTE_APPS,
    get_scene_for_app,
    get_tone_for_app,
)


class TestGetTone:
    @pytest.mark.parametrize("bundle_id", sorted(FORMAL_APPS))
    def test_formal_apps(self, bundle_id):
        assert get_tone_for_app({"bundle_id": bundle_id}) == "formal"

    @pytest.mark.parametrize("bundle_id", sorted(CASUAL_APPS))
    def test_casual_apps(self, bundle_id):
        assert get_tone_for_app({"bundle_id": bundle_id}) == "casual"

    @pytest.mark.parametrize("bundle_id", sorted(CODE_APPS))
    def test_code_apps(self, bundle_id):
        assert get_tone_for_app({"bundle_id": bundle_id}) == "technical"

    def test_unknown_app_neutral(self):
        assert get_tone_for_app({"bundle_id": "com.example.unknown"}) == "neutral"

    def test_missing_bundle_id_neutral(self):
        assert get_tone_for_app({}) == "neutral"


class TestGetScene:
    def test_formal_app_maps_to_email(self):
        assert get_scene_for_app({"bundle_id": "com.apple.mail"}) == "email"

    def test_casual_app_maps_to_chat(self):
        assert get_scene_for_app({"bundle_id": "com.tinyspeck.slackmacgap"}) == "chat"

    def test_code_app_maps_to_code(self):
        assert get_scene_for_app({"bundle_id": "com.microsoft.VSCode"}) == "code"

    def test_note_app_maps_to_notes(self):
        assert get_scene_for_app({"bundle_id": "md.obsidian"}) == "notes"

    def test_unknown_app_default(self):
        assert get_scene_for_app({"bundle_id": "com.example.unknown"}) == "default"

    def test_missing_bundle_id_default(self):
        assert get_scene_for_app({}) == "default"

    def test_empty_dict_default(self):
        assert get_scene_for_app({"bundle_id": ""}) == "default"
