"""Tests for bundled sounddevice compatibility."""

from types import SimpleNamespace

from speaktype.sounddevice_compat import ensure_sounddevice_data_dir


def test_ensure_sounddevice_data_dir_extracts_when_package_path_is_not_real(tmp_path):
    package = SimpleNamespace(__path__=["/tmp/python310.zip/_sounddevice_data"])

    def fake_get_data(package_name, resource_name):
        assert package_name == "_sounddevice_data"
        if resource_name.endswith("libportaudio.dylib"):
            return b"portaudio-bytes"
        if resource_name.endswith("README.md"):
            return b"readme"
        return None

    extracted = ensure_sounddevice_data_dir(
        package,
        data_getter=fake_get_data,
        extract_root=str(tmp_path / "sounddevice_data"),
    )

    assert extracted == str(tmp_path / "sounddevice_data")
    assert package.__path__ == [str(tmp_path / "sounddevice_data")]
    assert (tmp_path / "sounddevice_data" / "portaudio-binaries" / "libportaudio.dylib").read_bytes() == b"portaudio-bytes"


def test_ensure_sounddevice_data_dir_keeps_real_package_path(tmp_path):
    real_dir = tmp_path / "_sounddevice_data"
    real_dir.mkdir()
    package = SimpleNamespace(__path__=[str(real_dir)])

    def fake_get_data(package_name, resource_name):
        raise AssertionError("data getter should not be used for real package paths")

    extracted = ensure_sounddevice_data_dir(package, data_getter=fake_get_data)

    assert extracted == str(real_dir)
    assert package.__path__ == [str(real_dir)]
