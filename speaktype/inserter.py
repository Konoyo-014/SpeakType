"""Insert text at the cursor position in any application."""

import subprocess
import time
import logging

logger = logging.getLogger("speaktype.inserter")


def insert_text(text: str, method: str = "paste"):
    """Insert text at the current cursor position.

    Methods:
        paste: Copy to clipboard then Cmd+V (fast, reliable)
        type: Simulate keystrokes (slower, works everywhere)
    """
    if not text:
        return

    if method == "paste":
        _insert_via_paste(text)
    else:
        _insert_via_keystroke(text)


def _insert_via_paste(text: str):
    """Insert text by copying to clipboard and pasting."""
    try:
        # Save current clipboard
        save_script = 'try\nthe clipboard as text\non error\nreturn ""\nend try'
        result = subprocess.run(
            ["osascript", "-e", save_script],
            capture_output=True, text=True, timeout=2
        )
        old_clipboard = result.stdout.strip() if result.returncode == 0 else ""

        # Set clipboard to our text
        set_script = f'set the clipboard to "{_escape_applescript(text)}"'
        subprocess.run(["osascript", "-e", set_script], timeout=2)

        time.sleep(0.05)

        # Simulate Cmd+V
        paste_script = '''
        tell application "System Events"
            keystroke "v" using command down
        end tell
        '''
        subprocess.run(["osascript", "-e", paste_script], timeout=2)

        # Restore clipboard after a delay
        time.sleep(0.3)
        if old_clipboard:
            restore_script = f'set the clipboard to "{_escape_applescript(old_clipboard)}"'
            subprocess.run(["osascript", "-e", restore_script], timeout=2)

    except Exception as e:
        logger.error(f"Paste insertion failed: {e}")
        # Fallback to keystroke method
        _insert_via_keystroke(text)


def _insert_via_keystroke(text: str):
    """Insert text by simulating keystrokes (slower but universal)."""
    try:
        # Use System Events to type the text
        script = f'''
        tell application "System Events"
            keystroke "{_escape_applescript(text)}"
        end tell
        '''
        subprocess.run(["osascript", "-e", script], timeout=10)
    except Exception as e:
        logger.error(f"Keystroke insertion failed: {e}")


def replace_selection(text: str):
    """Replace the currently selected text with new text."""
    try:
        # Set clipboard
        set_script = f'set the clipboard to "{_escape_applescript(text)}"'
        subprocess.run(["osascript", "-e", set_script], timeout=2)

        time.sleep(0.05)

        # Cmd+V replaces the selection
        paste_script = '''
        tell application "System Events"
            keystroke "v" using command down
        end tell
        '''
        subprocess.run(["osascript", "-e", paste_script], timeout=2)

    except Exception as e:
        logger.error(f"Replace selection failed: {e}")


def _escape_applescript(text: str) -> str:
    """Escape special characters for AppleScript strings."""
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")
