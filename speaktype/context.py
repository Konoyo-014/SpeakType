"""Detect the active application for context-aware tone adjustment."""

import subprocess
import logging

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
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=2
        )
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


def get_selected_text() -> str:
    """Get currently selected text in the active application via Cmd+C."""
    import time
    try:
        # Save current clipboard
        script_get = 'the clipboard as text'
        result = subprocess.run(
            ["osascript", "-e", script_get],
            capture_output=True, text=True, timeout=2
        )
        old_clipboard = result.stdout.strip() if result.returncode == 0 else ""

        # Simulate Cmd+C
        script_copy = '''
        tell application "System Events"
            keystroke "c" using command down
        end tell
        '''
        subprocess.run(["osascript", "-e", script_copy], timeout=2)
        time.sleep(0.15)

        # Get new clipboard
        result = subprocess.run(
            ["osascript", "-e", script_get],
            capture_output=True, text=True, timeout=2
        )
        new_clipboard = result.stdout.strip() if result.returncode == 0 else ""

        if new_clipboard and new_clipboard != old_clipboard:
            return new_clipboard

    except Exception as e:
        logger.debug(f"Failed to get selected text: {e}")

    return ""
