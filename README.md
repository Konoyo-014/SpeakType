# SpeakType

[中文文档](README_CN.md)

Hold Right Command, speak, and release to insert text at the cursor. SpeakType runs Qwen3-ASR on your Mac and uses a local Ollama model for optional polishing and translation.

## Install

Requires **macOS 14 or later and an Apple Silicon Mac**. The DMG includes the Python runtime and application dependencies.

1. Open the [latest GitHub release](https://github.com/Konoyo-014/SpeakType/releases/latest) and download the `SpeakType-*.dmg` attachment.
2. Open the DMG, drag **SpeakType** into **Applications**, and launch it from Applications.
3. Follow the setup window to prepare the speech recognition model. The first download requires an internet connection.
4. In **System Settings > Privacy & Security**, allow SpeakType to use **Microphone**, **Accessibility**, and **Input Monitoring** when requested. Restart SpeakType if it prompts you after a permission change.
5. Click an editable text field, hold **Right Command**, speak, and release.

SpeakType appears in the menu bar. Click its microphone icon to change settings or open **Local Diagnostics**. If macOS requests approval to open the downloaded app, use **System Settings > Privacy & Security > Open Anyway** for SpeakType.

### Optional polishing and translation

Open your local Ollama app and install the model selected in **Preferences > AI Models**. The default model is:

```bash
ollama pull huihui_ai/qwen3.5-abliterated:9b-Claude
```

For a Homebrew installation, run `brew services start ollama` to keep the local service running in the background. `ollama serve` runs a foreground service that stops when its Terminal window closes. SpeakType connects to `http://localhost:11434` by default.

When Ollama is unavailable, SpeakType inserts the transcription and displays a message explaining that polishing or translation was skipped. **Local Diagnostics** shows the configured model and the command needed to install it.

Setup and diagnostics check the configured Ollama service and exact model tag. The ASR download is ready after its configuration, tokenizer, and weight files pass the cache check. Skipping an unavailable optional Ollama model disables polishing and translation in the saved settings.

## Dictate and recover text

| Action | How |
|---|---|
| Dictate while holding a key | Hold Right Command, speak, release |
| Toggle recording | Select toggle mode in Preferences; press once to start and again to stop |
| Change the hotkey or microphone | Use Preferences or the microphone submenu |
| Copy the most recent result | Menu bar > Copy Last Dictation |
| Insert the most recent result again | Focus the target text field, then choose Insert Last Dictation Again |
| Find an earlier result | Menu bar > Dictation History |

**Dictation History** searches original transcription, final text, app name, time, and insertion result. Select a row to read the complete original and final text, then use **Copy Original** or **Copy Final Text**. The window also offers refresh and export to TXT, Markdown, CSV, or JSON. Usage totals are available separately under **Dictation Statistics**.

With **Save Dictation History** enabled, SpeakType saves the original transcription before local model processing and saves the final text before attempting insertion. History distinguishes these results:

| Result | Meaning |
|---|---|
| Unconfirmed | Text is saved; insertion has not been confirmed |
| Inserted | Accessibility reported the inserted text in the target field |
| Sent, unverified | Input was sent, but the target did not expose enough information to verify it |
| Failed | SpeakType could not complete insertion |

For a failed insertion, copy the saved result from history or use **Copy Last Dictation**. For **Sent, unverified**, check the destination before inserting again to avoid duplicate text. When history is disabled, the most recent result remains available for copying or insertion during the current session.

## Voice commands

Enable **Voice Commands** in the menu to convert spoken punctuation and apply editing commands.

| Spoken command | Output |
|---|---|
| `period`, `full stop`, `comma`, `question mark` | `.`, `.`, `,`, `?` |
| `exclamation mark`, `colon`, `semicolon` | `!`, `:`, `;` |
| `open quote` / `close quote` | Double quotes |
| `open single quote` / `close single quote` | Single quotes |
| `open parenthesis` / `close parenthesis` | Parentheses |
| `open square bracket` / `close square bracket` | Square brackets |
| `new line`, `new paragraph`, `tab` | Line break, paragraph break, tab |

You can speak adjacent closing punctuation: `open quote hello close quote period` becomes `"hello".`; `hello open parenthesis world close parenthesis period` becomes `hello (world).` Chinese commands include `左引号` / `右引号`, `左括号` / `右括号`, `左书名号` / `右书名号`, `句号`, `换行`, and `新段落`.

To edit a selection, select the text and dictate a complete command such as `make it shorter`, `make it more formal`, `fix grammar`, `translate to Chinese`, `summarize this`, or `create a reply`. Editing uses the local Ollama model.

`undo that` and `scratch that` remove a verified insertion while the same input field, complete text, and cursor position remain unchanged. Undo selects the exact inserted span through Accessibility and verifies its removal, including text containing emoji. Moving the cursor, selecting other text, editing the document, switching documents, or using a target without readable Accessibility text leaves the current text unchanged.

## Vocabulary and shortcuts

**Adaptive Hotwords** learns reusable terms from immediate edits to text inserted by SpeakType. It observes the recently inserted span in the focused field for a short period. App changes end observation; password fields, unreadable inputs, unrelated typing, and simple appended text are excluded. The local Ollama model proposes terminology, and validation checks each proposal against the edited text before saving it in `~/.speaktype/hotwords.json`.

Later dictations receive a compact set of relevant terms selected by app, scene, language, confidence, and recent use. Qwen3-ASR receives this context when its installed API supports it; local polishing and translation also receive the terms. Open **Adaptive Hotwords** to inspect learned terms and their active state.

Use **Dictionary & Snippets** to manage custom vocabulary, corrections, and phrases that expand into saved text. Corrections preserve literal backslashes in replacement text and apply longer matching terms first. Snippets support `{date}`, `{time}`, `{datetime}`, `{clipboard}`, and `{env:NAME}`. Clipboard and environment placeholders expand only for exact trigger matches.

## Other controls

- **Polish Text** removes filler words, corrects grammar, and uses the current app to select a tone. Its prompts preserve the transcription's language, and retries retain the requested language. The feature requires the configured local Ollama model.
- **Translate After Transcription** supports English, Chinese, Japanese, Korean, Spanish, French, and German.
- **Streaming preview** shows recognition progress while recording. The final transcription supplies the inserted text.
- **Adaptive low-volume recording** detects quiet speech and increases recording gain automatically.
- **Local Diagnostics** checks input permissions, microphones, model availability, Ollama, hotwords, and focused-input readiness. It provides commands and local repair steps.
- **Preferences** includes Chinese and English UI choices, push-to-talk or toggle recording, microphone selection, and a six-minute default recording limit.

## What's new in v2.3.0

- Searchable native dictation history with full original/final text, copy buttons, insertion results, refresh, and export.
- Original transcription retained before polishing; final text saved before insertion; menu actions to copy or insert the latest result again.
- Consecutive spoken quotation marks, brackets, and punctuation in English and Chinese.
- Safe voice undo checks the input field, complete text, and UTF-16 cursor range before selecting and removing the verified insertion.
- Language-preserving polishing, actual microphone authorization, exact Ollama model tags, and ASR-cache validation before download completion.
- Clipboard restoration preserves content copied by the user between consecutive insertions.
- Literal correction replacements and priority for longer correction terms, plus explicit validation of saved data files.
- Standalone app builds verify ad hoc code signatures and embedded runtime dependencies, with a macOS 14 minimum target.

See the [v2.3.0 release notes](docs/releases/v2.3.0.md) for feature details and completed validation.

## Settings and local files

Preferences saves settings in `~/.speaktype/config.json`. History, hotwords, corrections, snippets, and the custom dictionary also remain in `~/.speaktype/`. Invalid JSON or invalid stored field types produce an explicit error and leave the file intact.

| Setting | Default | Purpose |
|---|---|---|
| `hotkey` | `"right_cmd"` | `right_cmd`, `left_cmd`, `fn`, `right_alt`, `right_ctrl`, `ctrl+shift+space`, `f5`, or `f6` |
| `dictation_mode` | `"push_to_talk"` | Hold a key or use `"toggle"` |
| `audio_device` | `null` | System default, device name, or device index |
| `asr_model` | `"mlx-community/Qwen3-ASR-1.7B-8bit"` | Local Qwen3-ASR model |
| `language` | `"auto"` | Recognition language |
| `llm_model` | `"huihui_ai/qwen3.5-abliterated:9b-Claude"` | Local Ollama model |
| `ollama_url` | `"http://localhost:11434"` | Ollama service address |
| `polish_enabled` | `true` | Text polishing |
| `auto_punctuation` | `true` | Allow polishing to add punctuation |
| `filler_removal` | `true` | Remove filler words during polishing |
| `context_aware_tone` | `true` | Select polishing tone by app |
| `translate_enabled` / `translate_target` | `false` / `"en"` | Translate the output |
| `voice_commands_enabled` | `true` | Punctuation and editing commands |
| `streaming_preview` | `true` | Display recognition progress |
| `history_enabled` / `history_max_entries` | `true` / `1000` | Save and limit history |
| `insert_method` | `"paste"` | Clipboard insertion or `"type"` for keyboard events |
| `max_recording_seconds` | `360` | Recording duration limit |
| `sound_feedback` | `true` | Recording start/stop sounds |
| `hotword_learning_enabled` | `true` | Learn terms from immediate edits |
| `hotword_context_enabled` | `true` | Include learned terms in recognition and polishing |
| `hotword_auto_corrections_enabled` | `true` | Promote confident correction pairs |
| `hotword_observation_seconds` | `18` | Edit-observation period |
| `hotword_observation_stable_seconds` | `1.2` | Wait for an edit to stabilize |
| `hotword_max_context_terms` | `30` | Maximum learned terms per request |
| `plugins_enabled` | `false` | Enable local Python plugins |
| `ui_language` | `"zh"` | `"zh"` or `"en"` |

## Troubleshooting

**Recording or hotkey failure:** open **Local Diagnostics**, check Microphone, Accessibility, and Input Monitoring in System Settings, and select the intended microphone. Restart SpeakType after changing permissions if prompted.

**Text is missing:** open **Dictation History** or use **Copy Last Dictation**, then paste the result into a focused editable field. Review the recorded insertion status before trying again.

**Polishing or translation is skipped:** open Ollama, confirm the model under **Preferences > AI Models**, and use the install command shown by **Local Diagnostics**. Dictation remains available while the local LLM is unavailable.

**A saved file is rejected:** use the reported format or field error to correct the corresponding JSON file before restarting. SpeakType preserves its contents. The log is `~/.speaktype/speaktype.log`.

## Run from source

Source use requires Python 3.10 on an Apple Silicon Mac. From the repository directory:

```bash
git clone https://github.com/Konoyo-014/SpeakType.git
cd SpeakType
python3.10 -m venv venv
./venv/bin/python -m pip install -r requirements.txt
./venv/bin/python -m pip check
./venv/bin/python scripts/verify_runtime.py
./venv/bin/python main.py
```

The setup window can download the ASR model. A source launch may require granting permissions to Terminal or your IDE. If you need a Hugging Face mirror, set `HF_ENDPOINT` to your chosen mirror before launching from the same Terminal.

`./setup.sh` additionally prepares Ollama and downloads the default ASR and polishing models. It requires Homebrew for Ollama installation when Ollama is missing.

### Validate and build

```bash
PYTHONPATH=. ./venv/bin/python scripts/validate_core.py
PYTHONPATH=. ./venv/bin/python scripts/validate_clipboard.py
PYTHONPATH=. ./venv/bin/python scripts/validate_history_ui.py
./venv/bin/python scripts/verify_runtime.py

./build_dmg.sh --app
./build_dmg.sh
```

Install `requirements-build.txt` in the build environment. `SPEAKTYPE_PYTHON` selects an absolute path to a Python 3.10 interpreter built for macOS 14 or earlier, with a shared zlib extension. The release uses conda-forge Python 3.10.19 and the official macOS 14 MLX wheels pinned in `requirements-build.txt`. The build checks the interpreter before packaging. Builds write intermediate files and logs under `work/`, produce `dist/SpeakType.app` and `dist/SpeakType-2.3.0.dmg`, apply ad hoc code signing, verify strict bundle signatures, and execute embedded-runtime dependency checks. The DMG includes an Applications shortcut for installation.

### Python plugins

Put plugin files in `~/.speaktype/plugins/` and enable them in Preferences. Files prefixed with `_` are ignored.

| Hook | Signature |
|---|---|
| `pre_transcribe` | `(audio_path) -> audio_path` |
| `post_transcribe` | `(raw_text) -> text` |
| `pre_polish` | `(text, tone) -> (text, tone)` |
| `post_polish` | `(polished_text) -> text` |
| `pre_insert` | `(text) -> text or None` |
| `post_insert` | `(text) -> None` |
| `on_recording_start` | `() -> None` |
| `on_recording_stop` | `() -> None` |

```python
PLUGIN_NAME = "Preferred Spelling"
PLUGIN_VERSION = "1.0"

def post_transcribe(text):
    return text.replace("Speak Type", "SpeakType")
```

## License

[MIT](LICENSE)
