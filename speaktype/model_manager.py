from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

import requests
from huggingface_hub import try_to_load_from_cache

from .config import CONFIG_DIR
from .diagnostics import find_ollama_binary
from .model_download import get_cached_model_path, model_snapshot_is_complete
from .polish import ollama_model_is_available
from .runtime import get_running_bundle_path


@dataclass(frozen=True)
class TransferProgress:
    state: str
    completed: int
    total: int
    message: str

    @property
    def percent(self) -> float:
        if self.state == "complete":
            return 100.0
        return min(100.0, max(0.0, self.completed * 100 / self.total)) if self.total > 0 else 0.0


class DownloadCancelled(RuntimeError):
    pass


class OllamaUpdateRequired(RuntimeError):
    pass


class CancelToken:
    def __init__(self):
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._response = None
        self._process = None

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def check_cancelled(self):
        if self.cancelled:
            raise DownloadCancelled("下载已取消，已经下载的缓存仍然保留。")

    def cancel(self):
        self._event.set()
        with self._lock:
            response, process = self._response, self._process
        if process is not None and process.poll() is None:
            process.terminate()
        if response is not None:
            threading.Thread(target=response.close, name="SpeakType-HTTP-cancel", daemon=True).start()

    def bind_response(self, response):
        with self._lock:
            self._response = response
        if self.cancelled:
            response.close()
        self.check_cancelled()

    def bind_process(self, process):
        with self._lock:
            self._process = process
        if self.cancelled and process.poll() is None:
            process.terminate()
        self.check_cancelled()

    def release_response(self, response):
        with self._lock:
            if self._response is response:
                self._response = None

    def release_process(self, process):
        with self._lock:
            if self._process is process:
                self._process = None


def inspect_asr(model_id: str) -> dict:
    cached_config = try_to_load_from_cache(model_id, "config.json")
    if isinstance(cached_config, str):
        snapshot = Path(cached_config).parent
        required_files = ("config.json", "tokenizer_config.json", "preprocessor_config.json",
                          "tokenizer.json", "vocab.json", "merges.txt", "model.safetensors.index.json")
        candidates = [snapshot / name for name in required_files] + list(snapshot.glob("*.safetensors"))
        for file in candidates:
            if file.is_file() and file.stat().st_size == 0:
                raise RuntimeError(f"语音模型缓存中的文件为空：{file.name}。请重新下载完整模型。")
    path = get_cached_model_path(model_id)
    return {
        "cached": path is not None,
        "path": str(path) if path is not None else None,
        "size_bytes": sum(file.stat().st_size for file in path.rglob("*") if file.is_file()) if path else 0,
    }


def _ollama_endpoint(base_url: str, endpoint: str) -> str:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Ollama 地址需要包含 http:// 或 https:// 和主机名称。")
    return f"{base_url.rstrip('/')}/api/{endpoint}"


def _ollama_app() -> Path | None:
    return next((path for path in (Path("/Applications/Ollama.app"), Path.home() / "Applications/Ollama.app") if path.is_dir()), None)


def inspect_ollama(base_url: str) -> dict:
    installed = bool(find_ollama_binary() or _ollama_app())
    with requests.Session() as session:
        session.trust_env = False
        try:
            response = session.get(_ollama_endpoint(base_url, "tags"), timeout=(1, 2))
            response.raise_for_status()
            models = response.json()["models"]
            if not isinstance(models, list):
                raise ValueError("Ollama 的模型列表格式无效。")
            return {
                "running": True,
                "models": [{"name": model["name"], "size": int(model.get("size", 0))} for model in models],
                "installed": installed,
                "error": "",
            }
        except (requests.RequestException, ValueError, KeyError, TypeError) as error:
            return {"running": False, "models": [], "installed": installed, "error": str(error)}


def start_installed_ollama(base_url: str) -> None:
    if inspect_ollama(base_url)["running"]:
        return
    parsed = urlsplit(base_url)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("请在配置的 Ollama 服务器上启动服务。")
    app, binary = _ollama_app(), find_ollama_binary()
    if app is not None:
        subprocess.run(["open", "-gj", str(app)], check=True, timeout=10)
    elif binary:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        environment = dict(os.environ, OLLAMA_HOST=parsed.netloc, OLLAMA_NOPRUNE="1")
        with (CONFIG_DIR / "ollama-start.log").open("a", encoding="utf-8") as log:
            subprocess.Popen([binary, "serve"], stdout=log, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, start_new_session=True, env=environment)
    else:
        raise RuntimeError("请先安装 Ollama 桌面应用，再点击启动服务。")
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if inspect_ollama(base_url)["running"]:
            return
        time.sleep(0.2)
    raise RuntimeError("Ollama 服务尚未启动成功，请查看 Ollama 应用或服务日志。")


def pull_ollama(base_url: str, model: str, callback, token: CancelToken) -> None:
    token.check_cancelled()
    completed = total = 0
    layers = {}
    response = None
    callback(TransferProgress("preparing", 0, 0, "正在连接 Ollama 模型服务。"))
    try:
        with requests.Session() as session:
            session.trust_env = False
            response = session.post(_ollama_endpoint(base_url, "pull"), json={"model": model, "stream": True},
                                    stream=True, timeout=(5, 30))
            token.bind_response(response)
            if response.status_code == 412:
                raise OllamaUpdateRequired(response.text or "请更新 Ollama 后再下载所需模型。")
            response.raise_for_status()
            success = False
            for line in response.iter_lines(chunk_size=1):
                token.check_cancelled()
                if not line:
                    continue
                event = json.loads(line)
                if event.get("error"):
                    if "requires a newer version of ollama" in str(event["error"]).lower():
                        raise OllamaUpdateRequired(str(event["error"]))
                    raise RuntimeError(f"Ollama 模型下载失败：{event['error']}")
                status = event.get("status", "")
                digest = event.get("digest")
                if digest and "total" in event:
                    layer_total = int(event["total"])
                    layer_completed = int(event.get("completed", 0))
                    layers[digest] = (min(layer_completed, layer_total), layer_total)
                    completed = sum(item[0] for item in layers.values())
                    total = sum(item[1] for item in layers.values())
                state = "validating" if status.startswith(("verifying", "writing", "removing")) else "downloading"
                if status == "success":
                    success = True
                    break
                callback(TransferProgress(state, completed, total, status or "正在下载 Ollama 模型。"))
            token.check_cancelled()
            if not success:
                raise RuntimeError("Ollama 下载连接已经结束，但模型尚未报告完成。")
            callback(TransferProgress("validating", completed, total, "正在确认模型已经安装。"))
            state = inspect_ollama(base_url)
            if not state["running"] or not ollama_model_is_available(model, [item["name"] for item in state["models"]]):
                raise RuntimeError("Ollama 下载结束后仍然找不到所需模型。")
            token.check_cancelled()
            callback(TransferProgress("complete", total, total, "Ollama 模型已经准备完成。"))
    except Exception:
        if token.cancelled:
            callback(TransferProgress("cancelled", completed, total, "下载已取消，缓存仍然保留。"))
            raise DownloadCancelled("Ollama 模型下载已取消。") from None
        raise
    finally:
        if response is not None:
            token.release_response(response)
            response.close()


def download_asr(model: str, callback, token: CancelToken, force: bool = False) -> Path:
    token.check_cancelled()
    bundle = get_running_bundle_path()
    if bundle:
        executable = Path(bundle) / "Contents/MacOS/model_download_worker"
        if not executable.is_file():
            raise FileNotFoundError(f"应用缺少模型下载程序：{executable}")
        command = [str(executable), "--model", model]
    else:
        command = [sys.executable, str(Path(__file__).with_name("model_download_worker.py")), "--model", model]
    if force:
        command.append("--force")
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    completed = total = 0
    result = None
    process = None
    error_message = ""
    try:
        with (CONFIG_DIR / "asr-download.log").open("a", encoding="utf-8") as log:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=log, text=True,
                                       encoding="utf-8", bufsize=1,
                                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1",
                                                SPEAKTYPE_MODEL_DOWNLOAD_WORKER="1", HF_HUB_DISABLE_XET="1"))
        token.bind_process(process)
        for line in process.stdout:
            token.check_cancelled()
            event = json.loads(line)
            completed, total = int(event["completed"]), int(event["total"])
            if event["state"] == "error":
                error_message = event["message"]
                continue
            if event["state"] == "complete":
                result = Path(event["path"])
            callback(TransferProgress(event["state"], completed, total, event["message"]))
        returncode = process.wait()
        token.check_cancelled()
        if returncode != 0:
            raise RuntimeError(error_message or f"语音模型下载程序退出，状态码为 {returncode}。")
        if result is None or not model_snapshot_is_complete(result):
            raise RuntimeError("语音模型下载结束，但模型文件尚未完整。")
        return result
    except Exception:
        if token.cancelled:
            callback(TransferProgress("cancelled", completed, total, "下载已取消，缓存仍然保留。"))
            raise DownloadCancelled("语音模型下载已取消。") from None
        raise
    finally:
        if process is not None:
            token.release_process(process)
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            if process.stdout is not None:
                process.stdout.close()
