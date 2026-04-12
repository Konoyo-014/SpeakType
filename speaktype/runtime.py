"""Runtime helpers for distinguishing source and bundled execution."""

import hashlib
from pathlib import Path

BUNDLE_IDENTIFIER = "com.speaktype.app"
APP_BUNDLE_NAME = "SpeakType.app"


def get_running_bundle_path() -> str:
    """Return the active SpeakType app bundle path when running inside one."""
    try:
        import AppKit

        bundle = AppKit.NSBundle.mainBundle()
        if not bundle:
            return ""
        bundle_path = str(bundle.bundlePath() or "")
        bundle_id = str(bundle.bundleIdentifier() or "")
        if bundle_path.endswith(".app") and (
            bundle_id == BUNDLE_IDENTIFIER or Path(bundle_path).name == APP_BUNDLE_NAME
        ):
            return str(Path(bundle_path).expanduser().resolve())
    except Exception:
        return ""
    return ""


def get_runtime_version(default_version: str) -> str:
    """Return the bundled build version when available, else the package version."""
    bundle_path = get_running_bundle_path()
    if not bundle_path:
        return default_version

    try:
        import AppKit

        bundle = AppKit.NSBundle.mainBundle()
        if not bundle:
            return default_version
        info = bundle.infoDictionary() or {}
        build_version = str(info.get("CFBundleVersion") or "").strip()
        return build_version or default_version
    except Exception:
        return default_version


def get_bundle_fingerprint(bundle_path: str | None = None) -> str:
    """Return a stable fingerprint for the currently installed app bundle."""
    active_bundle = bundle_path if bundle_path is not None else get_running_bundle_path()
    if not active_bundle:
        return ""

    bundle = Path(active_bundle).expanduser().resolve()
    candidates = [
        bundle / "Contents" / "Info.plist",
        bundle / "Contents" / "MacOS" / "SpeakType",
        bundle / "Contents" / "_CodeSignature" / "CodeResources",
    ]
    digest = hashlib.sha256()
    found = False
    for path in candidates:
        if not path.exists() or not path.is_file():
            continue
        found = True
        stat = path.stat()
        digest.update(str(path.relative_to(bundle)).encode("utf-8"))
        digest.update(str(stat.st_size).encode("ascii"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest() if found else ""


def get_launch_program_args(module_file: str, bundle_path: str | None = None) -> tuple[list[str], str]:
    """Resolve the correct LaunchAgent command for source or bundled runs."""
    active_bundle = bundle_path if bundle_path is not None else get_running_bundle_path()
    if active_bundle:
        bundle = Path(active_bundle).expanduser().resolve()
        return ["open", str(bundle)], str(bundle.parent)

    project_dir = Path(module_file).resolve().parent.parent
    return [
        str(project_dir / "venv" / "bin" / "python3"),
        str(project_dir / "main.py"),
    ], str(project_dir)
