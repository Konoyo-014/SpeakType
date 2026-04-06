"""Tests for runtime launch target resolution."""

from pathlib import Path

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
