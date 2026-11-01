import importlib.util
import os
from pathlib import Path
import re
import sys

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from setuptools import Distribution, setup
import importlib_metadata


def _read_base_version() -> str:
    from speaktype import __version__

    return __version__


BASE_VERSION = _read_base_version()
BUILD_VERSION = os.environ.get("SPEAKTYPE_BUILD_VERSION", BASE_VERSION)

if not re.fullmatch(r"\d+\.\d+\.\d+(?:(?:d|a|b|fc)\d+)?", BUILD_VERSION):
    raise SystemExit(
        "Invalid SPEAKTYPE_BUILD_VERSION. Use a macOS build version such as "
        "'2.3.0', '2.3.0d1', or '2.3.0b3'."
    )


RUNTIME_DISTRIBUTIONS = (
    "mlx-audio",
    "mlx-lm",
    "mlx",
    "sounddevice",
    "soundfile",
    "numpy",
    "rumps",
    "pynput",
    "pyobjc-framework-Cocoa",
    "pyobjc-framework-Quartz",
    "pyobjc-framework-AVFoundation",
    "pyperclip",
    "requests",
    "huggingface-hub",
)


def _runtime_modules() -> tuple[list[str], list[str]]:
    requested_extras = {}
    pending = [(name, set()) for name in RUNTIME_DISTRIBUTIONS]
    while pending:
        name, extras = pending.pop()
        name = canonicalize_name(name)
        previous_extras = requested_extras.get(name)
        if previous_extras is not None and extras.issubset(previous_extras):
            continue
        distribution = importlib_metadata.distribution(name)
        active_extras = (previous_extras or set()) | extras
        requested_extras[name] = active_extras
        for raw_requirement in distribution.requires or ():
            requirement = Requirement(raw_requirement)
            if requirement.marker is None or any(
                requirement.marker.evaluate({"extra": extra})
                for extra in active_extras | {""}
            ):
                pending.append((requirement.name, set(requirement.extras)))

    packages = {"speaktype"}
    modules = set()
    required = set(requested_extras)
    owners = importlib_metadata.packages_distributions()
    for module_name, distribution_names in owners.items():
        if not required.intersection(canonicalize_name(name) for name in distribution_names):
            continue
        if not module_name.isidentifier() or module_name == "tests":
            continue
        spec = importlib.util.find_spec(module_name)
        if spec is None:
            raise ModuleNotFoundError(f"Required runtime module is missing: {module_name}")
        if spec.submodule_search_locations is not None:
            packages.add(module_name)
        else:
            modules.add(module_name)

    return sorted(packages), sorted(modules)


PACKAGES, MODULES = _runtime_modules() if "py2app" in sys.argv else (["speaktype"], [])
COMMANDS = {}

if "py2app" in sys.argv:
    from macholib.dyld import dyld_find
    from macholib.MachO import MachO
    from py2app.build_app import py2app

    def python_runtime_libraries():
        _, runtime_path = py2app(Distribution()).get_runtime()
        prefix = Path(sys.base_prefix)
        pending = [Path(runtime_path)]
        pending.extend((prefix / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "lib-dynload").glob("*.so"))
        visited = set()
        libraries = set()
        environment = {"DYLD_LIBRARY_PATH": str(prefix / "lib")}
        while pending:
            binary = pending.pop()
            if binary in visited:
                continue
            visited.add(binary)
            for header in MachO(str(binary)).headers:
                for _, _, dependency in header.walkRelocatables():
                    if dependency.startswith(("/System/Library/", "/usr/lib/")):
                        continue
                    path = Path(dyld_find(
                        dependency,
                        executable_path=str(Path(sys.executable).parent),
                        loader_path=str(binary.parent),
                        env=environment,
                    ))
                    if path.is_relative_to(prefix / "lib") and path != Path(runtime_path):
                        libraries.add(str(path))
                        pending.append(path)
        return sorted(libraries)

    class SpeakTypeBuild(py2app):
        def initialize_prescripts(self):
            super().initialize_prescripts()
            bootstrap = str(Path("resources/runtime_bootstrap.py").resolve(strict=True))
            for target in self.targets:
                target.prescripts.insert(0, bootstrap)

        def get_bootstrap(self, bootstrap):
            if isinstance(bootstrap, str) and bootstrap in self.packages:
                spec = importlib.util.find_spec(bootstrap)
                locations = list(spec.submodule_search_locations or ())
                if len(locations) != 1:
                    raise RuntimeError(f"Expected one package directory for {bootstrap}: {locations}")
                return str(Path(locations[0]).resolve(strict=True))
            return super().get_bootstrap(bootstrap)

        def finalize_modulefinder(self, finder):
            namespace_packages = {
                name for name in self.packages
                if importlib.util.find_spec(name).origin is None
            }
            python_files, extensions = super().finalize_modulefinder(finder)
            # py2app 的空白 namespace 文件会遮住完整复制的 namespace 目录。
            return [item for item in python_files if item.identifier not in namespace_packages], extensions

    COMMANDS["py2app"] = SpeakTypeBuild
    FRAMEWORKS = python_runtime_libraries()
else:
    FRAMEWORKS = []

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "resources/SpeakType.icns",
    "plist": {
        "CFBundleName": "SpeakType",
        "CFBundleDisplayName": "SpeakType",
        "CFBundleIdentifier": "com.speaktype.app",
        "CFBundleVersion": BUILD_VERSION,
        "CFBundleShortVersionString": BASE_VERSION,
        "LSUIElement": False,
        "NSMicrophoneUsageDescription": "SpeakType needs microphone access for voice dictation.",
        "NSAppleEventsUsageDescription": "SpeakType needs accessibility access to detect the active application and insert text.",
        "CFBundleDocumentTypes": [],
        "LSMinimumSystemVersion": "14.0",
        "NSHighResolutionCapable": True,
        "PyErrorScripts": ["verify_error.sh"],
    },
    "packages": PACKAGES,
    "includes": sorted(set(MODULES) | {"AppKit", "Quartz", "objc"}),
    "frameworks": FRAMEWORKS,
    "excludes": ["sitecustomize"],
    "extra_scripts": ["scripts/verify_runtime.py"],
    "resources": ["resources/verify_error.sh"],
}

setup(
    name="SpeakType",
    version=BASE_VERSION,
    packages=["speaktype"],
    app=["main.py"],
    cmdclass=COMMANDS,
    options={"py2app": OPTIONS},
)
