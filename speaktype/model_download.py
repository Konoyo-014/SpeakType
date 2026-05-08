"""Model download with progress tracking for SpeakType."""

import logging
from pathlib import Path

logger = logging.getLogger("speaktype.model_download")


def format_progress_status(done_bytes: float, total_bytes: float) -> str:
    if total_bytes <= 0:
        return ""
    done_mb = done_bytes / (1024 * 1024)
    total_mb = total_bytes / (1024 * 1024)
    if total_mb > 1024:
        return f"{done_mb / 1024:.1f}/{total_mb / 1024:.1f} GB"
    return f"{done_mb:.0f}/{total_mb:.0f} MB"


def make_progress_tqdm(callback=None):
    from tqdm.auto import tqdm as auto_tqdm

    class ProgressTqdm(auto_tqdm):
        """tqdm wrapper that forwards byte progress to the setup wizard."""

        def __init__(self, *args, **kwargs):
            # huggingface_hub>=1.8 passes a logging/telemetry-only name kwarg
            # that some tqdm variants reject in packaged macOS builds.
            kwargs.pop("name", None)
            super().__init__(*args, **kwargs)
            self._callback = callback

        def update(self, n=1):
            super().update(n)
            if self._callback and self.total and self.total > 0:
                pct = min(self.n / self.total * 100, 100.0)
                status = format_progress_status(self.n, self.total)
                try:
                    self._callback(pct, status)
                except Exception:
                    pass

    return ProgressTqdm


def is_model_cached(model_name: str) -> bool:
    """Check if a HuggingFace model is already in the local cache."""
    return get_cached_model_path(model_name) is not None


def get_cached_model_path(model_name: str) -> Path | None:
    """Return the local HuggingFace snapshot path when the model is cached."""
    try:
        from huggingface_hub import try_to_load_from_cache

        result = try_to_load_from_cache(model_name, "config.json")
        if not isinstance(result, str):
            return None
        path = Path(result).parent
        return path if path.exists() else None
    except Exception:
        return None


def download_model_with_progress(model_name: str, callback=None):
    """Download a HuggingFace model with progress reporting.

    Args:
        model_name: HuggingFace model ID (e.g., 'mlx-community/Qwen3-ASR-1.7B-8bit')
        callback: function(progress_pct: float, status: str) called on updates.
                  progress_pct is 0.0-100.0, status is a human-readable string.
    """
    from huggingface_hub import snapshot_download

    if callback:
        callback(0.0, "Starting...")

    logger.info(f"Downloading model: {model_name}")
    try:
        snapshot_download(
            model_name,
            tqdm_class=make_progress_tqdm(callback),
        )
        if callback:
            callback(100.0, "Done")
        logger.info(f"Model download complete: {model_name}")
    except Exception as e:
        logger.error(f"Model download failed: {e}")
        raise
