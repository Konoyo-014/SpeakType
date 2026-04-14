# SpeakType

[中文文档](README_CN.md)

**On-device voice input for macOS.** Hold a key, speak, and polished text appears at the cursor -- in any application.

> Speech recognition via Qwen3-ASR on Apple Silicon, text polishing via Ollama. No cloud APIs, no data leaves your Mac.

## Features

- **Push-to-talk and toggle dictation** -- hold Right Command (configurable) to record; release to transcribe and insert
- **AI text polishing** -- removes filler words, fixes grammar, preserves your tone (powered by local LLM via Ollama)
- **Real-time streaming preview** -- floating overlay shows transcription as you speak
- **Adaptive Whisper Mode** -- automatically detects very low-volume speech and boosts it locally during recording, without exposing a manual toggle
- **Context-aware tone** -- automatically adjusts formality based on the active app (email vs Slack vs code editor)
- **Post-transcription translation** -- translate output to English, Chinese, Japanese, Korean, Spanish, French, or German
- **Voice commands** -- say "new line", "period", "make it shorter", "fix grammar", "translate to Chinese", etc.
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
git clone https://github.com/Konoyo-014/SpeakType.git
cd SpeakType
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
brew services start ollama
ollama pull huihui_ai/qwen3.5-abliterated:9b-Claude
```

Text polishing is optional. Without it, SpeakType inserts raw transcriptions.

Ollama must be running for SpeakType to polish or translate text. The easiest command-line setup is `brew services start ollama`, which starts Ollama as a macOS background service; you do not need to keep a Terminal window open after that. Check it with:

```bash
brew services list | grep ollama
curl http://localhost:11434/api/tags
```

If you prefer the Ollama desktop app, install and open Ollama.app instead; SpeakType connects to the same local server at `http://localhost:11434`. If you only run `ollama serve` in a Terminal window, that is a temporary foreground server: closing that Terminal stops Ollama, and SpeakType will insert raw transcription until Ollama is started again.

**4. Run SpeakType**

```bash
python main.py
```

On first launch, macOS will prompt for:
- **Microphone access** -- for voice recording
- **Accessibility access** -- for text insertion via keyboard simulation
- **Input Monitoring** -- for the global push-to-talk hotkey

Grant all three in **System Settings > Privacy & Security**. If you are running from source, macOS may ask you to authorize Terminal, iTerm, or your IDE instead of SpeakType.app.

### About the ASR model

The speech recognition model (`mlx-community/Qwen3-ASR-1.7B-8bit`) is downloaded automatically by mlx-audio from HuggingFace on the first run (~2 GB download).

**Users in mainland China:** HuggingFace is not accessible. Set the mirror before launching:

```bash
export HF_ENDPOINT=https://hf-mirror.com
python main.py
```

Add to `~/.zshrc` to persist:

```bash
echo 'export HF_ENDPOINT=https://hf-mirror.com' >> ~/.zshrc
```

### Build .app Bundle (optional)

```bash
./build_dmg.sh --app
```

The standalone workspace bundle is created at `dist/SpeakType.app`. For a release-ready installer, run `./build_dmg.sh` and distribute the generated DMG instead. The DMG path uses a cleaned, re-signed temporary copy so Desktop/iCloud file-provider metadata does not invalidate the bundle signature.

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

### Ollama startup options

SpeakType never sends dictated audio, raw transcription, or polished text to external APIs. Ollama is used only as a local server on your Mac, normally at `http://localhost:11434`.

For Homebrew installs, use `brew services start ollama` to keep Ollama running in the background after login. Use `brew services list | grep ollama` to verify the service state, and `brew services stop ollama` if you want to turn it off.

For the desktop app install, open Ollama.app and leave it running in the menu bar. This is usually the simplest choice for non-terminal users.

For temporary testing, `ollama serve` is fine, but it runs in the foreground. If you close that Terminal window, Ollama stops. SpeakType will keep dictation working, but text polishing and translation will be skipped and raw transcription will be inserted.

After Ollama is running, install or verify the model:

```bash
ollama list
ollama pull huihui_ai/qwen3.5-abliterated:9b-Claude
```

### Translation

Enable post-transcription translation from the menubar. Supported targets: English, Chinese, Japanese, Korean, Spanish, French, German. Technical terms are preserved during translation.

### Snippets

Define trigger phrases that expand into saved text. For example, say "my email" to insert your email address. Snippet bodies support `{date}`, `{time}`, `{datetime}`, `{clipboard}`, and `{env:NAME}`. Sensitive placeholders like `{clipboard}` and `{env:...}` only expand on exact trigger matches, so fuzzy matching cannot accidentally inject local secrets. Manage snippets from the menubar: Dictionary & Snippets.

## Configuration

All settings are stored in `~/.speaktype/config.json`. Edit via the Preferences window (Command+,) or directly.

Key options:

| Setting | Default | Description |
|---|---|---|
| `hotkey` | `"right_cmd"` | Push-to-talk key. Options: `right_cmd`, `left_cmd`, `fn`, `right_alt`, `right_ctrl`, `ctrl+shift+space`, `f5`, `f6` |
| `dictation_mode` | `"push_to_talk"` | `"push_to_talk"` or `"toggle"` |
| `asr_backend` | `"qwen"` | Legacy compatibility key. v2.1 always runs Qwen3-ASR and normalizes old Whisper configs back to `qwen` |
| `asr_model` | `"mlx-community/Qwen3-ASR-1.7B-8bit"` | HuggingFace model ID for Qwen ASR |
| `llm_model` | `"huihui_ai/qwen3.5-abliterated:9b-Claude"` | Ollama model for text polishing |
| `ollama_url` | `"http://localhost:11434"` | Ollama API endpoint |
| `polish_enabled` | `true` | Enable/disable LLM text polishing |
| `language` | `"auto"` | ASR language: `"auto"`, `"en"`, `"zh"`, `"ja"`, `"ko"` |
| `translate_enabled` | `false` | Enable post-transcription translation |
| `translate_target` | `"en"` | Translation target language |
| `streaming_preview` | `true` | Show real-time transcription overlay |
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
  -> ASR: Qwen3-ASR via mlx-audio
  -> Voice command detection / Snippet matching
  -> LLM polish via Ollama (optional)
  -> Translation (optional)
  -> Insert at cursor (CGEvent + NSPasteboard)
```

All processing runs locally on-device. Audio files are deleted immediately after transcription.

**Key components:**

- **ASR**: `mlx-community/Qwen3-ASR-1.7B-8bit` via mlx-audio
- **LLM**: `huihui_ai/qwen3.5-abliterated:9b-Claude` via Ollama (local inference)
- **Text insertion**: CGEvent keyboard simulation + NSPasteboard clipboard
- **UI**: rumps (NSStatusItem menubar), AppKit (native settings windows)

## Troubleshooting

### SpeakType does not appear in the menubar

Make sure you granted both **Accessibility** and **Input Monitoring**. Go to **System Settings > Privacy & Security** and allow SpeakType (or Terminal / your IDE if running from source) in both sections.

### Microphone not working

1. Check **System Settings > Privacy & Security > Microphone** and ensure SpeakType (or Terminal) is allowed.
2. Use "Test Microphone" from the menubar to verify the mic is capturing audio.
3. Try selecting a specific audio device from the menubar instead of "System Default".

### ASR model download fails

The model is downloaded from HuggingFace. If you are behind a proxy, set `HTTP_PROXY` and `HTTPS_PROXY` environment variables before running.

### Text polishing not working

First verify that Ollama is running:

```bash
curl http://localhost:11434/api/tags
```

If that command cannot connect, start Ollama with one of these methods:

```bash
# Background service, recommended for Homebrew installs
brew services start ollama

# Temporary foreground server, stops when this Terminal closes
ollama serve
```

Then verify the model is installed:

```bash
ollama list
ollama pull huihui_ai/qwen3.5-abliterated:9b-Claude
```

If SpeakType says polishing was skipped, dictation still worked locally; it inserted the raw transcription because Ollama was not available for the optional local LLM step.

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
./build_dmg.sh --app

# Build the release DMG
./build_dmg.sh
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines, the full plugin hook API, and development setup.

## License

[MIT](LICENSE)
