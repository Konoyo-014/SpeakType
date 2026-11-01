# SpeakType

[中文文档](README_CN.md)

Record speech in the native SpeakType window, edit the result, and copy or insert it into another app. Hold Right Command to dictate directly into a focused input field. Qwen3-ASR runs on your Mac; a local Ollama model provides optional polishing and translation.

## Install

Requires **macOS 14 or later and an Apple Silicon Mac**. The DMG includes the Python runtime and application dependencies.

1. Open the [latest GitHub release](https://github.com/Konoyo-014/SpeakType/releases/latest) and download the `SpeakType-*.dmg` attachment.
2. Open the DMG, drag **SpeakType** into **Applications**, and launch it from Applications.
3. The main window shows microphone, recognition, local-model, insertion, and global-shortcut readiness. Open **Setup** to prepare permissions and models.
4. Use the permission buttons to open **System Settings > Privacy & Security** for **Microphone**, **Accessibility**, and **Input Monitoring**. Allow SpeakType, refresh its status, and restart it when macOS requests a restart.
5. Click **Download model** for speech recognition. The default model downloads about 2.47 GB. Keep an internet connection available until the files are verified.
6. Select **Use dictation only**, or prepare the optional local model in the same window. Click **Try dictation** to record in the main window.

The app also provides a menu-bar microphone for opening the main window, setup, preferences, history, and diagnostics. If macOS requests approval to open the downloaded app, use **System Settings > Privacy & Security > Open Anyway** for SpeakType.

### Optional polishing and translation

In **Setup**, enable polishing or translation and check the Ollama service. **Install Ollama…** opens the [official macOS download page](https://ollama.com/download/mac). Once Ollama is installed, **Start Ollama** starts its installed app or service. SpeakType connects to `http://localhost:11434` by default; Preferences can select another server.

Choose an installed model from the list, or click **Download model** to install the configured model. The default is `huihui_ai/qwen3.5-abliterated:9b-Claude`, a download of about 6.59 GB. The window shows actual downloaded bytes and percentage. **Cancel download** ends this window's request and preserves the official cache for retry. Returning to the main window keeps the download running.

If Ollama reports that a model requires a newer server, **Update Ollama…** opens the official download page. **Error details…** displays the complete error in a scrollable window with text selection and **Copy error**. You can turn off both language features with **Use dictation only**.

Setup checks the configured service and full model tag. Recognition is marked ready after configuration, tokenizer, and weight files pass complete-cache validation. A damaged cache offers **Redownload model**, which downloads and validates the complete model through the official Hugging Face client.

If an enabled language feature becomes unavailable during dictation, SpeakType keeps the transcription and reports that processing was skipped. The main window and history retain available text for recovery.

## Record, edit, and insert

1. Click **Start dictation** in the main window, speak, and click **Stop recording**. The window shows microphone level, elapsed time, live recognition, original transcription, and final text.
2. Edit **Final text** directly. You can copy it, use **Polish again**, or choose a language and click **Translate**. These language actions use the configured local Ollama model.
3. Click the intended input field in another app, return to SpeakType, and select that app under **Target app**. Click **Insert into…**. SpeakType checks the target before sending text and reports the insertion result.
4. Use **Cancel** during recording, recognition, polishing, or translation to stop the current operation. Available text stays in the window. A cancelled operation cannot insert a later result.

Main-window recording prepares text for review. For direct insertion, focus the destination and use the global shortcut. Its destination is the app selected when recording starts.

| Main-window shortcut | Action |
|---|---|
| `⌘R` | Start or stop recording |
| `⌘↩` | Insert the current final text into the selected app |
| `⇧⌘C` | Copy final text |
| `⇧⌘P` | Polish final text again |
| `⇧⌘T` | Translate final text |
| `Esc` | Cancel the current operation |

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
| Saved; ready to insert | Final text is available for review or manual insertion |
| Inserted | Accessibility reported the inserted text in the target field |
| Sent, unverified | Input was sent, but the target did not expose enough information to verify it |
| Failed | SpeakType could not complete insertion |
| Cancelled | The operation ended before delivery; available text remains saved |

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

## What's new in v3.0.0

- A native main window with recording controls, readiness checks, original and editable final text, target-app selection, local polish/translation, recent records, and keyboard shortcuts.
- A single setup window for permissions, complete ASR downloads and repair, Ollama installation/startup, installed-model selection, actual progress, cancellation, and retry.
- Main-window recording prepares a reviewable result; the global shortcut inserts into the app captured at recording start. Cancellation and target checks protect delivery.
- Searchable native dictation history with full original/final text, copy buttons, insertion results, refresh, and export.
- Original transcription retained before polishing; final text saved before insertion; menu actions to copy or insert the latest result again.
- Consecutive spoken quotation marks, brackets, and punctuation in English and Chinese.
- Safe voice undo checks the input field, complete text, and UTF-16 cursor range before selecting and removing the verified insertion.
- Language-preserving polishing, actual microphone authorization, exact Ollama model tags, and ASR-cache validation before download completion.
- Clipboard restoration preserves content copied by the user between consecutive insertions.
- Literal correction replacements and priority for longer correction terms, plus explicit validation of saved data files.
- Standalone app builds verify ad hoc code signatures and embedded runtime dependencies, with a macOS 14 minimum target.

See the [v3.0.0 release notes](docs/releases/v3.0.0.md) for feature details and completed validation.

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

**Recording or hotkey failure:** open **Setup**, check Microphone, Accessibility, and Input Monitoring with their settings buttons, then refresh. Select the intended microphone in Preferences. Restart SpeakType after changing permissions if prompted.

**Text is missing:** open **Dictation History** or use **Copy Last Dictation**, then paste the result into a focused editable field. Review the recorded insertion status before trying again.

**Polishing or translation is skipped:** open **Setup**, start Ollama, and download the selected model or choose an installed model. Use the update button when the server requests a newer Ollama. **Use dictation only** disables both features.

**A model download fails:** read the actual error shown in Setup, check the connection or Ollama service, and use **Retry download**. A damaged ASR cache provides **Redownload model**. Cancellation preserves official cache files for a later request.

**A saved file is rejected:** use the reported format or field error to correct the corresponding JSON file before restarting. SpeakType preserves its contents. The log is `~/.speaktype/speaktype.log`.

## Run from source

Source use requires Python 3.10 on an Apple Silicon Mac. From the repository directory:

```bash
git clone https://github.com/Konoyo-014/SpeakType.git
cd SpeakType
python3.10 -m venv venv
mkdir -p work/temporary
export TMPDIR="$PWD/work/temporary/"
./venv/bin/python -m pip install -r requirements.txt
./venv/bin/python -m pip check
./venv/bin/python scripts/verify_runtime.py
./venv/bin/python main.py
```

The setup window manages recognition and optional Ollama models. A source launch may require granting permissions to Terminal or your IDE. If you need a Hugging Face mirror, set `HF_ENDPOINT` to your chosen mirror before launching from the same Terminal.

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

Install `requirements-build.txt` in the build environment. `SPEAKTYPE_PYTHON` selects an absolute path to a Python 3.10 interpreter built for macOS 14 or earlier, with a shared zlib extension. The release uses conda-forge Python 3.10.19 and the official macOS 14 MLX wheels pinned in `requirements-build.txt`. The build checks the interpreter before packaging. Builds write intermediate files and complete logs under `work/`, produce `dist/SpeakType.app` and `dist/SpeakType-3.0.0.dmg`, apply ad hoc code signing, verify strict bundle signatures, and execute embedded-runtime dependency checks. The DMG includes an Applications shortcut for installation.

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
