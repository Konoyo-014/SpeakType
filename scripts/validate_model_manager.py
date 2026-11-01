import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
from unittest import TestCase


repository = Path(__file__).resolve().parents[1]
bundle = Path(os.environ["SPEAKTYPE_TEST_BUNDLE"]).resolve() if os.environ.get("SPEAKTYPE_TEST_BUNDLE") else None
sys.path.insert(0, str(bundle / "Contents/Resources/lib/python3.10") if bundle else str(repository))

from speaktype.model_manager import (
    CancelToken,
    DownloadCancelled,
    download_asr,
    inspect_asr,
    inspect_ollama,
    pull_ollama,
    start_installed_ollama,
)
from speaktype.model_download import model_snapshot_is_complete


parser = argparse.ArgumentParser()
parser.add_argument("--ollama-url", default="http://localhost:11434")
parser.add_argument("--ollama-model", default="qwen3-vl:2b-instruct")
parser.add_argument("--asr-model", default="mlx-community/Qwen3-ASR-1.7B-8bit")
parser.add_argument("--repair-cache", action="store_true")
parser.add_argument("--force-repair-cache", action="store_true")
parser.add_argument("--force-cancel-only", action="store_true")
parser.add_argument("--skip-ollama-pull", action="store_true")
parser.add_argument("--report", type=Path, default=repository / "work/model-manager-validation/report.json")
args = parser.parse_args()
args.force_repair_cache = args.force_repair_cache or args.force_cancel_only
report = {"runtime": str(bundle) if bundle else "source", "cases": []}


def write_report():
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"REPORT {args.report}")


service = inspect_ollama(args.ollama_url)
assert service["running"] and service["installed"], service
assert any(model["name"] == args.ollama_model for model in service["models"]), service
start_installed_ollama(args.ollama_url)
report["cases"].append({"name": "existing_ollama_service", "models": service["models"]})
assert not inspect_ollama("http://127.0.0.1:1")["running"]

cache = inspect_asr(args.asr_model)
assert cache["cached"] and cache["size_bytes"] > 0, cache
events = []
path = download_asr(args.asr_model, events.append, CancelToken())
assert path == Path(cache["path"])
assert events[-1].state == "complete" and events[-1].percent == 100
report["cases"].append({"name": "cached_asr_worker", "path": str(path), "size_bytes": cache["size_bytes"],
                        "states": [event.state for event in events]})

token = CancelToken()
process_was_running = []


def cancel_asr(progress):
    if progress.state == "preparing" and not token.cancelled:
        process_was_running.append(token._process.poll() is None)
        token.cancel()


started = time.monotonic()
with TestCase().assertRaises(DownloadCancelled):
    download_asr(args.asr_model, cancel_asr, token)
assert process_was_running == [True], process_was_running
assert inspect_asr(args.asr_model)["cached"]
events = []
download_asr(args.asr_model, events.append, CancelToken())
assert events[-1].state == "complete"
report["cases"].append({"name": "cancel_actual_asr_worker_and_retry", "seconds": round(time.monotonic() - started, 3)})

if not args.skip_ollama_pull:
    token = CancelToken()
    response_was_open = []
    cancelled_responses = []
    cancellation_seconds = []

    def cancel_ollama(progress):
        if progress.state == "downloading" and not token.cancelled:
            response_was_open.append(token._response is not None and not token._response.raw.closed)
            cancelled_responses.append(token._response)
            cancel_started = time.monotonic()
            token.cancel()
            cancellation_seconds.append(time.monotonic() - cancel_started)

    started = time.monotonic()
    with TestCase().assertRaises(DownloadCancelled):
        pull_ollama(args.ollama_url, args.ollama_model, cancel_ollama, token)
    assert response_was_open == [True], response_was_open
    assert cancelled_responses[0].raw.closed
    assert cancellation_seconds[0] < 0.2, cancellation_seconds
    assert inspect_ollama(args.ollama_url)["running"]
    events = []
    pull_ollama(args.ollama_url, args.ollama_model, events.append, CancelToken())
    assert events[-1].state == "complete" and events[-1].percent == 100
    report["cases"].append({"name": "cancel_actual_ollama_stream_and_retry", "seconds": round(time.monotonic() - started, 3),
                            "cancel_call_seconds": cancellation_seconds[0], "http_closed": cancelled_responses[0].raw.closed,
                            "states": [event.state for event in events]})

if args.repair_cache or args.force_repair_cache:
    work = repository / "work"
    with tempfile.TemporaryDirectory(dir=work, prefix="asr-cache-repair-") as temporary:
        isolated_home = Path(temporary)
        original_snapshot = Path(cache["path"])
        original_repository = original_snapshot.parent.parent
        isolated_repository = isolated_home / "hub" / original_repository.name
        shutil.copytree(original_repository, isolated_repository, symlinks=True, copy_function=os.link)
        isolated_snapshot = isolated_repository / "snapshots" / original_snapshot.name
        missing = isolated_snapshot / "tokenizer_config.json"
        expected = hashlib.sha256(missing.read_bytes()).hexdigest()
        missing.resolve(strict=True).unlink()
        if args.force_repair_cache:
            missing.resolve().write_text("invalid-json", encoding="utf-8")
            with TestCase().assertRaises(json.JSONDecodeError):
                model_snapshot_is_complete(isolated_snapshot)
        else:
            missing.unlink(missing_ok=True)
        variables = ("HF_HOME", "HF_HUB_CACHE", "HF_HUB_OFFLINE")
        previous = {name: os.environ.get(name) for name in variables}
        os.environ["HF_HOME"] = str(isolated_home)
        os.environ.pop("HF_HUB_CACHE", None)
        os.environ.pop("HF_HUB_OFFLINE", None)
        events = []
        try:
            if args.force_repair_cache:
                token = CancelToken()
                cancelled_progress = []

                def cancel_force(progress):
                    cancelled_progress.append(progress)
                    if progress.total:
                        assert progress.total == cache["size_bytes"], (progress.total, cache["size_bytes"])
                    if progress.state == "downloading" and progress.completed > 0 and not token.cancelled:
                        assert token._process.poll() is None
                        token.cancel()

                with TestCase().assertRaises(DownloadCancelled):
                    download_asr(args.asr_model, cancel_force, token, force=True)
                assert any(progress.completed > 0 for progress in cancelled_progress)
                report["cases"].append({"name": "force_remote_size_and_actual_download_cancellation",
                                        "total": cache["size_bytes"],
                                        "states": [progress.state for progress in cancelled_progress]})
                if args.force_cancel_only:
                    write_report()
                    sys.exit(0)
            repaired = download_asr(args.asr_model, events.append, CancelToken(), force=args.force_repair_cache)
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        assert repaired == isolated_snapshot
        assert hashlib.sha256(missing.read_bytes()).hexdigest() == expected
        assert any(event.state == "downloading" for event in events)
        assert events[-1].state == "complete"
        if args.force_repair_cache:
            assert events[-1].total == cache["size_bytes"], (events[-1].total, cache["size_bytes"])
        assert inspect_asr(args.asr_model)["cached"]
        report["cases"].append({"name": "force_repair_real_corrupt_cache_over_https" if args.force_repair_cache else "repair_real_missing_cached_file_over_https",
                                "states": [event.state for event in events],
                                "completed": events[-1].completed, "total": events[-1].total})

write_report()
