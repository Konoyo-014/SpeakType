import time

import AppKit

from speaktype import inserter


pb = AppKit.NSPasteboard.generalPasteboard()
original = inserter._snapshot_pasteboard(pb)


def put(text):
    pb.clearContents()
    assert pb.setString_forType_(text, AppKit.NSPasteboardTypeString)


def current():
    return pb.stringForType_(AppKit.NSPasteboardTypeString)


try:
    put("clipboard before dictation")
    saved = inserter._snapshot_restore_data(pb)
    put("first dictation")
    inserter._schedule_pasteboard_restore(saved, "first dictation", pb.changeCount(), delay=0.25)
    put("new content copied by the user 🧪")
    saved_again = inserter._snapshot_restore_data(pb)
    put("second dictation")
    inserter._schedule_pasteboard_restore(saved_again, "second dictation", pb.changeCount(), delay=0.15)
    time.sleep(0.35)
    assert current() == "new content copied by the user 🧪"

    saved = inserter._snapshot_restore_data(pb)
    put("third dictation")
    inserter._schedule_pasteboard_restore(saved, "third dictation", pb.changeCount(), delay=0.15)
    saved = inserter._snapshot_restore_data(pb)
    put("fourth dictation")
    inserter._schedule_pasteboard_restore(saved, "fourth dictation", pb.changeCount(), delay=0.2)
    time.sleep(0.3)
    assert current() == "new content copied by the user 🧪"

    saved = inserter._snapshot_restore_data(pb)
    put("last dictation")
    inserter._schedule_pasteboard_restore(saved, "last dictation", pb.changeCount(), delay=0.1)
    put("copied during restore delay")
    time.sleep(0.2)
    assert current() == "copied during restore delay"
    print("Real NSPasteboard verified: new user copies survive repeated insertions and delayed restoration.")
finally:
    inserter._cancel_pending_pasteboard_restore(original)
    inserter._restore_pasteboard(pb, original)
