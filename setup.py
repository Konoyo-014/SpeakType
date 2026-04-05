"""py2app setup for building SpeakType.app bundle."""

import atexit
from pathlib import Path
from setuptools import setup


def _patch_site_py():
    """Fix py2app site.py: move PREFIXES before sitecustomize import.

    Homebrew Python's sitecustomize.py accesses site.PREFIXES during import.
    py2app's generated site.py defines PREFIXES at the end, causing a circular
    import crash. This moves it before the sitecustomize import.
    """
    site_py = Path("dist/SpeakType.app/Contents/Resources/site.py")
    if not site_py.exists():
        return
    text = site_py.read_text()
    needle = "PREFIXES = [sys.prefix, sys.exec_prefix]"
    if text.count(needle) != 1:
        return
    # Remove the line from its original position
    text = text.replace("# Prefixes for site-packages; add additional prefixes like /usr/local here\n" + needle, "")
    # Insert before sitecustomize import
    text = text.replace(
        "#\n# Run custom site specific code, if available.\n#",
        "# Prefixes for site-packages (must be set before sitecustomize import)\n"
        + needle + "\n\n"
        "#\n# Run custom site specific code, if available.\n#",
    )
    site_py.write_text(text)
    print("*** patched site.py: moved PREFIXES before sitecustomize import ***")


atexit.register(_patch_site_py)

APP = ["main.py"]
DATA_FILES = []

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "resources/SpeakType.icns",
    "plist": {
        "CFBundleName": "SpeakType",
        "CFBundleDisplayName": "SpeakType",
        "CFBundleIdentifier": "com.speaktype.app",
        "CFBundleVersion": "2.0.0",
        "CFBundleShortVersionString": "2.0",
        "LSUIElement": False,  # Must be False for NSStatusItem to show in menubar
        "NSMicrophoneUsageDescription": "SpeakType needs microphone access for voice dictation.",
        "NSAppleEventsUsageDescription": "SpeakType needs accessibility access to detect the active application and insert text.",
        "CFBundleDocumentTypes": [],
        "LSMinimumSystemVersion": "13.0",
        "NSHighResolutionCapable": True,
    },
    "packages": ["speaktype", "rumps", "sounddevice", "soundfile", "numpy", "requests", "pynput"],
    "includes": ["AppKit", "Quartz", "objc"],
    "excludes": ["tkinter", "matplotlib", "scipy", "PIL", "cv2"],
}

setup(
    name="SpeakType",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
