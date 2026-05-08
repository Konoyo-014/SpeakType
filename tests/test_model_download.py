"""Tests for local HuggingFace model cache and download progress helpers."""

from io import StringIO

from speaktype.model_download import (
    format_progress_status,
    get_cached_model_path,
    is_model_cached,
    make_progress_tqdm,
)


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


def test_format_progress_status_uses_mb_and_gb():
    assert format_progress_status(5 * 1024 * 1024, 10 * 1024 * 1024) == "5/10 MB"
    assert format_progress_status(1536 * 1024 * 1024, 3 * 1024 * 1024 * 1024) == "1.5/3.0 GB"


def test_progress_tqdm_accepts_huggingface_name_kwarg():
    calls = []
    progress = make_progress_tqdm(lambda pct, status: calls.append((round(pct), status)))

    bar = progress(
        total=10,
        disable=False,
        file=StringIO(),
        unit="B",
        unit_scale=True,
        name="huggingface_hub.snapshot_download",
    )
    bar.update(5)
    bar.close()

    assert calls == [(50, "0/0 MB")]
