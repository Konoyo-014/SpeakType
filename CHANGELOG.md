# Changelog

All notable changes to SpeakType will be documented in this file.

## [2.0.0] - 2025-04-05

### Added
- Streaming real-time transcription preview (floating overlay shows text as you speak)
- Audio input device selection (choose microphone from menubar or settings)
- Toggle dictation mode as alternative to push-to-talk (press once to start, press again to stop)
- Whisper model compatibility (supports openai-whisper and mlx-whisper as ASR backends)
- Custom dictionary and snippets editor UI (menubar > Dictionary & Snippets)
- Dictation statistics panel with per-day activity, top apps, and recent history
- Plugin system with hook-based extensibility (~/.speaktype/plugins/)
- DMG installer build script (build_dmg.sh)
- Homebrew formula for CLI installation
- System service integration via LaunchAgent
- Post-transcription translation with mixed-language support
- Context-aware tone detection (formal/casual/technical based on active app)
- Voice edit commands (select text, say "make it shorter" / "translate to Chinese")
- Snippet library for frequently used phrases
- Native macOS settings window with all options

### Fixed
- LLM prompt injection: transcription content no longer treated as instructions
- Translation now preserves technical terms and handles code-switching
- NSWindow overlay crash on macOS 13+ (disabled window tabbing)
- PortAudio retry mechanism for intermittent device failures
- History file encoding (UTF-8)

### Technical
- ASR: Qwen3-ASR 1.7B via mlx-audio (Apple Silicon native), with Whisper fallback
- LLM: Qwen3.5 via Ollama local inference
- Text insertion: CGEvent + NSPasteboard (no osascript dependency)
- Built with: Python 3.10, rumps, PyObjC, pynput, sounddevice

## [1.0.0] - 2025-03-15

### Added
- Initial release
- Push-to-talk voice dictation
- Qwen3-ASR speech recognition
- LLM text polishing via Ollama
- macOS menubar app with status icons
- Global hotkey listener (right Command key)
- Clipboard-based text insertion
