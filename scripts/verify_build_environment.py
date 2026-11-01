from pathlib import Path
import sys
import zlib

from macholib.MachO import MachO
from macholib.mach_o import CPU_TYPE_NAMES, LC_BUILD_VERSION, LC_VERSION_MIN_MACOSX
from packaging.version import Version
from py2app.build_app import py2app
from setuptools import Distribution


if zlib.__spec__.origin == "built-in":
    raise RuntimeError(
        "py2app 0.28.10 requires a Python distribution with a shared zlib extension. "
        "Select a conda-forge Python 3.10 interpreter with SPEAKTYPE_PYTHON."
    )

_, library_path = py2app(Distribution()).get_runtime()
runtime_library = Path(library_path)
minimum_system = Version("14.0")
for path in (Path(sys.executable).resolve(strict=True), runtime_library.resolve(strict=True)):
    for header in MachO(str(path)).headers:
        if CPU_TYPE_NAMES[header.header.cputype] != "ARM64":
            continue
        for command, data, _ in header.commands:
            if command.cmd == LC_BUILD_VERSION:
                version = int(data.minos)
            elif command.cmd == LC_VERSION_MIN_MACOSX:
                version = int(data.version)
            else:
                continue
            required_system = Version(f"{version >> 16}.{(version >> 8) & 255}.{version & 255}")
            if required_system > minimum_system:
                raise RuntimeError(
                    f"Build Python requires macOS {required_system}: {path}. "
                    "Select an interpreter built for macOS 14 or earlier with SPEAKTYPE_PYTHON."
                )

data = b"SpeakType standalone Python compression check"
if zlib.decompress(zlib.compress(data)) != data:
    raise RuntimeError("The build Python zlib extension failed its compression round trip")
print(f"Build Python: {sys.version}; executable: {sys.executable}; runtime: {runtime_library}")
print("Verified build Python deployment target and shared zlib execution.")
