import logging
import json
from pathlib import Path
import socket
import ssl

import httpx2
from huggingface_hub import try_to_load_from_cache
from huggingface_hub.errors import DryRunError, HfHubHTTPError, OfflineModeIsEnabled
from safetensors import safe_open

logger = logging.getLogger("speaktype.model_download")


def download_error_message(error: Exception) -> str:
    causes = []
    visited = set()
    cause = error
    while cause is not None and id(cause) not in visited:
        visited.add(id(cause))
        causes.append(cause)
        cause = cause.__cause__ if cause.__cause__ is not None else cause.__context__

    status = next((cause.response.status_code for cause in causes
                   if isinstance(cause, (httpx2.HTTPStatusError, HfHubHTTPError))
                   and cause.response is not None), None)
    if any(isinstance(cause, OfflineModeIsEnabled) for cause in causes):
        guidance = "模型下载处于离线模式。请关闭 Hugging Face 离线模式后重试。"
    elif any(isinstance(cause, ssl.SSLCertVerificationError) for cause in causes):
        guidance = "无法验证模型下载服务的安全证书。请检查系统时间、系统证书和网络代理设置后重试。"
    elif any(isinstance(cause, socket.gaierror) for cause in causes):
        guidance = "无法解析模型下载服务的网络地址。请检查网络连接、DNS 或系统代理设置后重试。"
    elif any(isinstance(cause, httpx2.ConnectTimeout) for cause in causes):
        guidance = "连接模型下载服务超时。请检查网络连接或系统代理设置后重试。"
    elif any(isinstance(cause, httpx2.ReadTimeout) for cause in causes):
        guidance = "等待模型下载数据超时。已下载的缓存仍然保留，请检查网络连接后重试。"
    elif any(isinstance(cause, (httpx2.TimeoutException, TimeoutError)) for cause in causes):
        guidance = "模型下载连接超时。请检查网络连接后重试。"
    elif any(isinstance(cause, httpx2.ProxyError) for cause in causes):
        guidance = "无法通过网络代理连接模型下载服务。请检查系统代理是否正常运行后重试。"
    elif any(isinstance(cause, (httpx2.ConnectError, ConnectionError)) for cause in causes):
        guidance = "无法连接模型下载服务。请检查网络连接或系统代理设置后重试。"
    elif status == 404:
        guidance = "模型下载服务找不到所需模型或文件（HTTP 404）。请检查模型名称和下载地址后重试。"
    elif status in (401, 403):
        guidance = f"模型下载服务拒绝了访问（HTTP {status}）。请检查模型访问权限和网络访问限制后重试。"
    elif status == 429:
        guidance = "模型下载服务限制了请求频率（HTTP 429）。请稍后重试。"
    elif status is not None and status >= 500:
        guidance = f"模型下载服务返回错误（HTTP {status}）。已下载的缓存仍然保留，请检查下载地址或稍后重试。"
    else:
        guidance = "模型下载失败。请根据详细原因处理后重试。"

    messages = []
    for cause in causes:
        if isinstance(cause, DryRunError) and len(causes) > 1:
            continue
        message = str(cause).strip() or type(cause).__name__
        if message not in messages:
            messages.append(message)
    return guidance + "\n\n详细原因：\n" + "\n".join(messages)


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
    result = try_to_load_from_cache(model_name, "config.json")
    if not isinstance(result, str):
        return None
    path = Path(result).parent
    return path if model_snapshot_is_complete(path) else None


def model_snapshot_is_complete(path: Path) -> bool:
    required = ("config.json", "tokenizer_config.json", "preprocessor_config.json")
    if any(not (path / name).is_file() or not (path / name).stat().st_size for name in required):
        return False
    json_files = [path / name for name in required]
    if (path / "tokenizer.json").is_file():
        json_files.append(path / "tokenizer.json")
    elif all((path / name).is_file() and (path / name).stat().st_size for name in ("vocab.json", "merges.txt")):
        json_files.append(path / "vocab.json")
    else:
        return False
    for json_file in json_files:
        if not json_file.stat().st_size:
            return False
        contents = json.loads(json_file.read_text(encoding="utf-8"))
        if not isinstance(contents, dict) or not contents:
            raise ValueError(f"Model configuration must be a nonempty JSON object: {json_file}")
    index_path = path / "model.safetensors.index.json"
    expected_size = 0
    if index_path.is_file():
        index = json.loads(index_path.read_text(encoding="utf-8"))
        if not isinstance(index, dict):
            raise ValueError(f"Invalid model weight index: {index_path}")
        weight_map = index.get("weight_map")
        if not isinstance(weight_map, dict) or not weight_map:
            raise ValueError(f"Invalid model weight index: {index_path}")
        if any(not isinstance(name, str) or Path(name).name != name for name in weight_map.values()):
            raise ValueError(f"Invalid model shard paths: {index_path}")
        names = set(weight_map.values())
        expected_size = index.get("metadata", {}).get("total_size", 0)
        if isinstance(expected_size, bool) or not isinstance(expected_size, int) or expected_size < 0:
            raise ValueError(f"Invalid model size in index: {index_path}")
        shards = [path / name for name in names]
    else:
        shards = list(path.glob("*.safetensors"))
    if not shards or any(not shard.is_file() or shard.stat().st_size == 0 for shard in shards):
        return False
    if sum(shard.stat().st_size for shard in shards) < expected_size:
        return False
    shard_keys = {}
    for shard in shards:
        with safe_open(shard, framework="np") as weights:
            shard_keys[shard.name] = set(weights.keys())
            if not shard_keys[shard.name]:
                return False
    if index_path.is_file() and any(tensor not in shard_keys[name] for tensor, name in weight_map.items()):
        raise ValueError(f"Model weight index references missing tensors: {index_path}")
    return True


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
        path = snapshot_download(
            model_name,
            tqdm_class=make_progress_tqdm(callback),
        )
        if not model_snapshot_is_complete(Path(path)):
            raise RuntimeError("The model download is incomplete. Download the missing model files before continuing.")
        if callback:
            callback(100.0, "Done")
        logger.info(f"Model download complete: {model_name}")
    except Exception as e:
        logger.error(f"Model download failed: {e}")
        raise
