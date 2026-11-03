import argparse
from pathlib import Path
import plistlib
import zipfile

from macholib.MachO import MachO, lc_str_value
from macholib.mach_o import CPU_TYPE_NAMES, LC_BUILD_VERSION, LC_RPATH, LC_VERSION_MIN_MACOSX
from macholib.util import iter_platform_files
from packaging.version import Version


parser = argparse.ArgumentParser()
parser.add_argument("app", type=Path)
parser.add_argument("--version", required=True)
parser.add_argument("--build-version", required=True)
parser.add_argument("--source", type=Path)
args = parser.parse_args()
bundle = args.app.resolve(strict=True)
with (bundle / "Contents" / "Info.plist").open("rb") as stream:
    info = plistlib.load(stream)

expected = {
    "CFBundleIdentifier": "com.speaktype.app",
    "CFBundleShortVersionString": args.version,
    "CFBundleVersion": args.build_version,
    "LSMinimumSystemVersion": "14.0",
    "PyErrorScripts": ["verify_error.sh"],
}
for key, value in expected.items():
    if info.get(key) != value:
        raise RuntimeError(f"Incorrect {key}: expected {value}, found {info.get(key)}")

minimum_system = Version(info["LSMinimumSystemVersion"])
binary_count = 0
for binary_path in iter_platform_files(str(bundle)):
    binary = MachO(binary_path)
    arm_headers = [header for header in binary.headers if CPU_TYPE_NAMES[header.header.cputype] == "ARM64"]
    if not arm_headers:
        raise RuntimeError(f"Apple Silicon binary is missing: {binary_path}")
    for header in arm_headers:
        for command_info in header.commands:
            command, data, _ = command_info
            if command.cmd == LC_RPATH:
                search_path = lc_str_value(data.path, command_info).decode("utf-8")
                if search_path.startswith("/") and not search_path.startswith(("/System/Library/", "/usr/lib/")):
                    raise RuntimeError(f"Binary searches a build-machine library directory: {binary_path}: {search_path}")
            if command.cmd == LC_BUILD_VERSION:
                if data.platform != 1:
                    raise RuntimeError(f"Binary targets a non-macOS platform: {binary_path}")
                version = int(data.minos)
            elif command.cmd == LC_VERSION_MIN_MACOSX:
                version = int(data.version)
            else:
                continue
            required_system = Version(f"{version >> 16}.{(version >> 8) & 255}.{version & 255}")
            if required_system > minimum_system:
                raise RuntimeError(f"Binary requires macOS {required_system}, above {minimum_system}: {binary_path}")
        for _, _, dependency in header.walkRelocatables():
            if dependency.startswith("/") and not dependency.startswith(("/System/Library/", "/usr/lib/")):
                raise RuntimeError(f"Binary links to a build-machine library: {binary_path}: {dependency}")
    binary_count += 1

if binary_count == 0:
    raise RuntimeError("No Mach-O binaries were found in the application")
resources = bundle / "Contents" / "Resources"
if args.source is not None:
    package_directories = [path for path in (resources / "lib").glob("python*/speaktype") if path.is_dir()]
    if len(package_directories) != 1:
        raise RuntimeError(f"Expected one bundled SpeakType package: {package_directories}")
    source_package = args.source.resolve(strict=True)
    bundled_package = package_directories[0]
    source_files = {path.relative_to(source_package) for path in source_package.rglob("*.py")}
    bundled_files = {path.relative_to(bundled_package) for path in bundled_package.rglob("*.py")}
    if source_files != bundled_files:
        raise RuntimeError("Bundled SpeakType Python files differ from the source checkout")
    for relative_path in source_files:
        if (source_package / relative_path).read_bytes() != (bundled_package / relative_path).read_bytes():
            raise RuntimeError(f"Bundled SpeakType source differs from the checkout: {relative_path}")
    for source_script, bundled_script in (
        (source_package.parent / "main.py", resources / "main.py"),
        (source_package.parent / "scripts" / "verify_runtime.py", resources / "verify_runtime.py"),
        (source_package / "model_download_worker.py", resources / "model_download_worker.py"),
        (source_package / "audio_capture_worker.py", resources / "audio_capture_worker.py"),
        (source_package.parent / "resources" / "verify_error.sh", resources / "verify_error.sh"),
    ):
        if source_script.read_bytes() != bundled_script.read_bytes():
            raise RuntimeError(f"Bundled entry script differs from the checkout: {source_script.name}")
archives = sorted((resources / "lib").glob("python*.zip"))
if not archives:
    raise RuntimeError("The bundled Python standard-library archive is missing")
for archive_path in archives:
    with zipfile.ZipFile(archive_path) as archive:
        invalid_member = archive.testzip()
        if invalid_member is not None:
            raise RuntimeError(f"The bundled Python archive is damaged: {archive_path}: {invalid_member}")

print(f"Verified {binary_count} Mach-O binaries, macOS {minimum_system} compatibility, bundle metadata, and Python archives.")
