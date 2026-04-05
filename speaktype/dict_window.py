"""Custom dictionary editor — native macOS window for managing custom words and snippets."""

import logging
import AppKit
import objc
from Foundation import NSObject, NSMakeRect
from .config import load_custom_dictionary, save_custom_dictionary
from .snippets import SnippetLibrary, SNIPPETS_FILE

logger = logging.getLogger("speaktype.dict_window")


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

    def onSave_(self, sender):
        self._controller._do_save()

    def onClose_(self, sender):
        self._controller.window.close()


class DictWindowController:
    """Manages the custom dictionary and snippets editor window."""

    def __init__(self, snippets: SnippetLibrary):
        self.snippets = snippets
        self.window = None
        self._delegate = None
        self._word_list_view = None
        self._snippet_list_view = None
        self._word_field = None
        self._snippet_trigger_field = None
        self._snippet_text_field = None
        self._words = list(load_custom_dictionary())
        self._snippet_data = list(snippets.get_all())

    def show(self):
        if self.window and self.window.isVisible():
            self.window.makeKeyAndOrderFront_(None)
            AppKit.NSApp.activateIgnoringOtherApps_(True)
            return
        self._build_window()
        self.window.makeKeyAndOrderFront_(None)
        AppKit.NSApp.activateIgnoringOtherApps_(True)

    def _build_window(self):
        frame = NSMakeRect(0, 0, 560, 600)
        style = (
            AppKit.NSTitledWindowMask
            | AppKit.NSClosableWindowMask
            | AppKit.NSMiniaturizableWindowMask
            | AppKit.NSResizableWindowMask
        )
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, AppKit.NSBackingStoreBuffered, False
        )
        self.window.setTitle_("SpeakType — Dictionary & Snippets")
        self.window.center()
        self.window.setLevel_(AppKit.NSFloatingWindowLevel)
        self.window.setTabbingMode_(AppKit.NSWindowTabbingModeDisallowed)

        self._delegate = _DictDelegate.alloc().initWithController_(self)
        content = self.window.contentView()
        y = 570

        # === Custom Dictionary Section ===
        y = self._section(content, "Custom Dictionary (words to always recognize correctly)", y)

        # Word input field + add button
        self._word_field = AppKit.NSTextField.alloc().initWithFrame_(
            NSMakeRect(30, y - 28, 380, 24)
        )
        self._word_field.setPlaceholderString_("Enter a word or phrase...")
        content.addSubview_(self._word_field)

        add_word_btn = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(420, y - 28, 60, 24))
        add_word_btn.setTitle_("Add")
        add_word_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        add_word_btn.setTarget_(self._delegate)
        add_word_btn.setAction_(b"onAddWord:")
        content.addSubview_(add_word_btn)

        remove_word_btn = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(485, y - 28, 60, 24))
        remove_word_btn.setTitle_("Remove")
        remove_word_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        remove_word_btn.setTarget_(self._delegate)
        remove_word_btn.setAction_(b"onRemoveWord:")
        content.addSubview_(remove_word_btn)
        y -= 36

        # Word list (scrollable text view showing all words)
        scroll_frame = NSMakeRect(30, y - 120, 515, 120)
        scroll_view = AppKit.NSScrollView.alloc().initWithFrame_(scroll_frame)
        scroll_view.setHasVerticalScroller_(True)
        scroll_view.setBorderType_(AppKit.NSBezelBorder)

        self._word_list_view = AppKit.NSTextView.alloc().initWithFrame_(
            NSMakeRect(0, 0, 500, 120)
        )
        self._word_list_view.setEditable_(False)
        self._word_list_view.setFont_(AppKit.NSFont.monospacedSystemFontOfSize_weight_(12, AppKit.NSFontWeightRegular))
        self._update_word_list()
        scroll_view.setDocumentView_(self._word_list_view)
        content.addSubview_(scroll_view)
        y -= 130

        # === Snippets Section ===
        y -= 10
        y = self._section(content, "Snippets (say trigger phrase to insert text)", y)

        # Trigger field
        lbl1 = self._label(content, "Trigger:", 30, y - 24)
        self._snippet_trigger_field = AppKit.NSTextField.alloc().initWithFrame_(
            NSMakeRect(100, y - 26, 200, 24)
        )
        self._snippet_trigger_field.setPlaceholderString_("e.g., my email")
        content.addSubview_(self._snippet_trigger_field)

        # Text field
        lbl2 = self._label(content, "Text:", 310, y - 24)
        self._snippet_text_field = AppKit.NSTextField.alloc().initWithFrame_(
            NSMakeRect(350, y - 26, 135, 24)
        )
        self._snippet_text_field.setPlaceholderString_("e.g., user@mail.com")
        content.addSubview_(self._snippet_text_field)

        add_snip_btn = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(495, y - 26, 50, 24))
        add_snip_btn.setTitle_("+")
        add_snip_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        add_snip_btn.setTarget_(self._delegate)
        add_snip_btn.setAction_(b"onAddSnippet:")
        content.addSubview_(add_snip_btn)
        y -= 36

        # Snippet list
        scroll_frame2 = NSMakeRect(30, y - 160, 515, 160)
        scroll_view2 = AppKit.NSScrollView.alloc().initWithFrame_(scroll_frame2)
        scroll_view2.setHasVerticalScroller_(True)
        scroll_view2.setBorderType_(AppKit.NSBezelBorder)

        self._snippet_list_view = AppKit.NSTextView.alloc().initWithFrame_(
            NSMakeRect(0, 0, 500, 160)
        )
        self._snippet_list_view.setEditable_(False)
        self._snippet_list_view.setFont_(AppKit.NSFont.monospacedSystemFontOfSize_weight_(12, AppKit.NSFontWeightRegular))
        self._update_snippet_list()
        scroll_view2.setDocumentView_(self._snippet_list_view)
        content.addSubview_(scroll_view2)
        y -= 170

        remove_snip_btn = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(30, y - 4, 140, 24))
        remove_snip_btn.setTitle_("Remove Selected")
        remove_snip_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        remove_snip_btn.setTarget_(self._delegate)
        remove_snip_btn.setAction_(b"onRemoveSnippet:")
        content.addSubview_(remove_snip_btn)

        # Save / Close buttons
        y -= 40
        save_btn = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(350, 15, 90, 32))
        save_btn.setTitle_("Save")
        save_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        save_btn.setKeyEquivalent_("\r")
        save_btn.setTarget_(self._delegate)
        save_btn.setAction_(b"onSave:")
        content.addSubview_(save_btn)

        close_btn = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(450, 15, 90, 32))
        close_btn.setTitle_("Close")
        close_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        close_btn.setKeyEquivalent_("\x1b")
        close_btn.setTarget_(self._delegate)
        close_btn.setAction_(b"onClose:")
        content.addSubview_(close_btn)

    def _section(self, view, title, y):
        y -= 8
        label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(20, y - 20, 520, 18))
        label.setStringValue_(title)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setFont_(AppKit.NSFont.boldSystemFontOfSize_(13))
        view.addSubview_(label)

        sep = AppKit.NSBox.alloc().initWithFrame_(NSMakeRect(20, y - 24, 520, 1))
        sep.setBoxType_(AppKit.NSBoxSeparator)
        view.addSubview_(sep)
        return y - 32

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
            text = "\n".join(f"  {w}" for w in self._words) if self._words else "  (no custom words)"
            self._word_list_view.setString_(text)

    def _update_snippet_list(self):
        if self._snippet_list_view:
            lines = []
            for i, s in enumerate(self._snippet_data):
                trigger = s.get("trigger", "")
                text = s.get("text", "")[:50]
                desc = s.get("description", "")
                lines.append(f"  [{i}] \"{trigger}\" -> {text}" + (f"  ({desc})" if desc else ""))
            text = "\n".join(lines) if lines else "  (no snippets)"
            self._snippet_list_view.setString_(text)

    def _add_word(self):
        word = self._word_field.stringValue().strip()
        if word and word not in self._words:
            self._words.append(word)
            self._update_word_list()
            self._word_field.setStringValue_("")

    def _remove_word(self):
        word = self._word_field.stringValue().strip()
        if word in self._words:
            self._words.remove(word)
            self._update_word_list()
            self._word_field.setStringValue_("")

    def _add_snippet(self):
        trigger = self._snippet_trigger_field.stringValue().strip()
        text = self._snippet_text_field.stringValue().strip()
        if trigger and text:
            self._snippet_data.append({
                "trigger": trigger,
                "text": text,
                "description": "",
            })
            self._update_snippet_list()
            self._snippet_trigger_field.setStringValue_("")
            self._snippet_text_field.setStringValue_("")

    def _remove_snippet(self):
        # Remove the last snippet (simple approach for now)
        if self._snippet_data:
            self._snippet_data.pop()
            self._update_snippet_list()

    def _do_save(self):
        save_custom_dictionary(self._words)
        # Update snippets library
        self.snippets._snippets = list(self._snippet_data)
        self.snippets._save()
        self.window.close()
        logger.info(f"Saved {len(self._words)} dictionary words and {len(self._snippet_data)} snippets")
