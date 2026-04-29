"""py2app setup for building SpeakType.app bundle."""

import atexit
import importlib.util
import os
from pathlib import Path
import py_compile
import re
import shutil
from setuptools import setup


def _read_base_version() -> str:
    namespace = {}
    exec(Path("speaktype/__init__.py").read_text(encoding="utf-8"), namespace)
    return namespace["__version__"]


BASE_VERSION = _read_base_version()
BUILD_VERSION = os.environ.get("SPEAKTYPE_BUILD_VERSION", BASE_VERSION)

if not re.fullmatch(r"\d+\.\d+\.\d+(?:(?:d|a|b|fc)\d+)?", BUILD_VERSION):
    raise SystemExit(
        "Invalid SPEAKTYPE_BUILD_VERSION. Use a macOS-friendly build string such as "
        "'2.0.1', '2.0.1d1', or '2.0.1b3'."
    )


def _patch_site_py():
    """Fix py2app site.py: move PREFIXES before sitecustomize import.

    Homebrew Python's sitecustomize.py accesses site.PREFIXES during import.
    py2app's generated site.py defines PREFIXES at the end, causing a circular
    import crash. This moves it before the sitecustomize import.
    """
    resources_dir = Path("dist/SpeakType.app/Contents/Resources")
    site_py = resources_dir / "site.py"
    site_pyc = resources_dir / "site.pyc"
    if not resources_dir.exists():
        return

    if site_py.exists():
        text = site_py.read_text(encoding="utf-8")
    else:
        import py2app

        template_py = Path(py2app.__file__).resolve().parent / "apptemplate" / "lib" / "site.py"
        if not template_py.exists():
            return
        text = template_py.read_text(encoding="utf-8")

    needle = "PREFIXES = [sys.prefix, sys.exec_prefix]"
    if needle not in text:
        return

    text = text.replace("# Prefixes for site-packages; add additional prefixes like /usr/local here\n" + needle, "")
    text = text.replace(needle, "")
    text = text.replace(
        "#\n# Run custom site specific code, if available.\n#",
        "# Prefixes for site-packages (must be set before sitecustomize import)\n"
        + needle + "\n\n"
        "#\n# Run custom site specific code, if available.\n#",
    )
    site_py.write_text(text, encoding="utf-8")
    if site_pyc.exists():
        py_compile.compile(str(site_py), cfile=str(site_pyc), doraise=True)
    print("*** patched site.py/site.pyc: moved PREFIXES before sitecustomize import ***")


def _copy_runtime_support():
    """Copy binary-backed packages out of the zip archive for bundled imports."""
    dest_root = Path("dist/SpeakType.app/Contents/Resources/lib/python3.10")
    if not dest_root.exists():
        return

    lib_dynload_root = dest_root / "lib-dynload"
    site_packages_root = None
    skip_dynload_packages = {
        "AppKit",
        "CoreFoundation",
        "CoreText",
        "Foundation",
        "HIServices",
        "Quartz",
        "objc",
    }
    dynload_packages = []
    if lib_dynload_root.exists():
        dynload_packages = sorted(
            path.name
            for path in lib_dynload_root.iterdir()
            if path.is_dir() and path.name not in skip_dynload_packages
        )

    for module_name in (
        "sounddevice",
        "_sounddevice_data",
        "soundfile",
        "_soundfile_data",
        *dynload_packages,
    ):
        spec = importlib.util.find_spec(module_name)
        if spec is None:
            continue

        if spec.submodule_search_locations:
            src = Path(next(iter(spec.submodule_search_locations))).resolve()
            if site_packages_root is None:
                site_packages_root = src.parent
            dest = dest_root / src.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)

            if module_name == "mlx" and not (dest / "__init__.py").exists():
                (dest / "__init__.py").write_text(
                    "# Force bundled MLX imports to resolve from lib/python3.10.\n",
                    encoding="utf-8",
                )

            shim_dir = lib_dynload_root / module_name
            if shim_dir.exists():
                for shim in shim_dir.iterdir():
                    if shim.is_file():
                        shutil.copy2(shim, dest / shim.name)
        elif spec.origin:
            src = Path(spec.origin).resolve()
            if site_packages_root is None:
                site_packages_root = src.parent
            shutil.copy2(src, dest_root / src.name)

    if site_packages_root is not None:
        for helper in site_packages_root.glob("*__mypyc*.so"):
            shutil.copy2(helper, dest_root / helper.name)
        for ext in site_packages_root.iterdir():
            if ext.is_file() and ext.suffix in {".so", ".dylib"}:
                shutil.copy2(ext, dest_root / ext.name)

    print("*** copied binary-backed runtime packages into lib/python3.10 ***")


atexit.register(_patch_site_py)
atexit.register(_copy_runtime_support)

APP = ["main.py"]
DATA_FILES = []

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "resources/SpeakType.icns",
    "plist": {
        "CFBundleName": "SpeakType",
        "CFBundleDisplayName": "SpeakType",
        "CFBundleIdentifier": "com.speaktype.app",
        "CFBundleVersion": BUILD_VERSION,
        "CFBundleShortVersionString": BASE_VERSION,
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
    version=BASE_VERSION,
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
