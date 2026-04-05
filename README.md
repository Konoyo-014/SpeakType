# SpeakType

**AI-powered voice input method for macOS.** Hold a key, speak, and your words appear as polished text at the cursor — in any application.

SpeakType runs entirely on-device: speech recognition via [Qwen3-ASR](https://huggingface.co/mlx-community/Qwen3-ASR-1.7B-8bit) on Apple Silicon, text polishing via [Qwen3.5](https://ollama.com/) through Ollama. No cloud APIs, no data leaves your Mac.

## Features

- **Push-to-talk & toggle dictation** — hold Right Command (or configure any key) to record; release to transcribe and insert
- **AI text polishing** — removes filler words, fixes grammar, respects your tone
- **Real-time streaming preview** — see transcription appear in a floating overlay as you speak
- **Context-aware tone** — automatically adjusts formality based on the active app (email vs Slack vs code editor)
- **Post-transcription translation** — translate output to any of 10 languages, with technical term preservation
- **Voice commands** — say "new line", "period", or "make it shorter" to control formatting and editing
- **Whisper compatibility** — switch between Qwen3-ASR and OpenAI Whisper backends
- **Audio device selection** — choose your preferred microphone from the menubar
- **Custom dictionary & snippets** — define words to always recognize correctly, and trigger phrases for quick text expansion
- **Plugin system** — extend SpeakType with Python plugins (~/.speaktype/plugins/)
- **Dictation statistics** — track your usage with a built-in analytics panel
- **Native macOS UI** — menubar app with a settings window, no Electron

## Requirements

- macOS 13+ (Ventura or later)
- Apple Silicon Mac (M1/M2/M3/M4) — required for mlx-audio acceleration
- Python 3.10
- ~4 GB disk space (ASR model + LLM model)

## Installation

### Quick Start (from source)

```bash
git clone https://github.com/speaktype/speaktype.git
cd speaktype
./setup.sh    # Creates venv, installs dependencies, downloads ASR model
./start.sh    # Starts Ollama + SpeakType
```

### DMG Installer

Download the latest `.dmg` from [Releases](https://github.com/speaktype/speaktype/releases), drag `SpeakType.app` to `/Applications`, then launch from Spotlight.

### Homebrew (CLI)

```bash
brew install speaktype
speaktype
```

### Grant Permissions

On first launch, macOS will ask for:
1. **Microphone access** — for voice recording
2. **Accessibility access** — for text insertion via keyboard simulation

Grant these in: **System Settings > Privacy & Security**

### Set Up Ollama (for text polishing)

```bash
brew install ollama
ollama serve &
ollama pull huihui_ai/qwen3.5-abliterated:9b-Claude
```

Text polishing is optional — SpeakType works without it, inserting raw transcriptions.

## Usage

| Action | How |
|--------|-----|
| **Dictate** | Hold Right Command, speak, release |
| **Toggle mode** | Press Right Command once to start, again to stop |
| **Insert punctuation** | Say "period", "comma", "question mark", "new line" |
| **Edit selected text** | Select text, then say "make it shorter" / "fix grammar" / "translate to Chinese" |
| **Use a snippet** | Say the trigger phrase (e.g., "my email") to insert saved text |
| **Open settings** | Click the menubar icon > Preferences (or Command+,) |
| **View stats** | Click the menubar icon > History & Stats |
| **Manage dictionary** | Click the menubar icon > Dictionary & Snippets |

## Configuration

All settings are stored in `~/.speaktype/config.json`. Edit via the Settings window or directly:

```json
{
  "hotkey": "right_cmd",
  "dictation_mode": "push_to_talk",
  "asr_backend": "qwen",
  "language": "auto",
  "polish_enabled": true,
  "streaming_preview": false,
  "translate_enabled": false,
  "translate_target": "en",
  "plugins_enabled": false
}
```

## Plugins

Place `.py` files in `~/.speaktype/plugins/` to extend SpeakType. Available hooks:

```python
# my_plugin.py
PLUGIN_NAME = "My Plugin"

def post_transcribe(text):
    """Modify text after ASR, before polishing."""
    return text.replace("um", "")
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full hook API.

## Architecture

```
Hotkey press → Record audio → ASR (Qwen3/Whisper)
    → Voice commands / Snippets
    → LLM polish (Ollama)
    → Translation (optional)
    → Insert at cursor (CGEvent + NSPasteboard)
```

All processing is local. Audio files are deleted immediately after transcription.

## Development

```bash
# Run tests
./venv/bin/python3 -m pytest tests/ -v

# Run with debug output
./venv/bin/python3 main.py  # logs to ~/.speaktype/speaktype.log

# Build .app bundle
./venv/bin/python3 setup.py py2app --alias

# Build DMG installer
./build_dmg.sh
```

## License

[MIT](LICENSE)
