"""ASR engine using Qwen3-ASR via mlx-audio."""

import os
import logging

logger = logging.getLogger("speaktype.asr")

ASR_MODELS = [
    "mlx-community/Qwen3-ASR-1.7B-8bit",
    "mlx-community/Qwen3-ASR-0.6B-4bit",
]


class ASREngine:
    def __init__(self, model_name="mlx-community/Qwen3-ASR-1.7B-8bit"):
        self.model_name = model_name
        self.model = None
        self._loaded = False

    def load(self):
        if self._loaded:
            return

        models_to_try = [self.model_name] + [m for m in ASR_MODELS if m != self.model_name]

        for model_name in models_to_try:
            try:
                logger.info(f"Loading ASR model: {model_name}")
                from mlx_audio.stt.utils import load_model
                self.model = load_model(model_name)
                self.model_name = model_name
                self._loaded = True
                logger.info(f"ASR model loaded: {model_name}")
                return
            except Exception as e:
                logger.warning(f"Failed to load {model_name}: {e}")
                continue

        raise RuntimeError("No ASR model could be loaded.")

    def transcribe(self, audio_path: str, language: str = "auto") -> str:
        """Transcribe an audio file to text."""
        if not self._loaded:
            self.load()

        try:
            from mlx_audio.stt.generate import generate_transcription

            kwargs = {
                "model": self.model,
                "audio": audio_path,
                "verbose": False,
            }

            if language and language != "auto":
                kwargs["language"] = language

            result = generate_transcription(**kwargs)

            try:
                os.unlink(audio_path)
            except OSError:
                pass

            if hasattr(result, "text"):
                return result.text.strip()
            elif isinstance(result, str):
                return result.strip()
            elif isinstance(result, dict) and "text" in result:
                return result["text"].strip()
            else:
                return str(result).strip()

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            try:
                os.unlink(audio_path)
            except OSError:
                pass
            raise
