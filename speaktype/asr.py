"""ASR engine with Qwen3-ASR (mlx-audio) and Whisper compatibility."""

import os
import logging
import tempfile
import threading

logger = logging.getLogger("speaktype.asr")

ASR_MODELS = [
    "mlx-community/Qwen3-ASR-1.7B-8bit",
    "mlx-community/Qwen3-ASR-0.6B-4bit",
]

WHISPER_MODELS = ["tiny", "base", "small", "medium", "large"]
TRANSCRIPT_OUTPUT_EXTENSIONS = (".txt", ".srt", ".vtt", ".json")


def _make_temp_transcript_output_path() -> str:
    """Return a temporary output stem for mlx-audio's mandatory save step."""
    fd, path = tempfile.mkstemp(prefix="speaktype-transcript-", suffix="")
    os.close(fd)
    try:
        os.unlink(path)
    except OSError:
        pass
    return path


def _cleanup_transcript_outputs(output_path: str):
    for suffix in TRANSCRIPT_OUTPUT_EXTENSIONS:
        try:
            os.unlink(f"{output_path}{suffix}")
        except OSError:
            pass


class ASREngine:
    def __init__(self, model_name="mlx-community/Qwen3-ASR-1.7B-8bit",
                 backend="qwen", whisper_model="base"):
        self.model_name = model_name
        self.backend = backend
        self.whisper_model = whisper_model
        self.model = None
        self._loaded = False
        # Serialize concurrent load() calls so a fast double-tap during
        # startup never triggers two parallel HuggingFace downloads.
        self._load_lock = threading.Lock()
        self._load_thread = None
        self._load_thread_lock = threading.Lock()
        # MLX/Metal model evaluation is not safe to run concurrently on the
        # same model object. Streaming preview uses non-blocking acquisition;
        # final transcription blocks until any in-flight preview pass exits.
        self._inference_lock = threading.Lock()

    def acquire_inference(self, blocking: bool = True) -> bool:
        return self._inference_lock.acquire(blocking=blocking)

    def release_inference(self):
        self._inference_lock.release()

    def load(self, progress_callback=None):
        """Load the ASR model. progress_callback(pct, status_str) for download progress."""
        if self._loaded:
            return

        with self._load_lock:
            if self._loaded:  # double-checked under the lock
                return
            if self.backend == "whisper":
                self._load_whisper()
            else:
                self._load_qwen(progress_callback=progress_callback)

    def load_async(self, progress_callback=None):
        """Start a background load if needed and return the worker thread."""
        if self._loaded:
            return None

        with self._load_thread_lock:
            if self._load_thread is not None and self._load_thread.is_alive():
                return self._load_thread

            self._load_thread = threading.Thread(
                target=self.load,
                kwargs={"progress_callback": progress_callback},
                daemon=True,
                name="SpeakTypeASRLoad",
            )
            self._load_thread.start()
            return self._load_thread

    def _load_qwen(self, progress_callback=None):
        """Load Qwen3-ASR via mlx-audio, with optional download progress."""
        from .model_download import is_model_cached, download_model_with_progress

        models_to_try = [self.model_name] + [m for m in ASR_MODELS if m != self.model_name]

        for model_name in models_to_try:
            try:
                # Pre-download with progress if not cached
                if not is_model_cached(model_name) and progress_callback:
                    logger.info(f"Downloading ASR model: {model_name}")
                    download_model_with_progress(model_name, callback=progress_callback)

                logger.info(f"Loading ASR model: {model_name}")
                from mlx_audio.stt.utils import load_model
                self.model = load_model(model_name)
                self.model_name = model_name
                self._loaded = True
                self.backend = "qwen"
                logger.info(f"ASR model loaded: {model_name}")
                return
            except Exception as e:
                logger.warning(f"Failed to load {model_name}: {e}")
                continue

        raise RuntimeError("No Qwen ASR model could be loaded.")

    def _load_whisper(self):
        """Load Whisper model. Tries mlx-whisper first, then openai-whisper."""
        model_size = self.whisper_model if self.whisper_model in WHISPER_MODELS else "base"

        # Try mlx-whisper (Apple Silicon optimized)
        try:
            import mlx_whisper
            logger.info(f"Loading mlx-whisper model: {model_size}")
            # mlx-whisper uses HuggingFace model names
            hf_name = f"mlx-community/whisper-{model_size}-mlx"
            self.model = {"backend": "mlx_whisper", "model_name": hf_name}
            self._loaded = True
            self.backend = "whisper"
            logger.info(f"mlx-whisper loaded: {hf_name}")
            return
        except ImportError:
            logger.debug("mlx-whisper not installed, trying openai-whisper")
        except Exception as e:
            logger.warning(f"mlx-whisper failed: {e}")

        # Try openai-whisper
        try:
            import whisper
            logger.info(f"Loading openai-whisper model: {model_size}")
            self.model = whisper.load_model(model_size)
            self._loaded = True
            self.backend = "whisper"
            logger.info(f"openai-whisper loaded: {model_size}")
            return
        except ImportError:
            logger.warning("Neither mlx-whisper nor openai-whisper installed")
        except Exception as e:
            logger.warning(f"openai-whisper failed: {e}")

        # Fallback to Qwen
        logger.info("Whisper not available, falling back to Qwen ASR")
        self._load_qwen()

    def transcribe(self, audio_input, language: str = "auto") -> str:
        """Transcribe an audio file path or in-memory audio buffer to text."""
        if not self._loaded:
            self.load()

        should_cleanup = isinstance(audio_input, (str, os.PathLike))
        self.acquire_inference(blocking=True)
        try:
            try:
                if self.backend == "whisper":
                    return self._transcribe_whisper(audio_input, language)
                else:
                    return self._transcribe_qwen(audio_input, language)
            finally:
                self.release_inference()
        finally:
            if should_cleanup:
                try:
                    os.unlink(audio_input)
                except OSError:
                    pass

    def _transcribe_qwen(self, audio_input, language: str) -> str:
        """Transcribe using Qwen3-ASR via mlx-audio."""
        from mlx_audio.stt.generate import generate_transcription

        output_path = _make_temp_transcript_output_path()
        kwargs = {
            "model": self.model,
            "audio": audio_input,
            "output_path": output_path,
            "verbose": False,
        }
        if language and language != "auto":
            kwargs["language"] = language

        try:
            result = generate_transcription(**kwargs)
        finally:
            _cleanup_transcript_outputs(output_path)

        if hasattr(result, "text"):
            return result.text.strip()
        elif isinstance(result, str):
            return result.strip()
        elif isinstance(result, dict) and "text" in result:
            return result["text"].strip()
        return str(result).strip()

    def _transcribe_whisper(self, audio_path: str, language: str) -> str:
        """Transcribe using Whisper (mlx-whisper or openai-whisper)."""
        if isinstance(self.model, dict) and self.model.get("backend") == "mlx_whisper":
            return self._transcribe_mlx_whisper(audio_path, language)
        else:
            return self._transcribe_openai_whisper(audio_path, language)

    def _transcribe_mlx_whisper(self, audio_path: str, language: str) -> str:
        """Transcribe using mlx-whisper."""
        import mlx_whisper

        kwargs = {"path_or_hf_repo": self.model["model_name"]}
        if language and language != "auto":
            kwargs["language"] = language

        result = mlx_whisper.transcribe(audio_path, **kwargs)
        return result.get("text", "").strip()

    def _transcribe_openai_whisper(self, audio_path: str, language: str) -> str:
        """Transcribe using openai-whisper."""
        kwargs = {"fp16": False}
        if language and language != "auto":
            kwargs["language"] = language

        result = self.model.transcribe(audio_path, **kwargs)
        return result.get("text", "").strip()

    def get_backend_info(self) -> str:
        """Return a human-readable string about the current ASR backend."""
        if not self._loaded:
            return "Not loaded"
        if self.backend == "whisper":
            if isinstance(self.model, dict):
                return f"mlx-whisper ({self.model.get('model_name', 'unknown')})"
            return f"openai-whisper ({self.whisper_model})"
        return f"Qwen ASR ({self.model_name})"
