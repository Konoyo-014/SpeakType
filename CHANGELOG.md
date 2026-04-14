# Changelog

All notable changes to SpeakType will be documented in this file.

## [2.1.2] - 2026-04-14

### Fixed
- Added clearer in-overlay feedback when local Ollama polish/translation is unavailable: SpeakType now explicitly says polish/translation was skipped and raw transcription was inserted.
- Added ASR cold-start and finalization overlay text so slow Qwen3-ASR model loading or live-preview-to-final delays no longer look like a stuck recording.
- Added recorder stop reasons for empty, too-short, and too-quiet audio, with user-facing overlay prompts for fast hotkey releases, missing audio, and weak microphone input.
- Added insertion diagnostics that distinguish verified insertion, unverified-but-sent insertion, PostEvent denial, missing focused fields, and target controls that do not confirm text changes.
- Improved insertion failure notifications with actionable hints for Input Monitoring/PostEvent, focus loss, and non-writable web or app input controls.
- Split startup permission labels so missing PostEvent access is reported as synthetic input permission, not as a generic Accessibility issue.
- Restored the post-authorization restart prompt when permissions are reset during bundled app replacement, including the macOS case where the current process still cannot read new PostEvent grants until restart.
- Separated overlay system notes from dictated text, using smaller secondary status text plus a wider/taller preview window so long prompts and streaming preview text fit more reliably.
- Removed live transcription text from the gray finalization note; that note now stays a short system status message.
- Prevented pending permission refresh state from showing a restart prompt before the user has granted any refreshed permission.
- Moved completed-state system notices such as local LLM fallback and unverified insertion out of the main dictated-text layer; these now render as status notes instead of black transcription text.
- Local Ollama calls now bypass system HTTP/HTTPS proxy settings, so `localhost:11434` health checks and polish requests do not get sent through a proxy such as `127.0.0.1:7897`.
- The local LLM fallback overlay no longer appends raw transcription text after the notice.
- Local LLM fallback notifications now distinguish Ollama not running, missing models, timeouts, and abnormal Ollama responses, with explicit local startup or `ollama pull` guidance.
- The first-run setup wizard now shows whether Ollama is installed but not running, and gives a direct `ollama serve` startup command without adding a new product mode or setting.

### Tests
- Test count grew to 410. New coverage includes ASR cold-start overlay text, audio negative-path reasons, LLM fallback raw-insert notices, Ollama not-running/model-missing/timeout fallback guidance, unverified insertion notices, insertion diagnostics, transcribing-state wait messages, partial permission-grant detection, no-premature-restart prompting while refreshed permissions are still ungranted, local Ollama proxy bypass, and system-notice overlay rendering.

## [2.1.1] - 2026-04-12

### Changed
- Reduced end-to-end dictation latency by overlapping model warmup with recording, reusing in-flight ASR loads, and avoiding unnecessary temporary wav files on the Qwen3-ASR hot path.
- Kept Ollama models warm with async prewarm and `keep_alive`, and merged polish+translation into a single local LLM request when plugins are disabled.
- Moved post-insert clipboard restoration and history persistence off the hot path so insertion returns sooner.
- Strengthened the LLM polish prompt so filler-removal requests are harder for local models to ignore.

### Fixed
- Text polishing now recovers if Ollama starts after SpeakType has already seen it as unavailable. The app retries stale local-LLM failures instead of caching the failure until restart.
- When Ollama is unavailable, SpeakType now shows one clear local-LLM fallback notification and inserts the raw transcription instead of silently appearing to ignore the polish setting.
- Streaming preview display now strips ASR control tokens and invisible control characters before rendering, and uses character wrapping so CJK text, paths, and long technical tokens do not overflow or render oddly.
- Stopping recording no longer waits for streaming preview cleanup, reducing release-to-transcribe delay.
- Qwen3-ASR in-memory audio transcription skips temporary file cleanup paths that only apply to file input.
- Paste-based insertion and replace-selection restore the user's original clipboard asynchronously and avoid overwriting a clipboard the user changed after insertion.
- Fast hotkey release during recorder startup no longer produces impossible multi-year recording durations in logs/history.
- Paste-mode insertion now uses clipboard paste before direct keystroke fallback, improving reliability in embedded editors such as Codex.
- Paste-mode insertion now verifies focused text changes when Accessibility exposes them, retries via System Events if raw Quartz paste is ignored, and reports insertion failure instead of recording false success.
- Paste/keystroke insertion now fails fast with a user-visible notification when macOS PostEvent permission is missing, avoiding false success after permission resets.
- After a permission reset, SpeakType now watches for macOS input permissions becoming granted while the app is still running and shows a restart prompt so the new grants take effect.
- Missing-permission notifications are shorter, so the system notification body fits in the macOS notification UI.
- Streaming preview and final Qwen/MLX transcription now share an inference lock, preventing concurrent Metal evaluation on the same model after hotkey release.
- Qwen streaming preview now uses chunked full-buffer decoding instead of native token-delta streaming, matching the final transcription Unicode path and avoiding transient CJK replacement glyphs in the overlay.
- SpeakType now appends to `~/.speaktype/speaktype.log` instead of overwriting it on restart, preserving pre-crash diagnostics.
- Text polish in auto-language mode now selects a Chinese system prompt for Chinese input and an English system prompt for English input, forbids accidental translation when the translation toggle is off, and retries Chinese polish once after obvious Chinese-to-English drift.
- Insert failures now surface a visible overlay error and user notification instead of silently saving a failed dictation as if it had been inserted.
- Same-version replacement builds now trigger macOS permission reset/re-request via bundled app fingerprint tracking, not only version-number changes.
- Qwen/MLX ASR no longer writes `transcript.txt` into the signed app bundle; mandatory mlx-audio transcript output is redirected to a temporary path and removed.
- The py2app post-build patch now rewrites `site.pyc` when no source `site.py` is emitted, preventing Homebrew `sitecustomize` from breaking bundled-Python smoke tests.

### Tests
- Test count grew to 396. New coverage includes local LLM retry/fallback behavior, language-specific polish prompts, combined polish+translation, streaming stop non-blocking behavior, in-memory ASR input, temporary ASR transcript output cleanup, ASR inference serialization, Qwen chunked preview routing, permission-grant restart prompting, async clipboard restoration, overlay display sanitization/error states, recorder-start timing races, same-version bundle permission refresh, feature-disabled negative paths, insertion verification failures, accidental translation guards, insert failure notifications, and v2.1.1 recording latency regressions.

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
