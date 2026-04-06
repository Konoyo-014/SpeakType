"""Tests for runtime launch target resolution."""

from pathlib import Path
import sys

from speaktype import runtime
from speaktype.runtime import get_launch_program_args


def test_get_launch_program_args_prefers_running_bundle():
    args, working_dir = get_launch_program_args(
        "/tmp/project/speaktype/settings_window.py",
        bundle_path="/Applications/SpeakType.app",
    )

    assert args == ["open", "/Applications/SpeakType.app"]
    assert working_dir == "/Applications"


def test_get_launch_program_args_falls_back_to_source_entrypoint(tmp_path):
    module_file = tmp_path / "speaktype" / "settings_window.py"
    module_file.parent.mkdir()
    module_file.write_text("", encoding="utf-8")

    args, working_dir = get_launch_program_args(str(module_file), bundle_path="")

    assert args == [
        str(tmp_path / "venv" / "bin" / "python3"),
        str(tmp_path / "main.py"),
    ]
    assert working_dir == str(tmp_path)


def test_get_runtime_version_prefers_bundle_build_version(monkeypatch):
    monkeypatch.setattr(runtime, "get_running_bundle_path", lambda: "/Applications/SpeakType.app")

    class FakeBundle:
        def infoDictionary(self):
            return {"CFBundleVersion": "2.0.1d7"}

    class FakeNSBundle:
        @staticmethod
        def mainBundle():
            return FakeBundle()

    class FakeAppKit:
        NSBundle = FakeNSBundle

    monkeypatch.setitem(sys.modules, "AppKit", FakeAppKit)

    assert runtime.get_runtime_version("2.0.1") == "2.0.1d7"


def test_get_runtime_version_falls_back_without_bundle(monkeypatch):
    monkeypatch.setattr(runtime, "get_running_bundle_path", lambda: "")

    assert runtime.get_runtime_version("2.0.1") == "2.0.1"
