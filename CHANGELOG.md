# Changelog

All notable changes to SpeakType will be documented in this file.

## [2.1.0] - 2026-04-06

### Added
- **Unified status overlay** — the recording dot, audio-level visualization, and streaming text preview are now a single floating window with a four-phase state machine: recording → transcribing → polishing → done. Color-coded state indicator, subtle whisper marker, and auto-hide on completion.
- **Adaptive Whisper Mode** — real-time detector watches the audio stream during recording. When it spots a sustained low-volume run, it transparently boosts gain by 5x so the ASR still produces a usable transcript. Hysteresis prevents flapping; a subtle 🌙 indicator on the overlay tells you it kicked in.
- **Real version check** — `Check for Updates` now hits the GitHub Releases API, compares semver, and offers to open the release page when a newer build is available. Network errors are surfaced as a non-fatal notification.
- **Scene-based polish prompts** — the LLM polish step now uses per-application scene templates (email / chat / code / notes / default) on top of the existing tone hint, so the same dictation reads differently in Mail vs Slack vs VS Code. Templates can be overridden via `config["scene_prompts"]`.
- **Enhanced voice edit commands** — added bullet/list/headline/expand/simplify/proofread variants in English and Chinese. New "undo last dictation" voice command (`undo that`, `scratch that`, `撤销刚才`) deletes the most recent insertion via backspace events.
- **Smarter snippets** — fuzzy matching now tolerates punctuation/whitespace differences (`我的邮箱。` matches `我的邮箱`) and one-edit-distance for short triggers. Snippet bodies support `{date}`, `{time}`, `{datetime}`, `{clipboard}`, and `{env:NAME}` placeholders that expand at insertion time, with sensitive placeholders restricted to exact trigger matches.
- **History export** — Stats window has a new Export button that saves the full dictation history as TXT, Markdown, CSV, or JSON via NSSavePanel.
- **Correction store** — new dictionary section lets you teach SpeakType "when you hear X, write Y". Replacements are word-boundary, case-insensitive, applied right after ASR returns.
- **Configurable hard recording cap** — the existing `max_recording_seconds` setting (default 6 minutes) now actually enforces itself via an audio-thread watchdog that triggers a clean stop.

### Changed
- SpeakType v2.1 now **locks ASR to Qwen3-ASR**. Legacy `asr_backend=whisper` configs are migrated back to `qwen` on load/save, and the app no longer advertises Whisper as a supported release configuration.
- The `auto_punctuation` and `filler_removal` config flags are now wired into the polish prompt; they previously had no effect.
- Streaming preview defaults to enabled and is exposed as a checkbox in Settings → Features.
- ASREngine.load() is now thread-safe — concurrent calls during startup no longer risk a double download.
- `context.get_selected_text()` always restores the user's clipboard, even on errors (was leaking the user's clipboard on exceptions).
- Quitting now waits up to 2 seconds for any in-flight transcription/polish thread before tearing down, instead of yanking the rug out.

### Fixed
- Voice undo now only deletes text in the same frontmost app that received the last insertion, and snippet/edit insertions are tracked so undo length stays correct.
- Microphone-open failures no longer leave the overlay stuck in `Listening…`; the app now only enters recording UI after the recorder starts successfully.
- Chunked streaming preview no longer crashes on legacy Whisper backends; unsupported backends skip the mlx-audio chunked path instead of dereferencing the wrong model type.
- `rumps.Timer` level monitoring is now dispatched onto the main thread, and auto-stop on `max_recording_seconds` is idempotent even when it races with hotkey release.
- `replace_selection()` now restores the user's clipboard with `try/finally`, matching the safety guarantees already used by selection reads.
- `StatusOverlay` ignores delayed reset callbacks from an earlier hide once a new visible session has already started.
- `WhisperDetector` now resets its quiet/loud streak counters on silence so whisper mode does not get incorrectly latched across gaps.
- Release DMG packaging now rebuilds a clean ad-hoc signed bundle outside Desktop-backed workspace paths so Finder/File Provider metadata does not invalidate the installer build.

### Removed
- `speaktype/overlay.py` — its functionality is merged into the new `status_overlay.py`.
- The old `streaming.StreamingPreviewWindow` class — replaced by the unified status overlay; `StreamingTranscriber` is now UI-agnostic and pushes partial text into a callback.

### Tests
- Test count grew from 90 → 323. New suites cover: status overlay state transitions, streaming transcriber callback chain, whisper detector hysteresis & gain, history export rendering, snippet fuzzy matching & variable expansion, version checker (offline + error paths), context scene mapping, polish prompt flag wiring, ASR concurrency, audio recorder whisper integration, voice action commands, correction storage, recording lifecycle regressions, and config migration hardening.

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
