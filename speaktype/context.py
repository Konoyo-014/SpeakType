"""Detect the active application for context-aware tone adjustment."""

import logging

from .applescript import run_osascript

logger = logging.getLogger("speaktype.context")

# App categories for tone detection
FORMAL_APPS = {
    "com.apple.mail", "com.microsoft.Outlook", "com.google.Gmail",
    "com.microsoft.Word", "com.microsoft.Excel", "com.microsoft.PowerPoint",
    "com.apple.Pages", "com.apple.Keynote", "com.apple.Numbers",
    "com.google.Chrome",  # might be in Gmail/Docs
    "notion.id", "com.notion.Notion",
}

CASUAL_APPS = {
    "com.apple.MobileSMS", "com.tinyspeck.slackmacgap", "com.hnc.Discord",
    "com.facebook.archon", "com.whatsapp.WhatsApp", "ru.keepcoder.Telegram",
    "com.apple.iChat", "jp.naver.line.mac", "com.tencent.xinWeChat",
}

CODE_APPS = {
    "com.microsoft.VSCode", "com.todesktop.230313mzl4w4u92",  # Cursor
    "com.apple.dt.Xcode", "com.jetbrains.intellij",
    "com.googlecode.iterm2", "com.apple.Terminal",
    "com.sublimetext.4", "com.github.atom",
}

NOTE_APPS = {
    "com.apple.Notes", "md.obsidian", "com.evernote.Evernote",
    "net.shinyfrog.bear",
}


def get_active_app() -> dict:
    """Get the active (frontmost) application info."""
    try:
        script = '''
        tell application "System Events"
            set frontApp to first application process whose frontmost is true
            set appName to name of frontApp
            set appID to bundle identifier of frontApp
            return appName & "|" & appID
        end tell
        '''
        result = run_osascript(script, timeout=2)
        if result.returncode == 0 and "|" in result.stdout.strip():
            name, bundle_id = result.stdout.strip().split("|", 1)
            return {"name": name, "bundle_id": bundle_id}
    except Exception as e:
        logger.debug(f"Failed to detect active app: {e}")
    return {"name": "Unknown", "bundle_id": ""}


def get_tone_for_app(app_info: dict) -> str:
    """Determine the appropriate tone based on the active application."""
    bundle_id = app_info.get("bundle_id", "")

    if bundle_id in FORMAL_APPS:
        return "formal"
    elif bundle_id in CASUAL_APPS:
        return "casual"
    elif bundle_id in CODE_APPS:
        return "technical"
    elif bundle_id in NOTE_APPS:
        return "neutral"
    else:
        return "neutral"


def get_scene_for_app(app_info: dict) -> str:
    """Map an active application to a polish scene id.

    Scene ids are looked up in polish.SCENE_PROMPTS to fetch a matching
    instruction fragment for the LLM. Returns ``"default"`` for unknown apps.
    """
    bundle_id = app_info.get("bundle_id", "")
    if not bundle_id:
        return "default"
    if bundle_id in FORMAL_APPS:
        return "email"
    if bundle_id in CASUAL_APPS:
        return "chat"
    if bundle_id in CODE_APPS:
        return "code"
    if bundle_id in NOTE_APPS:
        return "notes"
    return "default"


def get_selected_text() -> str:
    """Get currently selected text via Cmd+C using CGEvent + NSPasteboard.

    Always restores the user's previous clipboard contents, even if any
    intermediate step throws — the previous implementation could lose the
    user's clipboard on errors.
    """
    import time
    import AppKit
    import Quartz

    pb = AppKit.NSPasteboard.generalPasteboard()

    # Snapshot the current clipboard so we can put it back no matter what.
    old_types = pb.types()
    old_data: dict = {}
    if old_types:
        for t in old_types:
            try:
                d = pb.dataForType_(t)
                if d:
                    old_data[t] = d
            except Exception:
                continue

    new_text = ""
    try:
        # Clear clipboard so we can detect new content
        pb.clearContents()
        pb.setString_forType_("", AppKit.NSPasteboardTypeString)

        # Simulate Cmd+C via CGEvent
        src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        cmd_c_down = Quartz.CGEventCreateKeyboardEvent(src, 8, True)
        Quartz.CGEventSetFlags(cmd_c_down, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGAnnotatedSessionEventTap, cmd_c_down)

        cmd_c_up = Quartz.CGEventCreateKeyboardEvent(src, 8, False)
        Quartz.CGEventSetFlags(cmd_c_up, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGAnnotatedSessionEventTap, cmd_c_up)

        time.sleep(0.15)

        new_text = pb.stringForType_(AppKit.NSPasteboardTypeString) or ""
    except Exception as e:
        logger.debug(f"Failed to get selected text: {e}")
    finally:
        # Restore the old clipboard contents.
        if old_data:
            try:
                pb.clearContents()
                for t, d in old_data.items():
                    try:
                        pb.setData_forType_(d, t)
                    except Exception:
                        continue
            except Exception as e:
                logger.debug(f"Clipboard restore failed: {e}")

    if new_text and new_text.strip():
        return new_text.strip()
    return ""
