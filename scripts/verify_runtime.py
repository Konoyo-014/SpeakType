import argparse
import io
import os
from pathlib import Path
import runpy
import sys


parser = argparse.ArgumentParser()
parser.add_argument("--script", nargs=argparse.REMAINDER, metavar="PATH_AND_ARGS")
arguments = parser.parse_args()
script_path = None
if arguments.script is not None:
    if not arguments.script:
        parser.error("--script requires an absolute Python script path")
    script_path = Path(arguments.script[0])
    if not script_path.is_absolute() or not script_path.is_file():
        parser.error(f"--script requires an existing absolute Python script path: {script_path}")

script_dir = Path(__file__).resolve().parent
bundle_path = None
if script_dir.name == "Resources" and script_dir.parent.name == "Contents":
    bundle_path = script_dir.parent.parent
    runtime_dir = script_dir / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}"
    if not runtime_dir.is_dir():
        raise RuntimeError(f"Bundled Python runtime is missing: {runtime_dir}")
    sys.path.insert(0, str(runtime_dir))
else:
    sys.path.insert(0, str(script_dir.parent))

if os.environ.get("SPEAKTYPE_VERIFY_BUNDLE") and bundle_path is None:
    raise RuntimeError("Runtime verification must execute inside SpeakType.app")
if bundle_path is not None and not sys.dont_write_bytecode:
    raise RuntimeError("Bundled Python must disable bytecode writes before importing application modules")

import AppKit
import AVFoundation
import Quartz
import _cffi_backend
import httpcore2
import httpx2
import huggingface_hub
import miniaudio
import mlx.core as mx
import numpy as np
import sounddevice
import soundfile
import safetensors
import tokenizers
import transformers
import truststore
from huggingface_hub import HfApi, hf_hub_download, snapshot_download
from mlx_audio.audio_io import read as read_audio
from mlx_audio.stt import generate, utils
from mlx_audio.stt.models.qwen3_asr import qwen3_asr
from safetensors.numpy import load as load_safetensors, save as save_safetensors
from transformers import AutoTokenizer, WhisperFeatureExtractor
from transformers.models.qwen2.tokenization_qwen2 import Qwen2Tokenizer

from speaktype import __version__
from speaktype import app, updates


def require(condition: bool, message: str):
    if not condition:
        raise RuntimeError(message)


samples = (0.1 * np.sin(np.arange(16000, dtype=np.float32) * (2 * np.pi * 440 / 16000))).astype(np.float32)
require(bool(np.isfinite(samples).all()), "NumPy arithmetic failed")
weights = load_safetensors(save_safetensors({"audio": samples}))
require(bool(np.array_equal(weights["audio"], samples)), "SafeTensors round trip failed")
audio = io.BytesIO()
soundfile.write(audio, samples, 16000, format="WAV", subtype="PCM_16")
audio.seek(0)
decoded, sample_rate = soundfile.read(audio, dtype="float32")
require(sample_rate == 16000 and decoded.shape == samples.shape, "SoundFile WAV round trip failed")
require(bool(np.allclose(samples, decoded, atol=1 / 32768)), "SoundFile changed the WAV samples")
audio.seek(0)
decoded_mlx, sample_rate_mlx = read_audio(audio, dtype="float32")
require(sample_rate_mlx == 16000, "mlx-audio WAV decoder changed the sample rate")
require(bool(np.allclose(decoded, decoded_mlx, atol=1 / 32768)), "mlx-audio WAV decoder changed the samples")

mlx_result = mx.sum(mx.array([1.0, 2.0, 3.0]))
mx.eval(mlx_result)
require(float(mlx_result.item()) == 6.0, "MLX execution failed")
extractor = WhisperFeatureExtractor(feature_size=128, chunk_length=1)
features = extractor(samples, sampling_rate=16000, return_tensors="np")
require(features.input_features.shape == (1, 128, 100), "Qwen3-ASR feature extraction failed")
require(bool(np.isfinite(features.input_features).all()), "Qwen3-ASR features contain non-finite values")
require(callable(AutoTokenizer.from_pretrained) and callable(Qwen2Tokenizer), "Qwen tokenizer imports failed")
require(callable(qwen3_asr.Model) and callable(utils.load_model), "Qwen3-ASR model imports failed")
require(callable(generate.generate_transcription), "Qwen3-ASR generation imports failed")
require(callable(sounddevice.query_devices), "PortAudio import failed")
require(callable(HfApi.model_info) and callable(hf_hub_download) and callable(snapshot_download), "Hugging Face download API imports failed")
require(callable(app.run), "SpeakType application import failed")

if bundle_path is not None:
    for module in (
        AppKit, AVFoundation, Quartz, _cffi_backend, httpcore2, httpx2, huggingface_hub, miniaudio, mx, np,
        sounddevice, soundfile, safetensors, tokenizers, transformers, qwen3_asr, app,
        truststore,
    ):
        module_path = Path(module.__file__).resolve()
        require(module_path.is_relative_to(bundle_path), f"Module resolved outside the app: {module.__name__} ({module_path})")

if os.environ.get("SPEAKTYPE_VERIFY_NETWORK"):
    require(bundle_path is not None, "Network verification must execute inside SpeakType.app")
    release = updates.check_for_update(__version__)
    require(release.error is None, f"Bundled update check failed: {release.error}")
    require(bool(release.latest_version and release.download_url), "Bundled update check returned incomplete release data")
    model = HfApi().model_info("mlx-community/Qwen3-ASR-1.7B-8bit")
    require(model.id == "mlx-community/Qwen3-ASR-1.7B-8bit" and bool(model.sha), "Bundled model lookup returned incomplete metadata")
    print(f"Verified bundled HTTPS: GitHub {release.latest_version}; Hugging Face {model.id} at {model.sha}.")

print(f"SpeakType {__version__}: runtime imports, WAV codecs, MLX execution, and Qwen3-ASR feature extraction passed.")

if script_path is not None:
    sys.argv = [str(script_path), *arguments.script[1:]]
    runpy.run_path(str(script_path), run_name="__main__")
