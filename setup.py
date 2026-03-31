"""py2app setup for building SpeakType.app bundle."""

from setuptools import setup

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
        "LSUIElement": True,  # Hide from Dock, menubar-only app
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
