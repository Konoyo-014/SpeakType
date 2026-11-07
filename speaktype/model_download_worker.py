import argparse
import json
import os
from pathlib import Path
import sys


script_directory = Path(__file__).resolve().parent
if script_directory.name == "Resources" and script_directory.parent.name == "Contents":
    sys.path.insert(0, str(script_directory / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}"))
else:
    sys.path.insert(0, str(script_directory.parent))
sys.dont_write_bytecode = True
os.environ["HF_HUB_DISABLE_XET"] = "1"

from huggingface_hub import HfApi, hf_hub_download, snapshot_download
from huggingface_hub.utils.tqdm import tqdm

from speaktype.model_download import download_error_message, get_cached_model_path, model_snapshot_is_complete


def emit(state: str, completed: int, total: int, message: str, **values):
    print(json.dumps({"state": state, "completed": int(completed), "total": int(total),
                      "message": message, **values}, ensure_ascii=False), flush=True)


def remote_file_sizes(model: str, revision: str, files) -> dict[str, int]:
    info = HfApi().model_info(model, revision=revision, files_metadata=True)
    if info.sha != revision:
        raise RuntimeError("远端模型文件信息与下载版本不一致。")
    if info.siblings is None:
        raise RuntimeError("远端模型没有返回文件信息。")
    metadata = {file.rfilename: file.size for file in info.siblings}
    sizes = {}
    for file in files:
        if file.filename not in metadata:
            raise RuntimeError(f"远端信息缺少模型文件：{file.filename}")
        size = metadata[file.filename]
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise RuntimeError(f"无法获取模型文件的远端大小：{file.filename}")
        sizes[file.filename] = size
    return sizes


def download(model: str, force: bool = False) -> Path:
    emit("preparing", 0, 0, "正在检查语音模型缓存。")
    cached = get_cached_model_path(model) if not force else None
    if cached is not None:
        total = sum(path.stat().st_size for path in cached.rglob("*") if path.is_file())
        emit("validating", total, total, "正在检查缓存中的模型文件。")
        if not model_snapshot_is_complete(cached):
            raise RuntimeError("缓存中的语音模型文件尚未完整。")
        emit("complete", total, total, "语音模型已经准备完成。", path=str(cached))
        return cached
    emit("preparing", 0, 0, "正在读取模型文件的实际大小。")
    files = snapshot_download(model, dry_run=True, force_download=force)
    if not files:
        raise RuntimeError("模型仓库没有返回可下载的文件。")
    commits = {file.commit_hash for file in files}
    if len(commits) != 1:
        raise RuntimeError("模型文件来自不同版本，无法开始下载。")
    revision = next(iter(commits))
    sizes = remote_file_sizes(model, revision, files)
    total = sum(sizes.values())
    completed = sum(sizes[file.filename] for file in files if file.is_cached and not force)
    emit("downloading", completed, total, "正在下载语音模型文件。")
    snapshot_path = None
    for file in sorted(files, key=lambda item: item.filename):
        if file.is_cached and not force:
            snapshot_path = Path(file.local_path).parents[len(Path(file.filename).parts) - 1]
            continue

        class FileProgress(tqdm):
            def __init__(self, *args, **kwargs):
                self._report_progress = not str(kwargs.get("name", "")).endswith(".transfer")
                kwargs["disable"] = True
                super().__init__(*args, **kwargs)
                self._completed_bytes = int(kwargs.get("initial", 0))
                if self._report_progress:
                    emit("downloading", min(completed + self._completed_bytes, total), total, f"正在下载 {file.filename}")

            def update(self, count=1):
                self._completed_bytes += int(count or 0)
                super().update(count)
                if self._report_progress:
                    emit("downloading", min(completed + self._completed_bytes, total), total, f"正在下载 {file.filename}")

        path = Path(hf_hub_download(model, file.filename, revision=revision, tqdm_class=FileProgress, force_download=force))
        if path.stat().st_size != sizes[file.filename]:
            raise RuntimeError(f"模型文件大小与远端信息不一致：{file.filename}")
        completed += sizes[file.filename]
        snapshot_path = path.parents[len(Path(file.filename).parts) - 1]
        emit("downloading", completed, total, f"已经下载 {file.filename}")
    if snapshot_path is None:
        raise RuntimeError("模型下载没有返回缓存目录。")
    emit("validating", completed, total, "正在检查模型权重、分词器和音频配置。")
    if not model_snapshot_is_complete(snapshot_path):
        raise RuntimeError("模型文件尚未完整，请重新下载缺少的文件。")
    emit("complete", total, total, "语音模型已经准备完成。", path=str(snapshot_path))
    return snapshot_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        download(args.model, force=args.force)
    except Exception as error:
        emit("error", 0, 0, download_error_message(error))
        raise


if __name__ == "__main__":
    main()
