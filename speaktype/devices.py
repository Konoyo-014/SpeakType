"""Audio input device enumeration and selection."""

import logging
import sounddevice as sd

logger = logging.getLogger("speaktype.devices")


def list_input_devices() -> list[dict]:
    """Return a list of available audio input devices.

    Each entry: {"index": int, "name": str, "channels": int, "sample_rate": float, "is_default": bool}
    """
    devices = []
    try:
        default_input = sd.default.device[0]
        for i, dev in enumerate(sd.query_devices()):
            if dev["max_input_channels"] > 0:
                devices.append({
                    "index": i,
                    "name": dev["name"],
                    "channels": dev["max_input_channels"],
                    "sample_rate": dev["default_samplerate"],
                    "is_default": (i == default_input),
                })
    except Exception as e:
        logger.error(f"Failed to enumerate audio devices: {e}")
    return devices


def get_device_by_name(name: str) -> int | None:
    """Find a device index by name substring match. Returns None if not found."""
    if not name:
        return None
    for dev in list_input_devices():
        if name.lower() in dev["name"].lower():
            return dev["index"]
    return None


def get_default_device_name() -> str:
    """Return the name of the current default input device."""
    try:
        default_idx = sd.default.device[0]
        info = sd.query_devices(default_idx)
        return info["name"]
    except Exception:
        return "System Default"


def validate_device(device) -> int | None:
    """Validate and resolve a device config value to a device index.

    Accepts: None (default), int (index), or str (name).
    Returns device index or None for system default.
    """
    if device is None:
        return None
    if isinstance(device, int):
        try:
            info = sd.query_devices(device)
            if info["max_input_channels"] > 0:
                return device
        except Exception:
            pass
        return None
    if isinstance(device, str):
        return get_device_by_name(device)
    return None
