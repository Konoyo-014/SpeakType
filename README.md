# SpeakType

[中文文档](README_CN.md)

**On-device voice input for macOS.** Hold a key, speak, and polished text appears at the cursor -- in any application.

> Speech recognition via Qwen3-ASR on Apple Silicon, text polishing via Ollama. No cloud APIs, no data leaves your Mac.

## Features

- **Push-to-talk and toggle dictation** -- hold Right Command (configurable) to record; release to transcribe and insert
- **AI text polishing** -- removes filler words, fixes grammar, preserves your tone (powered by local LLM via Ollama)
- **Real-time streaming preview** -- floating overlay shows transcription as you speak
- **Context-aware tone** -- automatically adjusts formality based on the active app (email vs Slack vs code editor)
- **Post-transcription translation** -- translate output to English, Chinese, Japanese, Korean, Spanish, French, or German
- **Voice commands** -- say "new line", "period", "make it shorter", "fix grammar", "translate to Chinese", etc.
- **Whisper compatibility** -- switch between Qwen3-ASR and OpenAI Whisper backends
- **Audio device selection** -- choose your preferred microphone from the menubar
- **Custom dictionary and snippets** -- define words to always recognize correctly; trigger phrases for text expansion
- **Plugin system** -- extend SpeakType with Python plugins (`~/.speaktype/plugins/`)
- **Dictation history and statistics** -- track usage with a built-in analytics panel
- **Native macOS menubar app** -- no Electron, no Dock icon

## Quick Start

### Prerequisites

- macOS 13+ (Ventura or later), Apple Silicon (M1/M2/M3/M4)
- Python 3.10
- Ollama (optional, for text polishing)
- ~4 GB free disk space (for ASR + LLM models)

### Installation

**1. Clone the repository**

```bash
git clone https://github.com/speaktype/speaktype.git
cd speaktype
```

**2. Create a virtual environment and install dependencies**

```bash
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**3. Install Ollama and pull the LLM model (optional, for text polishing)**

```bash
brew install ollama
ollama serve &
ollama pull huihui_ai/qwen3.5-abliterated:9b-Claude
```

Text polishing is optional. Without it, SpeakType inserts raw transcriptions.

**4. Run SpeakType**

```bash
python main.py
```

On first launch, macOS will prompt for:
- **Microphone access** -- for voice recording
- **Accessibility access** -- for text insertion via keyboard simulation

Grant both in **System Settings > Privacy & Security**.

### About the ASR model

The speech recognition model (`mlx-community/Qwen3-ASR-1.7B-8bit`) is downloaded automatically by mlx-audio on the first run. No manual step is needed -- just expect a one-time delay (~2 GB download) the first time you dictate.

### Build .app Bundle (optional)

```bash
source venv/bin/activate
python setup.py py2app --alias
```

The app bundle is created at `dist/SpeakType.app`.

## Usage

### Basic dictation

| Action | How |
|---|---|
| Dictate (push-to-talk) | Hold Right Command, speak, release |
| Dictate (toggle mode) | Press Right Command once to start, again to stop |
| Change hotkey | Preferences > Hotkey |

### Voice commands

**Punctuation and structure** (spoken inline during dictation):

| Command | Result |
|---|---|
| "period" / "full stop" | . |
| "comma" | , |
| "question mark" | ? |
| "exclamation mark" | ! |
| "colon" / "semicolon" | : / ; |
| "new line" / "line break" | line break |
| "new paragraph" | double line break |

Chinese equivalents are also supported: "句号", "逗号", "问号", "换行", "新段落", etc.

**Edit commands** (select text first, then speak the command):

| Command | Effect |
|---|---|
| "make it shorter" | Condense the selected text |
| "make it more formal" | Adjust tone to formal |
| "make it more casual" | Adjust tone to casual |
| "fix grammar" / "fix typos" | Correct errors |
| "translate to [language]" | Translate the selection |
| "summarize this" | Summarize the selection |
| "create a reply" | Draft a reply to the selection |

### Text polishing

When Ollama is running with the LLM model, SpeakType automatically polishes transcriptions: removing filler words, fixing grammar, and adjusting tone based on the active application. Toggle this on/off from the menubar.

### Translation

Enable post-transcription translation from the menubar. Supported targets: English, Chinese, Japanese, Korean, Spanish, French, German. Technical terms are preserved during translation.

### Snippets

Define trigger phrases that expand into saved text. For example, say "my email" to insert your email address. Manage snippets from the menubar: Dictionary & Snippets.

## Configuration

All settings are stored in `~/.speaktype/config.json`. Edit via the Preferences window (Command+,) or directly.

Key options:

| Setting | Default | Description |
|---|---|---|
| `hotkey` | `"right_cmd"` | Push-to-talk key. Options: `right_cmd`, `left_cmd`, `fn`, `right_alt`, `right_ctrl`, `ctrl+shift+space`, `f5`, `f6` |
| `dictation_mode` | `"push_to_talk"` | `"push_to_talk"` or `"toggle"` |
| `asr_backend` | `"qwen"` | `"qwen"` (Qwen3-ASR via mlx-audio) or `"whisper"` (OpenAI Whisper) |
| `asr_model` | `"mlx-community/Qwen3-ASR-1.7B-8bit"` | HuggingFace model ID for Qwen ASR |
| `llm_model` | `"huihui_ai/qwen3.5-abliterated:9b-Claude"` | Ollama model for text polishing |
| `ollama_url` | `"http://localhost:11434"` | Ollama API endpoint |
| `polish_enabled` | `true` | Enable/disable LLM text polishing |
| `language` | `"auto"` | ASR language: `"auto"`, `"en"`, `"zh"`, `"ja"`, `"ko"` |
| `translate_enabled` | `false` | Enable post-transcription translation |
| `translate_target` | `"en"` | Translation target language |
| `streaming_preview` | `false` | Show real-time transcription overlay |
| `voice_commands_enabled` | `true` | Enable voice command processing |
| `context_aware_tone` | `true` | Adjust polishing tone per-app |
| `insert_method` | `"paste"` | `"paste"` (clipboard + Cmd+V) or `"type"` (key-by-key) |
| `plugins_enabled` | `false` | Enable the plugin system |
| `max_recording_seconds` | `360` | Maximum recording duration (6 min) |
| `sound_feedback` | `true` | Play sounds on record start/stop |

### Custom dictionary

Add words that ASR should always recognize correctly. Stored at `~/.speaktype/custom_dictionary.json`. Manage via menubar: Dictionary & Snippets.

## Plugin System

Place `.py` files in `~/.speaktype/plugins/` and enable plugins in Preferences.

### Available hooks

| Hook | Signature | Purpose |
|---|---|---|
| `pre_transcribe` | `(audio_path) -> audio_path` | Modify audio before ASR |
| `post_transcribe` | `(raw_text) -> text` | Modify text after ASR |
| `pre_polish` | `(text, tone) -> (text, tone)` | Modify text/tone before LLM |
| `post_polish` | `(polished_text) -> text` | Modify text after LLM |
| `pre_insert` | `(text) -> text or None` | Modify or skip insertion |
| `post_insert` | `(text) -> None` | Side effects after insertion |
| `on_recording_start` | `() -> None` | Notification: recording started |
| `on_recording_stop` | `() -> None` | Notification: recording stopped |

### Example plugin

```python
# ~/.speaktype/plugins/filler_remover.py
PLUGIN_NAME = "Filler Remover"
PLUGIN_VERSION = "1.0"

def post_transcribe(text):
    """Remove filler words after ASR transcription."""
    for filler in ["um", "uh", "like", "you know"]:
        text = text.replace(f" {filler} ", " ")
    return text
```

Plugins prefixed with `_` (e.g., `_example_plugin.py`) are ignored.

## Architecture

```
Hotkey press
  -> Record audio (sounddevice)
  -> ASR: Qwen3-ASR via mlx-audio  (or Whisper)
  -> Voice command detection / Snippet matching
  -> LLM polish via Ollama (optional)
  -> Translation (optional)
  -> Insert at cursor (CGEvent + NSPasteboard)
```

All processing runs locally on-device. Audio files are deleted immediately after transcription.

**Key components:**

- **ASR**: `mlx-community/Qwen3-ASR-1.7B-8bit` via mlx-audio, with Whisper fallback
- **LLM**: `huihui_ai/qwen3.5-abliterated:9b-Claude` via Ollama (local inference)
- **Text insertion**: CGEvent keyboard simulation + NSPasteboard clipboard
- **UI**: rumps (NSStatusItem menubar), AppKit (native settings windows)

## Troubleshooting

### SpeakType does not appear in the menubar

Make sure you granted Accessibility access. Go to **System Settings > Privacy & Security > Accessibility** and add SpeakType (or Terminal / your IDE if running from source).

### Microphone not working

1. Check **System Settings > Privacy & Security > Microphone** and ensure SpeakType (or Terminal) is allowed.
2. Use "Test Microphone" from the menubar to verify the mic is capturing audio.
3. Try selecting a specific audio device from the menubar instead of "System Default".

### ASR model download fails

The model is downloaded from HuggingFace. If you are behind a proxy, set `HTTP_PROXY` and `HTTPS_PROXY` environment variables before running.

### Text polishing not working

1. Verify Ollama is running: `curl http://localhost:11434/api/tags`
2. Verify the model is pulled: `ollama list` should show `huihui_ai/qwen3.5-abliterated:9b-Claude`
3. If not, run: `ollama pull huihui_ai/qwen3.5-abliterated:9b-Claude`

### Text not inserted into application

Some apps block simulated keyboard input. Try switching `insert_method` to `"type"` in the config, or grant Accessibility permissions to the target application.

### Log file

Logs are written to `~/.speaktype/speaktype.log` on each run. Check this for detailed error messages.

## Development

```bash
# Run with debug output
source venv/bin/activate
python main.py  # logs to ~/.speaktype/speaktype.log

# Quick pipeline test (records 3s, transcribes, polishes)
python main.py --test

# Run tests
python -m pytest tests/ -v

# Build .app bundle
python setup.py py2app --alias
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines, the full plugin hook API, and development setup.

## License

[MIT](LICENSE)
