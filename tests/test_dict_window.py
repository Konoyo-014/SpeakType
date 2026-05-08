from speaktype import dict_window
from speaktype.dict_window import (
    DictWindowController,
    dict_counts_text,
    dict_section_ids,
    format_correction_rows,
    format_snippet_rows,
    format_word_rows,
    selected_line_index,
)


def test_selected_line_index_maps_text_offset_to_item():
    text = '  [0] "brb" -> be right back\n  [1] "sig" -> signature\n  [2] "ty" -> thank you'

    assert selected_line_index(text, 0, 3) == 0
    assert selected_line_index(text, text.index("[1]"), 3) == 1
    assert selected_line_index(text, text.index("[2]"), 3) == 2


def test_selected_line_index_rejects_empty_and_out_of_range():
    assert selected_line_index("", 0, 0) is None
    assert selected_line_index("only one", -1, 1) is None
    assert selected_line_index("line 0\nline 1", 30, 1) is None


def test_dict_sections_are_stable_for_native_navigation():
    assert dict_section_ids() == ("words", "snippets", "corrections")


def test_formatters_preserve_long_dictionary_content():
    long_model = "huihui_ai/qwen3.5-abliterated:9b-Claude"
    snippet_text = "ollama pull huihui_ai/qwen3.5-abliterated:9b-Claude"

    words = format_word_rows(["Qwen3-ASR", long_model])
    snippets = format_snippet_rows(
        [{"trigger": "install model", "text": snippet_text, "description": "Ollama"}]
    )
    corrections = format_correction_rows(
        [{"wrong": "Q win three ASR", "right": "Qwen3-ASR"}]
    )

    assert long_model in words
    assert snippet_text in snippets
    assert "Ollama" in snippets
    assert '"Q win three ASR" -> "Qwen3-ASR"' in corrections


def test_dict_counts_text_includes_each_collection_size():
    text = dict_counts_text(["one", "two"], [{"trigger": "a"}], [{"wrong": "b"}])

    assert "2" in text
    assert "1" in text


class _FakeSnippets:
    def get_all(self):
        return []


class _FakeCorrections:
    def get_all(self):
        return []


class _FakeView:
    def __init__(self):
        self.hidden = None

    def setHidden_(self, value):
        self.hidden = value


class _FakeButton:
    def __init__(self):
        self.state = None

    def setState_(self, value):
        self.state = value


class _FakeStatus:
    def __init__(self):
        self.value = ""
        self.color = None

    def setStringValue_(self, value):
        self.value = value

    def setTextColor_(self, value):
        self.color = value


def test_switching_sections_replaces_stale_dirty_status(monkeypatch):
    monkeypatch.setattr(dict_window, "load_custom_dictionary", lambda: [])
    controller = DictWindowController(_FakeSnippets(), _FakeCorrections())
    controller._section_views = {"words": _FakeView(), "corrections": _FakeView()}
    controller._section_buttons = {"words": _FakeButton(), "corrections": _FakeButton()}
    controller._status_field = _FakeStatus()
    controller._active_section = "words"
    controller._dirty = True

    controller._show_section("corrections")

    assert controller._section_views["words"].hidden is True
    assert controller._section_views["corrections"].hidden is False
    assert "未保存" in controller._status_field.value or "Unsaved" in controller._status_field.value


def test_dirty_dictionary_close_requires_second_close(monkeypatch):
    monkeypatch.setattr(dict_window, "load_custom_dictionary", lambda: [])
    controller = DictWindowController(_FakeSnippets(), _FakeCorrections())
    controller._status_field = _FakeStatus()
    controller._dirty = True
    controller._close_discard_armed = False

    assert controller._request_close() is False
    assert controller._dirty is True
    assert controller._close_discard_armed is True
    assert "未保存" in controller._status_field.value or "Unsaved" in controller._status_field.value

    assert controller._request_close() is True


def test_dictionary_edit_resets_pending_discard_confirmation(monkeypatch):
    monkeypatch.setattr(dict_window, "load_custom_dictionary", lambda: [])
    controller = DictWindowController(_FakeSnippets(), _FakeCorrections())
    controller._status_field = _FakeStatus()
    controller._dirty = True

    assert controller._request_close() is False
    controller._set_status("changed again", dirty=True)

    assert controller._close_discard_armed is False
    assert controller._request_close() is False
