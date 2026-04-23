"""Tests for local HuggingFace model cache helpers."""

from speaktype.model_download import get_cached_model_path, is_model_cached


def test_cached_model_path_keeps_snapshot_parent_for_symlinked_files(monkeypatch, tmp_path):
    snapshot_dir = tmp_path / "models--org--repo" / "snapshots" / "abc123"
    blob_dir = tmp_path / "models--org--repo" / "blobs"
    snapshot_dir.mkdir(parents=True)
    blob_dir.mkdir(parents=True)
    blob_config = blob_dir / "config-blob"
    blob_config.write_text("{}", encoding="utf-8")
    config_link = snapshot_dir / "config.json"
    config_link.symlink_to(blob_config)

    monkeypatch.setattr(
        "huggingface_hub.try_to_load_from_cache",
        lambda model_name, filename: str(config_link),
    )

    assert get_cached_model_path("org/repo") == snapshot_dir
    assert is_model_cached("org/repo") is True
