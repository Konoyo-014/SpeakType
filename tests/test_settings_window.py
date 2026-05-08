from speaktype.settings_window import (
    SETTING_KEYS_BY_SECTION,
    SettingsWindowController,
    settings_section_ids,
    settings_section_keys,
)


class _FakeTextField:
    def __init__(self, value):
        self._value = str(value)

    def stringValue(self):
        return self._value


class _FakeCheckbox:
    def __init__(self, state):
        self._state = state

    def state(self):
        return self._state


def test_settings_sections_cover_each_key_once():
    keys = []
    for section_id in settings_section_ids():
        keys.extend(settings_section_keys(section_id))

    assert settings_section_ids() == ("general", "models", "features", "hotwords", "system")
    assert len(keys) == len(set(keys))
    assert "hotword_learning_enabled" in SETTING_KEYS_BY_SECTION["hotwords"]
    assert "auto_start" in SETTING_KEYS_BY_SECTION["system"]


def test_read_visible_controls_clamps_hotword_numbers():
    controller = SettingsWindowController({"hotword_max_context_terms": 30})
    controller._controls = {
        "hotword_max_context_terms": (
            "number",
            _FakeTextField("999"),
            {"type": "int", "min": 1, "max": 80},
        )
    }

    result = controller._read_visible_controls({"hotword_max_context_terms": 30})

    assert result["hotword_max_context_terms"] == 80


def test_read_visible_controls_preserves_fallback_for_invalid_number():
    controller = SettingsWindowController({"hotword_observation_stable_seconds": 1.2})
    controller._controls = {
        "hotword_observation_stable_seconds": (
            "number",
            _FakeTextField("not-a-number"),
            {"type": "float", "min": 0.2, "max": 10.0},
        )
    }

    result = controller._read_visible_controls({"hotword_observation_stable_seconds": 1.2})

    assert result["hotword_observation_stable_seconds"] == 1.2


def test_read_visible_controls_reads_checkbox_state():
    controller = SettingsWindowController({"streaming_preview": True})
    controller._controls = {
        "streaming_preview": ("checkbox", _FakeCheckbox(0), None),
    }

    result = controller._read_visible_controls({"streaming_preview": True})

    assert result["streaming_preview"] is False
