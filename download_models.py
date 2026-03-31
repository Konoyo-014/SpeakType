#!/usr/bin/env python3
"""Download all required models for SpeakType."""

import os
import sys
import subprocess


def download_asr_model():
    """Download the Qwen3-ASR model via mlx-audio."""
    print("\n▶ Downloading ASR model (Qwen3-ASR-1.7B-8bit)...")
    print("  This may take a while depending on network speed.\n")

    # Try mirror first, then fallback to direct
    mirrors = [
        ("hf-mirror.com", "https://hf-mirror.com"),
        ("huggingface.co", None),
    ]

    from huggingface_hub import snapshot_download

    for name, endpoint in mirrors:
        try:
            print(f"  Trying {name}...")
            kwargs = {"repo_id": "mlx-community/Qwen3-ASR-1.7B-8bit"}
            if endpoint:
                os.environ["HF_ENDPOINT"] = endpoint
                kwargs["endpoint"] = endpoint
            path = snapshot_download(**kwargs)
            print(f"  ✓ ASR model downloaded to: {path}")
            return True
        except Exception as e:
            print(f"  ✗ Failed from {name}: {e}")
            continue

    # Fallback: try whisper-small
    print("\n  Falling back to whisper-small...")
    try:
        path = snapshot_download("mlx-community/whisper-small-mlx")
        print(f"  ✓ Whisper-small downloaded to: {path}")
        return True
    except Exception as e:
        print(f"  ✗ Whisper fallback also failed: {e}")
        return False


def download_llm_model():
    """Download the LLM model via Ollama."""
    print("\n▶ Downloading LLM model (qwen3.5:4b)...")

    # Check Ollama
    ollama_bin = "/opt/homebrew/opt/ollama/bin/ollama"
    if not os.path.exists(ollama_bin):
        ollama_bin = "ollama"

    # Check if running
    try:
        import requests
        resp = requests.get("http://localhost:11434/api/tags", timeout=3)
        if resp.status_code != 200:
            raise Exception("Ollama not responding")
    except Exception:
        print("  Starting Ollama...")
        subprocess.Popen(
            [ollama_bin, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={**os.environ, "OLLAMA_FLASH_ATTENTION": "1"},
        )
        import time
        time.sleep(3)

    # Pull model
    try:
        result = subprocess.run(
            [ollama_bin, "pull", "qwen3.5:4b"],
            timeout=3600,
        )
        if result.returncode == 0:
            print("  ✓ LLM model downloaded")
            return True
    except Exception as e:
        print(f"  ✗ LLM download failed: {e}")

    return False


if __name__ == "__main__":
    print("╔══════════════════════════════════════╗")
    print("║   SpeakType Model Downloader         ║")
    print("╚══════════════════════════════════════╝")

    asr_ok = download_asr_model()
    llm_ok = download_llm_model()

    print("\n" + "=" * 40)
    print(f"ASR Model: {'✓ Ready' if asr_ok else '✗ Failed'}")
    print(f"LLM Model: {'✓ Ready' if llm_ok else '✗ Failed'}")

    if not asr_ok:
        print("\nTo manually download ASR model:")
        print("  python -c \"from huggingface_hub import snapshot_download; snapshot_download('mlx-community/Qwen3-ASR-1.7B-8bit')\"")

    if not llm_ok:
        print("\nTo manually download LLM model:")
        print("  ollama pull qwen3.5:4b")
