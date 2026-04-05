"""ASR engine with Qwen3-ASR (mlx-audio) and Whisper compatibility."""

import os
import logging

logger = logging.getLogger("speaktype.asr")

ASR_MODELS = [
    "mlx-community/Qwen3-ASR-1.7B-8bit",
    "mlx-community/Qwen3-ASR-0.6B-4bit",
]

WHISPER_MODELS = ["tiny", "base", "small", "medium", "large"]


class ASREngine:
    def __init__(self, model_name="mlx-community/Qwen3-ASR-1.7B-8bit",
                 backend="qwen", whisper_model="base"):
        self.model_name = model_name
        self.backend = backend
        self.whisper_model = whisper_model
        self.model = None
        self._loaded = False

    def load(self):
        if self._loaded:
            return

        if self.backend == "whisper":
            self._load_whisper()
        else:
            self._load_qwen()

    def _load_qwen(self):
        """Load Qwen3-ASR via mlx-audio."""
        models_to_try = [self.model_name] + [m for m in ASR_MODELS if m != self.model_name]

        for model_name in models_to_try:
            try:
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

    def transcribe(self, audio_path: str, language: str = "auto") -> str:
        """Transcribe an audio file to text."""
        if not self._loaded:
            self.load()

        try:
            if self.backend == "whisper":
                return self._transcribe_whisper(audio_path, language)
            else:
                return self._transcribe_qwen(audio_path, language)
        finally:
            try:
                os.unlink(audio_path)
            except OSError:
                pass

    def _transcribe_qwen(self, audio_path: str, language: str) -> str:
        """Transcribe using Qwen3-ASR via mlx-audio."""
        from mlx_audio.stt.generate import generate_transcription

        kwargs = {
            "model": self.model,
            "audio": audio_path,
            "verbose": False,
        }
        if language and language != "auto":
            kwargs["language"] = language

        result = generate_transcription(**kwargs)

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
