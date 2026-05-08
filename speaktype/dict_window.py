"""Custom dictionary editor — native macOS window for managing custom words, snippets, and corrections."""

import logging
import AppKit
import objc
from Foundation import NSObject, NSMakeRect, NSMakeSize
from .config import load_custom_dictionary, save_custom_dictionary
from .corrections import CorrectionStore
from .snippets import SnippetLibrary
from .i18n import t

logger = logging.getLogger("speaktype.dict_window")


DICT_SECTION_ORDER = ("words", "snippets", "corrections")


def selected_line_index(text: str, selection_location: int, item_count: int) -> int | None:
    """Return the list row touched by a text-view selection."""
    if item_count <= 0:
        return None
    try:
        location = int(selection_location)
    except (TypeError, ValueError):
        return None
    if location < 0:
        return None
    location = min(location, len(text or ""))
    index = (text or "")[:location].count("\n")
    if 0 <= index < item_count:
        return index
    return None


def dict_section_ids() -> tuple[str, ...]:
    return DICT_SECTION_ORDER


def format_word_rows(words: list[str]) -> str:
    return "\n".join(f"  {word}" for word in words) if words else f"  {t('dict_no_words')}"


def format_snippet_rows(snippets: list[dict]) -> str:
    lines = []
    for i, snippet in enumerate(snippets):
        trigger = snippet.get("trigger", "")
        text = snippet.get("text", "")
        desc = snippet.get("description", "")
        line = f"  [{i}] \"{trigger}\" -> {text}"
        if desc:
            line += f"  ({desc})"
        lines.append(line)
    return "\n".join(lines) if lines else f"  {t('dict_no_snippets')}"


def format_correction_rows(corrections: list[dict]) -> str:
    lines = []
    for i, correction in enumerate(corrections):
        wrong = correction.get("wrong", "")
        right = correction.get("right", "")
        lines.append(f"  [{i}] \"{wrong}\" -> \"{right}\"")
    return "\n".join(lines) if lines else f"  {t('dict_no_corrections')}"


def dict_counts_text(words: list, snippets: list, corrections: list) -> str:
    return t(
        "dict_counts",
        words=len(words),
        snippets=len(snippets),
        corrections=len(corrections),
    )


class _DictDelegate(NSObject):
    """ObjC delegate for dictionary editor buttons."""

    def initWithController_(self, controller):
        self = objc.super(_DictDelegate, self).init()
        if self is not None:
            self._controller = controller
        return self

    def onAddWord_(self, sender):
        self._controller._add_word()

    def onRemoveWord_(self, sender):
        self._controller._remove_word()

    def onAddSnippet_(self, sender):
        self._controller._add_snippet()

    def onRemoveSnippet_(self, sender):
        self._controller._remove_snippet()

    def onAddCorrection_(self, sender):
        self._controller._add_correction()

    def onRemoveCorrection_(self, sender):
        self._controller._remove_correction()

    def onSave_(self, sender):
        self._controller._do_save()

    def onClose_(self, sender):
        if self._controller._request_close():
            self._controller.window.close()

    def windowShouldClose_(self, sender):
        return bool(self._controller._request_close())

    def onShowWords_(self, sender):
        self._controller._show_section("words")

    def onShowSnippets_(self, sender):
        self._controller._show_section("snippets")

    def onShowCorrections_(self, sender):
        self._controller._show_section("corrections")


class DictWindowController:
    """Manages the custom dictionary, snippets, and correction editor window."""

    WINDOW_WIDTH = 720
    WINDOW_HEIGHT = 540
    BUTTON_BAR_HEIGHT = 56
    SIDEBAR_WIDTH = 168
    CONTENT_X = 192
    CONTENT_WIDTH = 500

    def __init__(self, snippets: SnippetLibrary, corrections: CorrectionStore | None = None):
        self.snippets = snippets
        self.corrections = corrections or CorrectionStore()
        self.window = None
        self._delegate = None
        self._word_list_view = None
        self._snippet_list_view = None
        self._correction_list_view = None
        self._word_field = None
        self._snippet_trigger_field = None
        self._snippet_text_field = None
        self._correction_wrong_field = None
        self._correction_right_field = None
        self._status_field = None
        self._counts_field = None
        self._section_views = {}
        self._section_buttons = {}
        self._active_section = "words"
        self._dirty = False
        self._close_discard_armed = False
        self._words = list(load_custom_dictionary())
        self._snippet_data = list(snippets.get_all())
        self._correction_data = list(self.corrections.get_all())

    def show(self):
        if self.window and self.window.isVisible():
            self.window.makeKeyAndOrderFront_(None)
            AppKit.NSApp.activateIgnoringOtherApps_(True)
            return
        self._build_window()
        self.window.makeKeyAndOrderFront_(None)
        AppKit.NSApp.activateIgnoringOtherApps_(True)

    def _build_window(self):
        frame = NSMakeRect(0, 0, self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        style = (
            AppKit.NSTitledWindowMask
            | AppKit.NSClosableWindowMask
            | AppKit.NSMiniaturizableWindowMask
            | AppKit.NSResizableWindowMask
        )
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, AppKit.NSBackingStoreBuffered, False
        )
        self.window.setTitle_(t("dict_title"))
        self.window.center()
        self.window.setLevel_(AppKit.NSFloatingWindowLevel)
        self.window.setTabbingMode_(AppKit.NSWindowTabbingModeDisallowed)

        self._delegate = _DictDelegate.alloc().initWithController_(self)
        self.window.setDelegate_(self._delegate)
        root = self.window.contentView()

        self._build_sidebar(root)

        self._counts_field = self._text_label(
            root,
            dict_counts_text(self._words, self._snippet_data, self._correction_data),
            self.CONTENT_X,
            490,
            self.CONTENT_WIDTH,
            22,
            size=12,
            color=AppKit.NSColor.secondaryLabelColor(),
        )

        self._build_words_section(root)
        self._build_snippets_section(root)
        self._build_corrections_section(root)

        sep = AppKit.NSBox.alloc().initWithFrame_(
            NSMakeRect(0, self.BUTTON_BAR_HEIGHT - 1, self.WINDOW_WIDTH, 1)
        )
        sep.setBoxType_(AppKit.NSBoxSeparator)
        sep.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewMaxYMargin)
        root.addSubview_(sep)

        self._status_field = self._text_label(
            root,
            t("dict_status_ready"),
            20,
            18,
            430,
            22,
            size=12,
            color=AppKit.NSColor.secondaryLabelColor(),
        )
        self._status_field.setLineBreakMode_(AppKit.NSLineBreakByTruncatingTail)

        save_btn = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(514, 15, 82, 32))
        save_btn.setTitle_(t("dict_btn_save"))
        save_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        save_btn.setKeyEquivalent_("\r")
        save_btn.setTarget_(self._delegate)
        save_btn.setAction_(b"onSave:")
        save_btn.setAutoresizingMask_(AppKit.NSViewMinXMargin | AppKit.NSViewMaxYMargin)
        root.addSubview_(save_btn)

        close_btn = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(608, 15, 82, 32))
        close_btn.setTitle_(t("dict_btn_close"))
        close_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        close_btn.setKeyEquivalent_("\x1b")
        close_btn.setTarget_(self._delegate)
        close_btn.setAction_(b"onClose:")
        close_btn.setAutoresizingMask_(AppKit.NSViewMinXMargin | AppKit.NSViewMaxYMargin)
        root.addSubview_(close_btn)
        self._show_section("words")

    def _build_sidebar(self, root):
        title = self._text_label(
            root,
            t("dict_sidebar_title"),
            20,
            492,
            self.SIDEBAR_WIDTH - 32,
            20,
            size=12,
            weight=AppKit.NSFontWeightMedium,
            color=AppKit.NSColor.secondaryLabelColor(),
        )
        title.setSelectable_(False)

        self._add_nav_button(root, "words", t("dict_section_words"), b"onShowWords:", 444)
        self._add_nav_button(root, "snippets", t("dict_section_snippets"), b"onShowSnippets:", 394)
        self._add_nav_button(root, "corrections", t("dict_section_corrections"), b"onShowCorrections:", 344)

        sep = AppKit.NSBox.alloc().initWithFrame_(
            NSMakeRect(self.SIDEBAR_WIDTH, self.BUTTON_BAR_HEIGHT, 1, self.WINDOW_HEIGHT - self.BUTTON_BAR_HEIGHT)
        )
        sep.setBoxType_(AppKit.NSBoxSeparator)
        sep.setAutoresizingMask_(AppKit.NSViewHeightSizable | AppKit.NSViewMaxXMargin)
        root.addSubview_(sep)

    def _add_nav_button(self, root, section_id: str, title: str, action, y: int):
        button = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(20, y, 128, 34))
        button.setTitle_(title)
        button.setButtonType_(AppKit.NSButtonTypeToggle)
        button.setBezelStyle_(AppKit.NSBezelStyleRounded)
        button.setTarget_(self._delegate)
        button.setAction_(action)
        root.addSubview_(button)
        self._section_buttons[section_id] = button

    def _build_words_section(self, root):
        view = self._section_view(root, "words")
        self._section_header(view, t("dict_section_words"), t("dict_words_summary"))
        self._word_field = AppKit.NSTextField.alloc().initWithFrame_(
            NSMakeRect(0, 322, 382, 26)
        )
        self._word_field.setPlaceholderString_(t("dict_placeholder_word"))
        view.addSubview_(self._word_field)
        self._add_button(view, t("dict_btn_add"), b"onAddWord:", 394, 319, 96)
        scroll, self._word_list_view = self._list_view(NSMakeRect(0, 72, self.CONTENT_WIDTH, 230))
        view.addSubview_(scroll)
        self._add_button(view, t("dict_btn_remove_selected"), b"onRemoveWord:", 0, 28, 148)
        self._update_word_list()

    def _build_snippets_section(self, root):
        view = self._section_view(root, "snippets")
        self._section_header(view, t("dict_section_snippets"), t("dict_snippets_summary"))
        self._label(view, t("dict_trigger"), 0, 326)
        self._snippet_trigger_field = AppKit.NSTextField.alloc().initWithFrame_(
            NSMakeRect(74, 322, 312, 26)
        )
        self._snippet_trigger_field.setPlaceholderString_(t("dict_placeholder_trigger"))
        view.addSubview_(self._snippet_trigger_field)
        self._label(view, t("dict_text"), 0, 290)
        self._snippet_text_field = AppKit.NSTextField.alloc().initWithFrame_(
            NSMakeRect(74, 286, 416, 26)
        )
        self._snippet_text_field.setPlaceholderString_(t("dict_placeholder_text"))
        view.addSubview_(self._snippet_text_field)
        self._add_button(view, t("dict_btn_add"), b"onAddSnippet:", 394, 319, 96)
        scroll, self._snippet_list_view = self._list_view(NSMakeRect(0, 72, self.CONTENT_WIDTH, 194))
        view.addSubview_(scroll)
        self._add_button(view, t("dict_btn_remove_selected"), b"onRemoveSnippet:", 0, 28, 148)
        self._update_snippet_list()

    def _build_corrections_section(self, root):
        view = self._section_view(root, "corrections")
        self._section_header(view, t("dict_section_corrections"), t("dict_corrections_summary"))
        self._label(view, t("dict_correction_wrong"), 0, 326)
        self._correction_wrong_field = AppKit.NSTextField.alloc().initWithFrame_(
            NSMakeRect(74, 322, 312, 26)
        )
        self._correction_wrong_field.setPlaceholderString_(t("dict_correction_placeholder_wrong"))
        view.addSubview_(self._correction_wrong_field)
        self._label(view, t("dict_correction_right"), 0, 290)
        self._correction_right_field = AppKit.NSTextField.alloc().initWithFrame_(
            NSMakeRect(74, 286, 416, 26)
        )
        self._correction_right_field.setPlaceholderString_(t("dict_correction_placeholder_right"))
        view.addSubview_(self._correction_right_field)
        self._add_button(view, t("dict_btn_add"), b"onAddCorrection:", 394, 319, 96)
        scroll, self._correction_list_view = self._list_view(NSMakeRect(0, 72, self.CONTENT_WIDTH, 194))
        view.addSubview_(scroll)
        self._add_button(view, t("dict_btn_remove_selected"), b"onRemoveCorrection:", 0, 28, 148)
        self._update_correction_list()

    def _section_view(self, root, section_id: str):
        view = AppKit.NSView.alloc().initWithFrame_(
            NSMakeRect(self.CONTENT_X, 70, self.CONTENT_WIDTH, 412)
        )
        view.setHidden_(True)
        root.addSubview_(view)
        self._section_views[section_id] = view
        return view

    def _section_header(self, view, title: str, subtitle: str):
        self._text_label(
            view,
            title,
            0,
            392,
            self.CONTENT_WIDTH,
            24,
            size=18,
            weight=AppKit.NSFontWeightSemibold,
        )
        self._text_label(
            view,
            subtitle,
            0,
            366,
            self.CONTENT_WIDTH,
            18,
            size=12,
            color=AppKit.NSColor.secondaryLabelColor(),
        )

    def _list_view(self, frame):
        scroll = AppKit.NSScrollView.alloc().initWithFrame_(frame)
        scroll.setHasVerticalScroller_(True)
        scroll.setHasHorizontalScroller_(False)
        scroll.setBorderType_(AppKit.NSBezelBorder)
        scroll.setAutohidesScrollers_(True)

        text_view = AppKit.NSTextView.alloc().initWithFrame_(
            NSMakeRect(0, 0, frame.size.width - 12, frame.size.height)
        )
        text_view.setEditable_(False)
        text_view.setSelectable_(True)
        text_view.setHorizontallyResizable_(False)
        text_view.setVerticallyResizable_(True)
        text_view.setFont_(
            AppKit.NSFont.monospacedSystemFontOfSize_weight_(
                12,
                AppKit.NSFontWeightRegular,
            )
        )
        container = text_view.textContainer()
        if container is not None:
            container.setContainerSize_(NSMakeSize(frame.size.width - 12, 1000000))
            container.setWidthTracksTextView_(True)
        text_view.setAutoresizingMask_(AppKit.NSViewWidthSizable)
        scroll.setDocumentView_(text_view)
        return scroll, text_view

    def _add_button(self, view, title: str, action, x: int, y: int, width: int):
        button = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(x, y, width, 30))
        button.setTitle_(title)
        button.setBezelStyle_(AppKit.NSBezelStyleRounded)
        button.setTarget_(self._delegate)
        button.setAction_(action)
        view.addSubview_(button)
        return button

    def _show_section(self, section_id: str):
        if section_id not in self._section_views:
            return
        previous = self._active_section
        self._active_section = section_id
        for name, view in self._section_views.items():
            view.setHidden_(name != section_id)
        for name, button in self._section_buttons.items():
            button.setState_(AppKit.NSControlStateValueOn if name == section_id else AppKit.NSControlStateValueOff)
        if previous != section_id and self._status_field is not None:
            if self._dirty:
                self._set_status(t("dict_status_unsaved"), dirty=True)
            else:
                self._set_status(t("dict_status_ready"), dirty=False)

    def _text_label(
        self,
        view,
        text,
        x,
        y,
        width,
        height,
        *,
        size=12,
        weight=None,
        color=None,
    ):
        label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, width, height))
        label.setStringValue_(text)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(True)
        if weight is None:
            label.setFont_(AppKit.NSFont.systemFontOfSize_(size))
        else:
            label.setFont_(AppKit.NSFont.systemFontOfSize_weight_(size, weight))
        if color is not None:
            label.setTextColor_(color)
        view.addSubview_(label)
        return label

    def _label(self, view, text, x, y):
        label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, 65, 18))
        label.setStringValue_(text)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setFont_(AppKit.NSFont.systemFontOfSize_(12))
        view.addSubview_(label)
        return label

    def _update_word_list(self):
        if self._word_list_view:
            self._word_list_view.setString_(format_word_rows(self._words))
        self._update_counts()

    def _update_snippet_list(self):
        if self._snippet_list_view:
            self._snippet_list_view.setString_(format_snippet_rows(self._snippet_data))
        self._update_counts()

    def _update_correction_list(self):
        if self._correction_list_view:
            self._correction_list_view.setString_(format_correction_rows(self._correction_data))
        self._update_counts()

    def _update_counts(self):
        if self._counts_field is not None:
            self._counts_field.setStringValue_(
                dict_counts_text(self._words, self._snippet_data, self._correction_data)
            )

    def _set_status(
        self,
        text: str,
        *,
        dirty: bool | None = None,
        error: bool = False,
        preserve_close_arm: bool = False,
    ):
        if not preserve_close_arm:
            self._close_discard_armed = False
        if dirty is not None:
            self._dirty = dirty
        if self._status_field is not None:
            self._status_field.setStringValue_(text)
            if error:
                self._status_field.setTextColor_(AppKit.NSColor.systemRedColor())
            elif self._dirty:
                self._status_field.setTextColor_(AppKit.NSColor.systemOrangeColor())
            else:
                self._status_field.setTextColor_(AppKit.NSColor.secondaryLabelColor())

    def _request_close(self) -> bool:
        if not self._dirty:
            return True
        if self._close_discard_armed:
            return True
        self._close_discard_armed = True
        self._set_status(
            t("dict_status_close_unsaved"),
            dirty=True,
            error=True,
            preserve_close_arm=True,
        )
        return False

    def _add_word(self):
        word = self._word_field.stringValue().strip()
        if not word:
            self._set_status(t("dict_status_empty_word"), error=True)
            return
        if word in self._words:
            self._set_status(t("dict_status_duplicate_word", word=word), error=True)
            return
        self._words.append(word)
        self._update_word_list()
        self._word_field.setStringValue_("")
        self._set_status(t("dict_status_added_word", word=word), dirty=True)

    def _remove_word(self):
        word = self._word_field.stringValue().strip()
        if word in self._words:
            self._words.remove(word)
            self._update_word_list()
            self._word_field.setStringValue_("")
            self._set_status(t("dict_status_removed"), dirty=True)
            return
        idx = self._selected_index(self._word_list_view, len(self._words))
        if idx is not None:
            del self._words[idx]
            self._update_word_list()
            self._set_status(t("dict_status_removed"), dirty=True)
            return
        self._set_status(t("dict_status_no_selection"), error=True)

    def _add_snippet(self):
        trigger = self._snippet_trigger_field.stringValue().strip()
        text = self._snippet_text_field.stringValue().strip()
        if not trigger or not text:
            self._set_status(t("dict_status_empty_snippet"), error=True)
            return
        self._snippet_data.append({
            "trigger": trigger,
            "text": text,
            "description": "",
        })
        self._update_snippet_list()
        self._snippet_trigger_field.setStringValue_("")
        self._snippet_text_field.setStringValue_("")
        self._set_status(t("dict_status_added_snippet", trigger=trigger), dirty=True)

    def _remove_snippet(self):
        idx = self._selected_index(self._snippet_list_view, len(self._snippet_data))
        if idx is not None:
            del self._snippet_data[idx]
            self._update_snippet_list()
            self._set_status(t("dict_status_removed"), dirty=True)
            return
        self._set_status(t("dict_status_no_selection"), error=True)

    def _add_correction(self):
        wrong = self._correction_wrong_field.stringValue().strip()
        right = self._correction_right_field.stringValue().strip()
        if not wrong:
            self._set_status(t("dict_status_empty_correction"), error=True)
            return
        # Update existing entry if the same wrong already exists
        for entry in self._correction_data:
            if entry.get("wrong", "").lower() == wrong.lower():
                entry["right"] = right
                break
        else:
            self._correction_data.append({"wrong": wrong, "right": right})
        self._update_correction_list()
        self._correction_wrong_field.setStringValue_("")
        self._correction_right_field.setStringValue_("")
        self._set_status(t("dict_status_added_correction", wrong=wrong), dirty=True)

    def _remove_correction(self):
        idx = self._selected_index(self._correction_list_view, len(self._correction_data))
        if idx is not None:
            del self._correction_data[idx]
            self._update_correction_list()
            self._set_status(t("dict_status_removed"), dirty=True)
            return
        self._set_status(t("dict_status_no_selection"), error=True)

    def _selected_index(self, text_view, item_count: int) -> int | None:
        if text_view is None:
            return None
        try:
            selection = text_view.selectedRange()
            location = selection[0] if isinstance(selection, tuple) else selection.location
            return selected_line_index(text_view.string(), location, item_count)
        except Exception:
            return None

    def _do_save(self):
        save_custom_dictionary(self._words)
        # Update snippets library
        self.snippets._snippets = list(self._snippet_data)
        self.snippets._save()
        # Update correction store
        self.corrections.replace_all(self._correction_data)
        self._set_status(
            t(
                "dict_status_saved",
                words=len(self._words),
                snippets=len(self._snippet_data),
                corrections=len(self._correction_data),
            ),
            dirty=False,
        )
        self.window.close()
        logger.info(
            f"Saved {len(self._words)} dictionary words, "
            f"{len(self._snippet_data)} snippets, "
            f"{len(self._correction_data)} corrections"
        )
