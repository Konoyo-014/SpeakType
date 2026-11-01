import argparse
import json
import os
from pathlib import Path
import sys

import AppKit
from ApplicationServices import AXValueCreate, kAXSelectedTextAttribute, kAXSelectedTextRangeAttribute, kAXValueCFRangeType
from CoreFoundation import CFEqual, CFRangeMake, CFStringGetLength
from Foundation import NSDate, NSMakeRect, NSRunLoop

repository = Path(__file__).resolve().parents[1]
prefix = Path(sys.prefix).resolve()
bundle = next((path for path in (prefix, *prefix.parents) if path.suffix == ".app"), None)
bundled = bundle is not None or bool(getattr(sys, "frozen", False) or os.environ.get("SPEAKTYPE_VERIFY_BUNDLE"))
if bundled:
    assert bundle is not None and prefix.is_relative_to(bundle), sys.prefix
else:
    sys.path.insert(0, str(repository))

from speaktype import inserter
from speaktype.context import get_active_app
from speaktype.inserter import (
    _copy_ax_attribute,
    _get_focused_element,
    _prepare_target_app,
    _selected_utf16_range,
    _set_ax_attribute,
    capture_verified_insertion,
    get_last_insert_diagnostic,
    insert_text,
    reset_last_insert_diagnostic,
    undo_verified_insertion,
)

if bundled:
    assert Path(inserter.__file__).resolve().is_relative_to(bundle), inserter.__file__


def focus_textedit():
    _prepare_target_app(bundle_id="com.apple.TextEdit", app_name="TextEdit")
    assert get_active_app()["bundle_id"] == "com.apple.TextEdit"
    element = _get_focused_element()
    assert element is not None
    assert isinstance(_copy_ax_attribute(element, "AXValue"), str)
    return element


def set_range(element, location, length=0):
    value = AXValueCreate(kAXValueCFRangeType, CFRangeMake(location, length))
    assert _set_ax_attribute(element, kAXSelectedTextRangeAttribute, value) == 0
    assert _selected_utf16_range(element) == (location, length)


def replace_document(value, caret):
    element = focus_textedit()
    previous = _copy_ax_attribute(element, "AXValue")
    set_range(element, 0, CFStringGetLength(previous))
    assert _set_ax_attribute(element, kAXSelectedTextAttribute, value) == 0
    assert _copy_ax_attribute(element, "AXValue") == value
    set_range(element, caret)
    return element


def insert_case(prefix, text, suffix):
    element = replace_document(prefix + suffix, CFStringGetLength(prefix))
    assert insert_text(text, app_name="TextEdit", bundle_id="com.apple.TextEdit")
    diagnostic = get_last_insert_diagnostic()
    assert diagnostic.success and diagnostic.verified, diagnostic
    snapshot = capture_verified_insertion(text)
    assert snapshot is not None
    assert CFEqual(element, snapshot.element)
    assert snapshot.value == prefix + text + suffix
    assert snapshot.selected_range == (CFStringGetLength(prefix + text), 0)
    return snapshot


parser = argparse.ArgumentParser(description="Verify safe undo against real dedicated TextEdit documents.")
parser.add_argument("--textedit", action="store_true", help="Use dedicated TextEdit documents created and switched through CUA.")
parser.add_argument("--report", type=Path, default=repository / "work" / "undo-validation-report.json")
args = parser.parse_args()
if not args.textedit:
    parser.error("Pass --textedit to authorize the dedicated native document test.")

work = repository / "work"
work.mkdir(exist_ok=True)
native_window = None
checks = []
pasteboard = AppKit.NSPasteboard.generalPasteboard()
clipboard = {kind: pasteboard.dataForType_(kind) for kind in pasteboard.types() or []}

try:
    print("READY_FIRST_DOCUMENT: create and focus a dedicated TextEdit document with CUA, then send first", flush=True)
    assert input().strip() == "first"

    for prefix, text, suffix in (("Prefix: ", "dictation", " suffix"),
                                 ("前缀🧪 ", "听写🧪 café", " 后文🧪")):
        snapshot = insert_case(prefix, text, suffix)
        assert undo_verified_insertion(snapshot)
        assert _copy_ax_attribute(snapshot.element, "AXValue") == prefix + suffix
        assert _selected_utf16_range(snapshot.element) == (CFStringGetLength(prefix), 0)
        assert not undo_verified_insertion(snapshot)
        assert _copy_ax_attribute(snapshot.element, "AXValue") == prefix + suffix
        checks.append("precise_unicode_undo" if "🧪" in text else "precise_ascii_undo")

    snapshot = insert_case("Prefix: ", "dictation🧪", " suffix")
    set_range(snapshot.element, 0)
    assert not undo_verified_insertion(snapshot)
    assert _copy_ax_attribute(snapshot.element, "AXValue") == snapshot.value
    assert _selected_utf16_range(snapshot.element) == (0, 0)
    checks.append("moved_cursor_preserves_text")

    snapshot = insert_case("Prefix: ", "dictation🧪", " suffix")
    set_range(snapshot.element, 0, 3)
    assert not undo_verified_insertion(snapshot)
    assert _copy_ax_attribute(snapshot.element, "AXValue") == snapshot.value
    assert _selected_utf16_range(snapshot.element) == (0, 3)
    checks.append("changed_selection_preserves_text")

    snapshot = insert_case("Prefix: ", "dictation🧪", " suffix")
    changed = "X" + snapshot.value[1:]
    replace_document(changed, snapshot.selected_range[0])
    assert not undo_verified_insertion(snapshot)
    assert _copy_ax_attribute(snapshot.element, "AXValue") == changed
    checks.append("edited_value_preserves_text")

    snapshot = insert_case("Prefix: ", "dictation🧪", " suffix")
    print("PASS FIRST_DOCUMENT: precise ASCII/Unicode undo and cursor/selection/value protection", flush=True)
    print("READY_OTHER_DOCUMENT: create and focus another TextEdit document with CUA, then send continue", flush=True)
    assert input().strip() == "continue"
    other_element = replace_document(snapshot.value, snapshot.selected_range[0])
    assert not CFEqual(other_element, snapshot.element)
    assert not undo_verified_insertion(snapshot)
    assert _copy_ax_attribute(other_element, "AXValue") == snapshot.value
    assert _copy_ax_attribute(snapshot.element, "AXValue") == snapshot.value
    checks.append("other_document_same_value_and_range_preserves_text")

    application = AppKit.NSApplication.sharedApplication()
    application.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
    native_window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, 260, 100), AppKit.NSTitledWindowMask, AppKit.NSBackingStoreBuffered, False)
    native_window.setReleasedWhenClosed_(False)
    native_window.setTitle_("SpeakType Undo Validation")
    native_window.makeKeyAndOrderFront_(None)
    application.activateIgnoringOtherApps_(True)
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.15))
    focused = _get_focused_element()
    assert focused is None or _selected_utf16_range(focused) is None
    assert capture_verified_insertion("dictation🧪") is None
    assert not undo_verified_insertion(snapshot)
    assert _copy_ax_attribute(snapshot.element, "AXValue") == snapshot.value
    checks.append("target_without_ax_text_range_preserves_original_text")
    native_window.close()
    native_window = None
    focus_textedit()

    reset_last_insert_diagnostic()
    assert capture_verified_insertion("dictation🧪") is None
    assert not undo_verified_insertion(None)
    assert _copy_ax_attribute(other_element, "AXValue") == snapshot.value
    checks.append("unverified_insertion_has_no_undo_snapshot")

    report = {"method": "real TextEdit documents, Accessibility attributes, CoreFoundation UTF16 ranges",
              "sys_prefix": sys.prefix, "inserter_module": inserter.__file__,
              "bundle": str(bundle) if bundled else None,
              "checks_passed": checks, "check_count": len(checks)}
    path = args.report.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"REPORT {path}")
finally:
    if native_window is not None:
        native_window.close()
    pasteboard.clearContents()
    for kind, data in clipboard.items():
        if data is not None:
            pasteboard.setData_forType_(data, kind)
