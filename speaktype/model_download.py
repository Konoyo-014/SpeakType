"""Model download with progress tracking for SpeakType."""

import os
import logging
from pathlib import Path

logger = logging.getLogger("speaktype.model_download")


def is_model_cached(model_name: str) -> bool:
    """Check if a HuggingFace model is already in the local cache."""
    try:
        from huggingface_hub import try_to_load_from_cache, model_info
        # Check if config.json (always present) is cached
        result = try_to_load_from_cache(model_name, "config.json")
        return result is not None and isinstance(result, str)
    except Exception:
        return False


def download_model_with_progress(model_name: str, callback=None):
    """Download a HuggingFace model with progress reporting.

    Args:
        model_name: HuggingFace model ID (e.g., 'mlx-community/Qwen3-ASR-1.7B-8bit')
        callback: function(progress_pct: float, status: str) called on updates.
                  progress_pct is 0.0-100.0, status is a human-readable string.
    """
    from huggingface_hub import snapshot_download
    from tqdm.auto import tqdm as auto_tqdm

    class ProgressTqdm(auto_tqdm):
        """Custom tqdm that forwards progress to a callback."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._callback = callback

        def update(self, n=1):
            super().update(n)
            if self._callback and self.total and self.total > 0:
                pct = min(self.n / self.total * 100, 100.0)
                # Format size info
                done_mb = self.n / (1024 * 1024)
                total_mb = self.total / (1024 * 1024)
                if total_mb > 1024:
                    status = f"{done_mb / 1024:.1f}/{total_mb / 1024:.1f} GB"
                else:
                    status = f"{done_mb:.0f}/{total_mb:.0f} MB"
                try:
                    self._callback(pct, status)
                except Exception:
                    pass

    if callback:
        callback(0.0, "Starting...")

    logger.info(f"Downloading model: {model_name}")
    try:
        snapshot_download(
            model_name,
            tqdm_class=ProgressTqdm,
        )
        if callback:
            callback(100.0, "Done")
        logger.info(f"Model download complete: {model_name}")
    except Exception as e:
        logger.error(f"Model download failed: {e}")
        raise
