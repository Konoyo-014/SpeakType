"""Compatibility helpers for py2app + sounddevice bundles."""

from pathlib import Path
import pkgutil
import tempfile


def _write_bytes_if_needed(path: Path, data: bytes):
    if path.exists() and path.read_bytes() == data:
        return
    path.write_bytes(data)


def ensure_sounddevice_data_dir(package_module, data_getter=None, extract_root: str | None = None) -> str:
    """Ensure PortAudio lives on disk even when _sounddevice_data is zipped."""
    package_path = next(iter(getattr(package_module, "__path__", [])), "")
    if package_path and Path(package_path).is_dir():
        return str(Path(package_path))

    data_getter = data_getter or pkgutil.get_data
    lib_bytes = data_getter("_sounddevice_data", "portaudio-binaries/libportaudio.dylib")
    if not lib_bytes:
        return package_path

    root = Path(extract_root or (Path(tempfile.gettempdir()) / "speaktype_sounddevice_data"))
    binary_dir = root / "portaudio-binaries"
    binary_dir.mkdir(parents=True, exist_ok=True)
    (root / "__init__.py").write_text("# extracted by SpeakType for bundled sounddevice\n", encoding="utf-8")
    _write_bytes_if_needed(binary_dir / "libportaudio.dylib", lib_bytes)

    readme_bytes = data_getter("_sounddevice_data", "portaudio-binaries/README.md")
    if readme_bytes:
        _write_bytes_if_needed(binary_dir / "README.md", readme_bytes)

    package_module.__path__ = [str(root)]
    return str(root)


def prepare_sounddevice_import():
    """Preload _sounddevice_data onto a real filesystem path when bundled."""
    try:
        import _sounddevice_data
    except Exception:
        return ""
    return ensure_sounddevice_data_dir(_sounddevice_data)
