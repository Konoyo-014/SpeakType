# Contributing to SpeakType

Thank you for your interest in contributing to SpeakType! This guide will help you get started.

## Development Setup

### Prerequisites
- macOS 13+ (Ventura or later)
- Python 3.10 (not 3.11+, due to mlx-audio compatibility)
- Apple Silicon Mac (M1/M2/M3/M4) for mlx-audio acceleration
- Ollama (for LLM text polishing)

### Quick Start

```bash
# Clone the repo
git clone https://github.com/speaktype/speaktype.git
cd speaktype

# Run the setup script (creates venv, installs deps, downloads models)
./setup.sh

# Start the app
./start.sh

# Or run directly
./venv/bin/python3 main.py
```

### Running Tests

```bash
./venv/bin/python3 -m pytest tests/ -v
```

### Building the App

```bash
# Build a standalone .app bundle
./build_dmg.sh --app

# Build DMG installer
./build_dmg.sh

# Build a uniquely versioned debug bundle
SPEAKTYPE_BUILD_VERSION=2.0.1d1 ./build_dmg.sh --app
```

## Project Structure

```
speaktype/
  app.py              # Main menubar application (rumps)
  asr.py              # ASR engine (Qwen3-ASR + Whisper)
  audio.py            # Microphone recording (sounddevice)
  polish.py           # LLM text polishing (Ollama)
  inserter.py         # Text insertion (CGEvent + NSPasteboard)
  hotkey.py           # Global hotkey listener (pynput)
  streaming.py        # Streaming transcription preview
  overlay.py          # Recording indicator overlay
  settings_window.py  # Native settings UI (PyObjC)
  dict_window.py      # Dictionary & snippets editor
  stats_window.py     # Statistics panel
  devices.py          # Audio device enumeration
  plugins.py          # Plugin system
  config.py           # Configuration management
  context.py          # Active app detection
  commands.py         # Voice command processing
  snippets.py         # Snippet library
  history.py          # Dictation history
```

## How to Contribute

### Reporting Bugs
- Open a GitHub issue with reproduction steps
- Include your macOS version, Python version, and chip (M1/M2/etc.)
- Attach `~/.speaktype/speaktype.log` if relevant

### Submitting Changes
1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes
4. Run tests: `python3 -m pytest tests/ -v`
5. Commit with a descriptive message
6. Push and open a pull request

### Writing Plugins
Plugins are Python files placed in `~/.speaktype/plugins/`. See the example plugin generated on first run for the hook API. Available hooks:

- `pre_transcribe(audio_path)` - Modify audio before ASR
- `post_transcribe(raw_text)` - Modify raw transcription
- `pre_polish(text, tone)` - Modify text before LLM polishing
- `post_polish(polished_text)` - Modify polished output
- `pre_insert(text)` - Modify text before insertion (return None to skip)
- `post_insert(text)` - Side effects after insertion
- `on_recording_start()` - Notification when recording begins
- `on_recording_stop()` - Notification when recording ends

### Code Style
- Follow existing patterns in the codebase
- Use type hints where they improve clarity
- Keep modules focused and imports clean
- Test any new functionality

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
