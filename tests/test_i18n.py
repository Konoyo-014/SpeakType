from speaktype.i18n import localized_hotkey_display, set_language


def test_localized_hotkey_display_follows_ui_language():
    try:
        set_language("zh")
        assert localized_hotkey_display("right_cmd") == "右 ⌘"
        assert localized_hotkey_display("ctrl+shift+space") == "⌃⇧空格"

        set_language("en")
        assert localized_hotkey_display("right_cmd") == "Right ⌘"
        assert localized_hotkey_display("ctrl+shift+space") == "⌃⇧Space"
    finally:
        set_language("zh")


def test_localized_hotkey_display_keeps_unknown_custom_hotkey():
    set_language("zh")

    assert localized_hotkey_display("custom-key") == "custom-key"
