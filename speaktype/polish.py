"""Text polishing engine using Ollama (Qwen3.5)."""

import json
import logging
import requests

logger = logging.getLogger("speaktype.polish")


class PolishEngine:
    def __init__(self, model="qwen3.5:4b", ollama_url="http://localhost:11434"):
        self.model = model
        self.ollama_url = ollama_url.rstrip("/")
        self._available = None

    def check_available(self) -> bool:
        """Check if Ollama is running and the model is available."""
        try:
            resp = requests.get(f"{self.ollama_url}/api/tags", timeout=3)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                base_name = self.model.split(":")[0]
                self._available = any(base_name in name for name in model_names)
                if not self._available:
                    logger.warning(
                        f"Model {self.model} not found. Available: {model_names}"
                    )
                return self._available
        except requests.ConnectionError:
            logger.warning("Ollama is not running. Start with: ollama serve")
            self._available = False
        except Exception as e:
            logger.warning(f"Ollama check failed: {e}")
            self._available = False
        return False

    def _chat(self, messages: list, max_tokens: int = 1024) -> str:
        """Send a chat request to Ollama and return the response text."""
        try:
            resp = requests.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "think": False,  # Disable thinking mode for fast, direct responses
                    "options": {
                        "temperature": 0.3,
                        "top_p": 0.9,
                        "num_predict": max_tokens,
                    },
                },
                timeout=120,
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data.get("message", {}).get("content", "").strip()
                return content
            else:
                logger.warning(f"Ollama returned status {resp.status_code}")
        except requests.Timeout:
            logger.warning("Ollama request timed out")
        except Exception as e:
            logger.error(f"Ollama request failed: {e}")
        return ""

    def polish(self, raw_text: str, tone: str = "neutral", language: str = "auto") -> str:
        """Polish raw transcription text using LLM."""
        if not raw_text.strip():
            return raw_text

        if self._available is None:
            self.check_available()
        if not self._available:
            return raw_text

        tone_instruction = {
            "formal": "Use a professional, formal tone.",
            "casual": "Use a relaxed, conversational tone.",
            "technical": "Preserve technical terms. Keep it precise.",
            "neutral": "Use a clear, natural tone.",
        }.get(tone, "Use a clear, natural tone.")

        lang_note = ""
        if language and language != "auto":
            lang_map = {"zh": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean"}
            lang_note = f" Output in {lang_map.get(language, language)}."

        messages = [
            {
                "role": "system",
                "content": f"You are a voice-to-text post-processor. Clean up speech transcriptions into well-written text. {tone_instruction}{lang_note}\n\nRules:\n- Remove filler words (um, uh, like, you know, 嗯, 那个, 就是)\n- Fix grammar and punctuation\n- Keep only the final intended version when the speaker self-corrects\n- Remove unnecessary repetitions\n- Preserve the speaker's intended meaning exactly\n- Do NOT add explanations, options, or commentary\n- Return ONLY the cleaned text, nothing else"
            },
            {
                "role": "user",
                "content": raw_text,
            },
        ]

        result = self._chat(messages, max_tokens=max(len(raw_text) * 2, 256))
        return result if result else raw_text

    def edit_text(self, command: str, selected_text: str, tone: str = "neutral") -> str:
        """Process a voice edit command on selected text."""
        if self._available is None:
            self.check_available()
        if not self._available:
            return selected_text

        messages = [
            {
                "role": "system",
                "content": "You are a text editing assistant. Apply the user's voice command to modify the given text. Return ONLY the modified text, no explanations."
            },
            {
                "role": "user",
                "content": f"Text to modify:\n{selected_text}\n\nCommand: {command}",
            },
        ]

        result = self._chat(messages, max_tokens=max(len(selected_text) * 3, 512))
        return result if result else selected_text
