# Changelog

## [3.0.0] - 2026-11-01

### Added

- Added a native main window with recording and cancellation controls, readiness checks, original transcription, editable final text, target-app selection, polishing, translation-language selection, recent history, and keyboard shortcuts.
- Added a native permissions-and-models window with accurate permission links, complete ASR downloads and repair, installed Ollama startup, official installation/update actions, installed-model selection, real download progress, cancellation, and retry.
- Main-window recording retains text for review. Global-shortcut recording captures the destination app at recording start; explicit insertion checks the selected process before sending text.
- Cancellation rejects late transcription and language-model results while retaining available text. Manual edits are saved to the same history record and receive a saved-for-insertion status.
- Quit waits for in-flight text persistence, marks pending work cancelled, and rejects new delivery. Engine identity checks keep a replaced ASR model's load result from changing the active model state.
- Added a searchable native Dictation History window with time, app, insertion result, complete original/final text, separate copy buttons, refresh, empty states, and TXT/Markdown/CSV/JSON export.
- Added Copy Last Dictation and Insert Last Dictation Again to the menu. The latest result remains available during the current session when history is disabled.
- Retained original transcription before local polishing and saved final text before insertion. History records unconfirmed, verified insertion, sent-but-unverified, and failed insertion states.
- Added consecutive spoken punctuation, quotation marks, parentheses, square brackets, and Chinese book-title marks, including nested quoted and parenthesized content.
- Voice undo captures the verified insertion's Accessibility element, complete text, and UTF-16 cursor range. It removes the exact inserted span only while the element, text, and cursor still match.

### Changed

- Clipboard restoration preserves content copied by the user between consecutive insertions and during a pending restore.
- Correction replacements preserve literal backslashes and apply longer terms before shorter overlapping terms.
- Saved configuration, dictionary, corrections, snippets, hotwords, and history validate JSON structure and field types. Invalid files raise explicit errors and retain their original contents.
- History uses stable record identifiers, synchronous atomic updates, deep-copy snapshots, and thread-safe export reads.
- Existing history without an insertion outcome is displayed as sent but unverified.
- Polish-only processing preserves the transcription's language. Language-drift checks cover short English text, and retries retain the requested language for Japanese and Korean input.
- Setup and diagnostics read actual microphone authorization, check the configured Ollama model's exact tag and service address, and verify model configuration, tokenizer files, weight files, and indexed tensors before reporting a complete ASR cache. Download progress completes after the model check.
- The setup window preserves its controller and active downloads across closing, reopening, and UI-language changes. Use dictation only disables polishing and translation in saved settings.
- Native windows retain their objects across closing and reopening. Language changes release the previous main window's edit timer, undo notifications, and delegates. Quit waits for model and preparation workers; a timed-out quit restores the running application's controls and preparation state.
- ASR downloads use an isolated native helper and the official Hugging Face HTTP client. Cancelled downloads retain official cache files; damaged configuration offers an explicit complete redownload. Ollama transfers use its official streaming API and display the original service error.
- The first correction or snippet saved to an empty library takes effect immediately. The hotword window refreshes newly learned terms from the application's active store.
- Standalone application builds use ad hoc code signing, strict signature checks, embedded-runtime execution checks, Mach-O dependency checks, and a macOS 14 minimum deployment target. Build logs and intermediate files are stored under `work/`.
- Installation instructions start with the release DMG, Applications installation, macOS permissions, and daily dictation/recovery controls.

### Validation

- Functional checks ran on an Apple Silicon Mac running macOS 26.6.2. The macOS 14 minimum was checked against binary deployment metadata and linked dependencies.
- `scripts/validate_core.py`: six source groups passed using isolated real files and production functions, including concurrent persistence, all four history export formats, invalid-data rejection, and literal text handling.
- `scripts/validate_main_window.py`: actual native controls passed all operation phases, five readiness items, real running-app selection, persisted Unicode edits, native undo/redo, clipboard copying, recent records, auxiliary-window actions, resizing, close/reopen, keyboard equivalents, and Chinese/English labels. Explicit phase inputs exercise control behavior separately from microphone/model tests.
- `scripts/validate_operation_commits.py`: 24 real concurrent worker commits were rejected after cancellation. Actual history-lock contention, old-operation results, cancelled record creation, saved outcomes, and history-disabled sessions retained the correct text and state.
- `scripts/validate_setup_center.py`: source controls saved feature/model changes to isolated files, used actual permissions, checked the complete default ASR cache, and read the live Ollama model list. An actual 9B transfer passed language changes and close/reopen without replacing the task, then cancelled successfully. A real registry-version error exposed the update action. A damaged JSON cache exposed complete redownload, began official HTTP transfer, and cancelled successfully.
- `scripts/validate_model_manager.py`: the source helper checked the complete default ASR cache, cancelled and retried actual helper processes, repaired a missing tokenizer file through official HTTPS with matching SHA-256, and started an isolated installed Ollama service without changing the main service.
- The configured default 9B model completed its actual official download. All five local blobs passed independent size/SHA-256 verification, totaling 6,594,471,075 bytes. The complete `setup.sh` run exited successfully with dependency checks, runtime execution, and both configured models ready.
- `scripts/validate_desktop_flow.py`: 14 bundled cases passed actual readiness, ASR preview/save, cancellation during a real ASR wait, the next operation, native editing/copying, actual 2b polishing/translation on the same record, microphone recording, an actual F6 stop, TextEdit target capture, rejection after a selection change, and explicit reinsertion.
- `scripts/validate_lifecycle.py`: source checks passed real language-menu changes, stale-engine identity rejection, pending-record preservation on quit, actual file-write contention and deadline behavior, and concurrent microphone stop/cancellation.
- `scripts/validate_window_lifetime.py`: source and final-bundle `NSApplication.run` loops passed 20 rounds across ten windows, with 400 opens/reopens per run separated by native timer events and garbage collection. The final bundle also passed 20 Chinese/English menu changes with old-main-window disposal and recreation. Both processes exited successfully and their fatal-signal logs were empty.
- `scripts/validate_relaunch.py`: the old native process exited and the actual main application restarted with its isolated configuration, default ASR loaded, and native shortcut monitoring active. The fatal-signal log was empty.
- Computer Use verified the final main application saving Chinese UI/F6 push-to-talk preferences and reopening Preferences, holding/releasing F6 in SpeakType for actual speaker-to-microphone dictation, selecting TextEdit, and inserting matching document text with a verified history outcome.
- `scripts/validate_model_shutdown.py` and `scripts/validate_quit_recovery.py`: source and final-bundle checks passed five actual 1.7B-model shutdown scenarios covering loading, asynchronous loading, warmup, timeout recovery, and replaced-engine collection. Preparation/diagnostics remained usable after real Unicode-file worker delays, with restored readiness/timers and successful native process exits.
- The final bundle passed all six core groups, 24 concurrent cancellation cases, actual concurrent Ollama metadata queries, and lifecycle checks through its native verification entry point. Actual product-module paths resolved inside the app. The native ASR worker passed cache completion and active cancellation/retry; invalid model input exited in 0.33 seconds. Strict signatures, 262 Mach-O files, actual GitHub/Hugging Face HTTPS, and read-only mounted execution passed.
- Final bundled main-window, history, clipboard, auxiliary-window, and model-cache checks also passed. They verified actual product-module paths, complete pasteboard restoration, no remaining visible test windows, and actual SafeTensors corruption/completeness cases.
- The final bundle passed seven complete ASR/TextEdit delivery/recovery flows, eight safe-undo cases, real English/Chinese streaming with simultaneous final transcription, default ASR file/array/silence checks, and actual 2b polishing/translation with short-English/Japanese/Korean language preservation.
- The final bundle also passed default-ASR English/Chinese file/array and silence checks using the configured default 9B polishing model. Actual 9B English polishing, Chinese translation, and short-English/Japanese/Korean language preservation passed.
- The final default-9B desktop run passed all nine readiness, preview/save, cancellation during real ASR waiting, following-operation, native edit/copy, same-record polishing/translation, recording-cancel, and help/setup cases.
- Actual source microphone capture, default Qwen3-ASR 1.7B English/Chinese recognition, input-file preservation, silence handling, and local `qwen3-vl:2b-instruct` polishing/translation were verified. Language checks retained English, Japanese, and Korean.
- Source TextEdit insertion/recovery, eight safe-undo conditions, clipboard preservation, searchable history, six auxiliary native windows, preferences persistence, vocabulary changes, and streaming recognition were verified with real application controls and files.

### 中文

- 原生主窗口提供录音、取消、准备状态、原始转写、可编辑最终文本、目标应用选择、润色、翻译语言、最近历史和键盘快捷键。
- 同一个原生准备窗口提供权限设置入口、完整语音模型下载与修复、Ollama 启动与官方安装页面、已安装模型选择、真实下载进度、取消和重试。
- 主窗口录音保留结果供检查与编辑。全局快捷键使用录音开始时记录的目标应用，主动插入会在发送之前检查选定进程。
- 已取消操作的后续结果不会覆盖当前文本或继续插入。手动编辑保存到原来的历史记录，并显示为待插入状态。
- 退出会等待正在完成的文本写入，保留尚未完成的记录并取消后续发送。切换语音模型后，旧模型的加载结果不会改变当前模型状态。
- 新增可搜索的原生听写历史窗口，显示时间、应用和插入结果，可以查看与复制完整的原始转写和最终文本，并提供刷新、空状态和四种格式的导出功能。
- 菜单新增复制最近听写与再次插入最近听写。关闭历史记录时，当前会话仍保留最近一次结果。
- 在本地润色前保留原始转写，在插入前保存最终文本；历史记录区分尚未确认、已插入、已发送但未验证和插入失败。
- 支持连续口述引号、圆括号、方括号、书名号和结尾标点，包括引号与括号嵌套的内容。
- 语音撤销会保存已验证插入的辅助功能元素、完整正文与 UTF-16 光标位置，只有这些内容仍然一致时，才会精确选中并删除对应的听写内容。
- 剪贴板恢复保留用户新复制的内容；纠错保留反斜杠，并优先处理较长的词语。
- 本地保存文件会验证 JSON 结构与字段类型，错误会明确报告，原文件得到保留。
- 旧历史缺少插入结果时，会显示为已发送但未验证。润色会保持原文语言，短英文误译检查与日文、韩文重试也遵守语言要求。
- 准备设置与本地自检读取真实麦克风授权，核对指定的 Ollama 服务与完整模型标签，并检查语音模型的配置、分词文件和权重。完成模型检查后，下载进度才会显示完成。
- 关闭和重新打开准备窗口，以及切换界面语言，都会保留正在进行的下载。仅使用语音识别会同时关闭润色与翻译。空词库首次保存的纠错与快捷短语立即生效，热词窗口刷新后可以显示新增词语。
- 原生窗口保留关闭后重新打开所需的对象。切换语言会清理旧主窗口的编辑定时器、撤销通知与委托。退出会等待模型和准备任务结束；等待超时后，应用继续运行并恢复准备状态与控件。
- 源码与最终应用包均在正式 `NSApplication.run` 事件循环中完成十种窗口二十轮关闭与重新打开，每次运行包含400次打开操作和垃圾回收；最终包还完成二十次中英文菜单切换，以及旧主窗口清理与重建。两个进程均正常退出，致命信号日志为空。源码与最终应用包还通过五种真实 1.7B 模型退出情形，包含加载、异步加载、预热、超时恢复和旧模型释放；真实文件任务结束后，准备窗口与自检窗口可以继续使用，状态和定时器得到恢复。
- 最终应用包已经通过正式重新启动检查：旧原生进程结束，新主程序保留原来的配置，完成默认识别模型加载并启动快捷键监听，致命信号日志为空。
- 最终正式主程序通过实际界面检查：中文与F6按住说话设置保存后可以重新打开偏好设置，在SpeakType中按住和松开F6完成扬声器到麦克风的真实听写，再选择TextEdit插入；实际正文与结果一致，历史显示已验证插入。
- 源码已经通过主窗口原生控件、24个并发取消结果、真实权限与服务、下载进度、下载期间语言切换与窗口复用、真实服务版本错误、损坏缓存重新下载及取消检查。控件状态检查与实际麦克风、模型测试分别记录。
- 默认9B模型已经完成官方实际下载，全部五个本地文件通过独立大小与SHA-256检查，总计6,594,471,075字节。完整 `setup.sh` 正常结束，依赖检查、真实运行环境与两个默认模型的准备状态均通过验证。
- 源码还通过默认 1.7B 中英文识别、输入文件保留、静音、真实麦克风录音、实际 2b 本地模型润色与翻译、TextEdit 插入与恢复、六种辅助窗口、设置保存、流式预览和八项安全撤销检查。
- 3.0 应用包已经通过十四项完整桌面检查，包含实际录音、真实 F6 停止、原生编辑复制、同条历史的实际 2b 润色与翻译、TextEdit 目标记录、选区变化后拒绝自动插入，以及明确选择再次插入后的成功发送。
- 最终应用包通过六组核心功能、24个并发取消结果、真实 Ollama 信息查询和退出处理检查，并核对实际模块来自应用包。原生下载程序通过缓存完成、取消、重试与快速失败；严格签名、262个二进制文件、真实 HTTPS 和只读安装包运行检查通过。
- 最终应用包还通过七项识别、发送与恢复流程，八项安全撤销，真实中英文流式预览与并发最终识别，默认识别模型的文件、数组和静音检查，以及实际 2b 模型的润色、翻译和短英文、日文、韩文语言保持检查。
- 最终应用包已经使用默认9B模型完成默认识别模型的中英文文件、数组和静音检查，以及真实英文润色、中文翻译、短英文和日韩语言保持检查。
- 最终默认9B桌面检查的九项流程全部通过，包含真实准备状态、识别预览与保存、真实识别等待期间取消、后续新操作、原生编辑复制、同条历史润色与翻译、录音取消，以及帮助与准备窗口入口。
- 功能检查使用 macOS 26.6.2 的 Apple Silicon Mac；macOS 14 最低要求通过二进制最低系统声明和依赖检查确认。
- 独立应用构建检查 ad hoc 代码签名、内置运行环境和二进制依赖，最低系统版本为 macOS 14；安装说明优先介绍 DMG、应用程序文件夹、权限和日常使用。

## [2.2.0] - 2026-05-08

### Official public release
- Published V2.2 as the official `v2.2.0` release instead of exposing the internal v2.2.x development iteration numbers.
- Consolidated the adaptive-hotword system, native hotword window, preferences controls, local diagnostics, setup-wizard hardening, dictionary/statistics/HUD polish, Chinese localization work, and packaged-app release validation into the public release notes.
- 正式公开版本号统一为 `v2.2.0`，不再把内部 v2.2.x 渐进开发编号作为公开 release 口径。
- 公开说明已合并自适应热词、原生热词窗口、偏好设置控制、本地自检、首次启动向导加固、词典/统计/HUD 打磨、中文本地化和打包验证结果。

### Validation
- `venv/bin/python -m pytest -q $(git ls-files 'tests/test_*.py')`: 517 passed.
- `venv/bin/python -m compileall $(git ls-files 'speaktype/*.py' 'tests/test_*.py')`: passed.
- `git diff --check` and `git diff --check --cached`: passed.
- Packaged macOS DMG verification, mounted-app version checks, and strict codesign verification are required for the final public `SpeakType-2.2.0.dmg`.

## [2.2.22-dev] - 2026-05-08

### Changed
- Reused already-visible utility windows from the menubar instead of creating duplicate Settings, Dictionary & Snippets, Statistics, Local Diagnostics, or Adaptive Hotwords windows on repeated menu clicks.
- Preserved in-progress edits and current window focus by raising the existing visible window rather than replacing its controller.

### Tests
- Added app-level window-controller lifecycle coverage for visible-controller reuse and hidden-controller replacement. Computer Use verified the packaged native controller-reuse path.

## [2.2.21-dev] - 2026-05-08

### Changed
- Tightened the Local Diagnostics window's fallback layout. When the diagnostic list switches from a populated report back to a running or empty state, the scroll document height is now reset instead of preserving stale blank scroll space.
- Kept populated diagnostic reports sized from their actual row content while making the no-item state a stable, compact document.

### Tests
- Added diagnostics-window coverage for empty-row document sizing after stale rows are removed. Computer Use verified the packaged native diagnostics window after a tall report collapsed back to the running fallback state.

## [2.2.20-dev] - 2026-05-08

### Changed
- Added visible feedback to the Adaptive Hotwords window's Reveal File action. The footer now confirms whether SpeakType revealed the hotword file or opened the configuration folder because no hotword file exists yet.
- Reused the hotword window footer feedback line for copy, refresh, and reveal actions so action results are visible in one predictable place.

### Tests
- Added adaptive-hotword window coverage for reveal feedback and missing-file fallback behavior. Computer Use verified the packaged native hotword window with an empty learned-hotword store and Reveal File action.

## [2.2.19-dev] - 2026-05-08

### Changed
- Tightened the Adaptive Hotwords refresh behavior. Refresh now clears stale Copy Context feedback so old copy or empty-state messages are not shown after the hotword store is reloaded.
- Reset the hotword list document height when the refreshed list is empty, avoiding blank scroll space left over from a previously populated list.

### Tests
- Added adaptive-hotword window coverage for refresh feedback clearing and empty-list document sizing. Computer Use verified the packaged native hotword window after copy-empty followed by refresh.

## [2.2.18-dev] - 2026-05-08

### Changed
- Improved the Adaptive Hotwords window's Copy Context action. When there are no active learned hotwords, SpeakType now shows a clear empty-state message instead of reporting that zero hotwords were copied.
- Preserved the user's clipboard when no active hotword context exists. The clipboard is only written when there is real hotword context to copy.

### Tests
- Added adaptive-hotword window coverage for empty and non-empty copy-context states. Computer Use verified the packaged native hotword window with an empty learned-hotword store.

## [2.2.17-dev] - 2026-05-08

### Changed
- Added a dirty-close guard to the Dictionary & Snippets window. When users have unsaved dictionary, snippet, or correction edits, the first Close action now keeps the window open and shows a clear warning; closing again intentionally discards the changes.
- Applied the same guard to the native window close control, so the titlebar close button no longer silently drops unsaved dictionary edits.

### Tests
- Added dictionary-window coverage for the two-step discard confirmation and for resetting that confirmation after another edit. Computer Use verified the packaged native dictionary window with a real unsaved edit.

## [2.2.16-dev] - 2026-05-08

### Changed
- Rebuilt the setup wizard ASR error transition so a failed model download now re-renders the full Speech Recognition Model step in its error state. This restores the explanatory hint below the error instead of leaving the user with only a red status line and retry buttons.
- Kept the stale progress-bar removal behavior by clearing and rebuilding the step after a failed download.

### Tests
- Added setup-wizard coverage for the full ASR error-state rebuild after a failed download. Computer Use verified the packaged macOS wizard with a real missing-model failure.

## [2.2.15-dev] - 2026-05-08

### Changed
- Expanded the setup wizard's ASR download failure state into a wrapped, variable-height label. Long network, Hugging Face, or model-resolution errors now remain readable instead of being clipped inside a one-line status row.
- Kept the ASR download hint and action buttons anchored below the expanded error text, preserving the step layout after a retryable failure.
- Removed the stale progress bar when ASR model download fails, so the error state no longer looks like a download is still running.

### Tests
- Added setup-wizard layout coverage for short, medium, and long ASR download status text, plus stale-progress removal after errors. Computer Use verified the packaged macOS wizard with a real failed model-download path.

## [2.2.14-dev] - 2026-05-08

### Fixed
- Hardened setup-wizard ASR model downloading against the `huggingface_hub.snapshot_download` progress-bar `name` argument used by newer Hugging Face Hub releases. The packaged app now absorbs that argument instead of surfacing a raw `Unknown argument(s)` failure when a user clicks `下载模型`.
- Replaced raw Python download exceptions in the setup wizard with localized, user-readable failure states for downloader incompatibility, missing models, network/Hugging Face service failures, and unknown errors.

### Tests
- Added model-download coverage for Hugging Face progress-bar compatibility and localized setup-wizard download errors. Computer Use and packaged-Python verification were run against the final macOS bundle.

## [2.2.13-dev] - 2026-05-08

### Changed
- Localized compact hotkey display names used in the menubar, ready notification, and setup completion step. Chinese UI now shows `快捷键：右 ⌘` and `⌃⇧空格` instead of mixing in `Right ⌘` or `Space`.
- Localized the About notification body so Chinese UI shows `识别后端` instead of the hardcoded English `Backend:`.
- The setup wizard no longer auto-starts the ASR model download as soon as the Speech Recognition Model step appears. It now shows an explicit `下载模型` action and a `稍后下载` path before any network download starts.
- Localized the ASR download preparation status so Chinese UI shows `正在准备` instead of `Starting...`.

### Tests
- Added coverage for localized hotkey display names, About body text, ASR download status localization, and the setup-wizard download action state. Computer Use verified the packaged macOS setup wizard no longer starts ASR download before the explicit download action.

## [2.2.12-dev] - 2026-05-08

### Changed
- Localized the setup wizard's Ollama readiness labels. The Text Polishing step now shows `Ollama 安装`, `Ollama 本地服务`, and `润色模型` in the Chinese UI instead of mixing in English labels.
- Tightened the Chinese LLM model status copy so it consistently refers to the polishing model as `润色模型`.
- Copy Command buttons in the setup wizard now confirm the action by changing to `已复制` after the command is written to the pasteboard.

### Tests
- Added setup-wizard coverage for localized LLM-step labels and copy confirmation text. Computer Use verified the real macOS setup wizard LLM step with Ollama installed, service missing, model missing, both copy buttons, and visible copied confirmation.

## [2.2.11-dev] - 2026-05-08

### Changed
- Localized the Statistics window duration formatting. Chinese UI now shows minutes and seconds as `分钟` and `秒` in the summary, metric tiles, and recent-dictation metadata instead of mixing in `min` and `s`.
- Localized the recent 7-day activity labels in the Statistics window. Chinese UI now uses `周一` through `周日` instead of English weekday abbreviations.

### Tests
- Added statistics-window coverage for localized duration units and Chinese weekday labels. Computer Use verified the real macOS Statistics window with populated history, localized summary/metric/activity labels, long recent-dictation rows, scrolling, and fixed footer controls.

## [2.2.10-dev] - 2026-05-08

### Changed
- Local Diagnostics now uses localized readiness summaries instead of English-only `OK / WARN / FAIL` counters in the Chinese UI.
- Refresh now has visible in-place progress feedback: the Refresh button changes to a disabled checking state while the diagnostics worker is running, and Copy Report is disabled until a report is available.
- Copy Report now gives direct confirmation by changing the button title to Copied after the pasteboard write succeeds. Starting a new refresh resets the button to its normal label.

### Fixed
- Namespaced the native flipped-view classes used by Local Diagnostics and Adaptive Hotwords so PyObjC does not see duplicate Objective-C class names when both modules are loaded in one process.

### Tests
- Added diagnostics-window coverage for localized summary counts. Computer Use verified the real macOS diagnostics window across localized summary rendering, copy confirmation, disabled running state, and recovery after refresh completion. Full-suite testing also verified the diagnostics/hotwords Objective-C class-name collision is resolved.

## [2.2.9-dev] - 2026-05-08

### Changed
- Rebuilt Dictionary & Snippets as a native sectioned editor with a left navigation rail for Custom Dictionary, Snippets, and Corrections. Users no longer have to scan one long scrolling form to manage V2.2 hotword-adjacent vocabulary, shortcuts, and correction rules.
- Added live collection counts and a fixed footer status line. Add, duplicate, empty-input, remove, unsaved, and save states now produce visible feedback instead of silently changing the underlying lists.
- Preserved full snippet and correction text in the list formatters and widened long-text input rows after real Computer Use testing showed the first rebuild still clipped long snippet bodies.

### Tests
- Added dictionary-window coverage for section ordering, full-content row formatting, collection counts, and dirty-status reset across section switches. Computer Use verified the real macOS dictionary editor across section switching, long-word entry, visible unsaved state, and save/close behavior.

## [2.2.8-dev] - 2026-05-07

### Changed
- Rebuilt Preferences as a native sectioned window with a left navigation rail and a single visible settings group at a time. General, AI Models, Features, Adaptive Hotwords, and System no longer live in one long scroll form.
- Made Adaptive Hotword settings directly reachable without scrolling, with all learning/context/correction toggles and numeric bounds visible in one view.
- Preserved edits while switching preference sections and clamped numeric hotword settings immediately when a section is left and re-entered.

### Tests
- Added settings-window coverage for section ownership, numeric clamping, invalid-number fallback, and checkbox state reads. Computer Use verified every Preferences section, hotword numeric clamp behavior, and the save callback path in a real macOS window.

## [2.2.7-dev] - 2026-05-07

### Changed
- Reworked the adaptive-hotword status window rows to use variable heights. Long learned terms, aliases, and application contexts now remain readable instead of being clipped inside a fixed 88pt row.
- Widened the adaptive-hotword status window slightly and moved row status metadata under the term, preserving the full term as the primary visual object.
- Added copy feedback below the hotword list so Copy Context visibly confirms how many active hotwords were copied.

### Tests
- Added deterministic hotword-row sizing coverage and active-context copy coverage. Computer Use verified the real native hotword window with long terms, long aliases, active/candidate rows, and long application identifiers.

## [2.2.6-dev] - 2026-05-07

### Changed
- Reworked the recording HUD body text renderer so dictated previews and final inserted text use a native read-only multiline text view instead of a single-line text field. Long CJK and mixed technical terms now wrap visibly instead of being clipped on the right edge.
- Made the HUD width responsive to the current visible screen frame so the overlay remains inside narrow displays, split-screen windows, and constrained desktop spaces.

### Tests
- Added responsive HUD geometry coverage. Computer Use verified the real macOS HUD across final-result, recording with active hotwords and whisper indicator, long streaming preview, polishing, and error states.

## [2.2.5-dev] - 2026-05-07

### Changed
- Added a step counter and progress bar to the first-launch setup wizard so users can see where they are in the setup flow.
- Increased the setup wizard window height to preserve spacing after adding progress context.

### Fixed
- Fixed the setup wizard command-copy behavior when multiple commands are visible on the Ollama step. Each Copy Command button now copies the command next to it instead of reusing the last command rendered on the page.

### Tests
- Added setup-wizard command selection coverage. Computer Use reproduced the incorrect copy behavior, then verified that the Ollama service button copies `ollama serve`, the model button copies the matching `ollama pull ...` command, and the new progress indicator renders through the completion step.

## [2.2.4-dev] - 2026-05-07

### Changed
- Rebuilt the statistics window as a scrollable native dashboard with a fixed header, fixed bottom action bar, metric tiles, real activity bars, app-frequency bars, and wrapped recent-dictation rows. Long history no longer pushes recent entries below the window.
- Added a close action to the statistics window footer so it matches the other utility windows instead of relying only on the window chrome.
- Adjusted dictionary-window spacing so selected-row delete buttons sit below their lists instead of overlapping list borders, and increased the scrollable document height so the correction section is not cramped against the footer.

### Tests
- Full targeted UI regression checks pass for statistics, dictionary, diagnostics, and hotword windows. Computer Use verified the statistics window before and after the fix, including scrolling to recent dictations, and rechecked Settings, Dictionary, Diagnostics copy-report behavior, and fixed footer controls.

## [2.2.3-dev] - 2026-05-07

### Added
- Added a native adaptive-hotword status window from the menubar. The window shows learned terms, active/candidate state, confidence, observation count, last update date, aliases, and app context without requiring the user to open or understand `hotwords.json`.
- Added a Copy Context action that copies only active learned hotwords, making the current ASR adaptation context inspectable without exposing candidates as if they were already trusted.
- Added a Reveal File action that opens the local SpeakType configuration folder or hotword store for power users while keeping the primary experience read-only and automatic.

### Changed
- Replaced the menubar hotword reveal shortcut with the new native status window so adaptive learning remains observable but not manually maintained.
- Tightened the hotword row layout after real macOS testing showed right-side metadata truncation. Status, confidence, observations, date, aliases, and app context now fit as stable multi-line rows.

### Tests
- Full hotword, diagnostics, dictionary, and app-recording targeted tests pass with 48 tests. Computer Use verified the real native hotword window, Copy Context clipboard output, Reveal File behavior, and the corrected non-truncating row layout.

## [2.2.2-dev] - 2026-05-07

### Changed
- Improved the local diagnostics window so long detail text and repair actions use variable-height wrapped rows instead of single-line truncation. Chinese action text now breaks naturally before temporary test commands such as `ollama serve`.
- Expanded and tightened the first-launch setup wizard layout. The wizard now uses wider content columns, right-aligned primary actions, wider status labels, and full-width command boxes so Ollama commands and long model names remain readable.
- Improved setup command copy controls by placing Copy Command below full-width command fields. Long commands such as `ollama pull huihui_ai/qwen3.5-abliterated:9b-Claude` are now visible and still copy the complete command.

### Tests
- Full test suite passes with 443 tests. Computer Use verified Diagnostics, Setup Wizard, Preferences, Dictionary, Statistics, and the recording HUD after the UI changes.

## [2.2.1-dev] - 2026-05-07

### Changed
- Added a menubar hotword status item showing active and learned adaptive hotwords, with a direct reveal action for the local hotword store.
- Added adaptive-hotword controls to Preferences so learning, recognition context, correction promotion, observation time, edit-stability delay, and per-dictation context size can be changed without hand-editing config JSON.
- Redesigned the local diagnostics window from a plain text report into a scannable native checklist with severity color, summary counts, details, and repair actions while preserving copyable plain-text export.
- Added hotword readiness diagnostics covering learning/context state and learned/active counts.
- Improved the recording overlay so it can show when learned hotword context is active for the current dictation.
- Tightened dictionary-window section labels and changed snippet/correction removal to use the selected row instead of deleting the last row.
- Added empty-state rows to the statistics window for no app history and no recent dictations.

### Tests
- Full test suite passes with 443 tests. New coverage includes selected-row deletion in the dictionary window and the hotword/status UI integration paths added in v2.2.1.

## [2.2.0-dev] - 2026-05-07

### Added
- Added an adaptive hotword learning system that starts a short local observation window after successful SpeakType insertions and learns only from edits made to the just-inserted text span.
- Added `HotwordStore` persistence at `~/.speaktype/hotwords.json`, with candidate reinforcement, confidence-based activation, app/scene/language counters, and compact active-context selection.
- Added local Ollama edit analysis for post-insert learning. The model classifies whether a user edit is a reusable ASR term, spelling/capitalization/hyphenation preference, or a non-reusable content/style edit, then returns strict JSON for the app to validate before saving.
- Added conservative fallback learning for obvious technical terms when the local LLM is unavailable.
- Added ASR hotword context wiring for Qwen3-ASR. SpeakType passes active learned hotwords to `mlx_audio.stt.generate.generate_transcription` only when the installed API supports a `context` keyword or accepts arbitrary keyword arguments.
- Added hotword preservation guidance to local polish, translation, and combined polish+translation prompts so learned terms keep exact spelling when they are actually present.

### Changed
- Successful insertions now remain eligible for short-term learning while ordinary typing, pure append-only edits, app switches, unreadable focused inputs, and unchanged inserted spans are ignored.
- High-confidence learned wrong-to-right pairs can be promoted into the existing correction store, while hotwords themselves remain contextual ASR/polish hints rather than unconditional replacements.
- Streaming preview can now receive the same active hotword context as final transcription without changing the rule that preview remains display-only.
- Unverified-but-sent insertions once again show a small status notice while preserving the final inserted text preview.
- Focused input capture now falls back from the system-wide Accessibility focused element to the frontmost application's own `AXFocusedUIElement`, improving insertion verification and post-insert edit observation in apps such as TextEdit.
- README and README_CN now document adaptive hotwords, local-only learning boundaries, and the new configuration keys.

### Tests
- Full test suite passes with 438 tests. New coverage includes hotword persistence and prioritization, edit-span extraction, short-lived edit observation, local model JSON learning analysis, ASR context forwarding, polish hotword preservation prompts, focused Accessibility fallback, and app-level learning/correction promotion.

## [2.1.3] - 2026-04-15

### Added
- Added a local diagnostics window from the menubar. It checks macOS input permissions, microphone discovery, Qwen3-ASR cache/load state, Ollama installation, Ollama service reachability, configured Ollama model availability, and the current focused input target without reading dictated content or uploading anything.
- Added user-facing repair guidance for local readiness failures, including exact Ollama startup choices, `ollama pull` instructions for missing polish models, permission restart guidance, and current-input-field hints.
- Added a v2.1.3 readiness and acceleration design note documenting the local-only constraints, non-goals, and validation expectations.
- Added ASR warmup after Qwen model load, safe streaming-preview transcript reuse, and local Ollama chat-path warmup while recording.

### Changed
- Startup now begins local LLM availability checking and Ollama prewarm in parallel with Qwen3-ASR loading instead of waiting for ASR setup to finish first.
- Paste insertion trims the pasteboard settle delay and checks Accessibility verification immediately before polling, reducing avoidable fast-path insertion latency.
- Accessibility insertion verification now returns immediately when `AXSelectedText` only echoes the attempted text while `AXValue` remains unchanged, avoiding extra waiting on a known false-success path.
- Codex, Claude, Chrome, ChatGPT, Gemini, and similar Electron/browser input targets now use paste-first insertion instead of first attempting Accessibility direct insertion, avoiding a repeated false-success round trip on these editors.
- Routine unverified-but-sent insertions no longer replace the final text preview with a prominent "could not verify" notice. They are still logged and exposed through local diagnostics, while real insertion failures and permission failures remain user-visible.
- Repeated insertions into the same target process now reuse the `AXManualAccessibility` preparation state instead of setting it again before every dictation.
- Streaming preview remains display-only for final insertion quality. The app no longer inserts preview-derived or preview-tail-merged text as the final transcript after testing showed that path could degrade Qwen output quality.
- Streaming preview now adapts its cadence for UI feedback: quiet tails get an earlier preview pass, while longer ongoing recordings back off from fixed full-buffer preview retries.
- Cached Qwen3-ASR models now load through the local HuggingFace snapshot path first, with automatic fallback to the previous model-id load path if the local path is rejected.
- The final ASR input now preserves the full captured audio buffer by default. Testing showed that trimming quiet edges on short Mandarin phrases could remove useful acoustic context and push Qwen toward near-homophones such as "颜色" or "绿色" when the user said "润色".
- Recording-time LLM warmup now uses the same `/api/chat` path as real polish requests and avoids launching a simultaneous generate prewarm.
- Local Ollama polish, translation, and edit requests now use bounded generation budgets for short dictations so the model has less unnecessary token headroom to fill.
- Recording-stop latency logs now separate audio finalization time from processing-thread dispatch time, making release-to-insert delays easier to diagnose.
- Push-to-talk recordings now have a missed-keyup recovery guard. If macOS drops the release event while the physical hotkey is no longer held, SpeakType auto-stops recording and clears the stale hotkey state so the preview overlay cannot stay pinned in a fake recording state. Modifier hotkeys use AppKit's current modifier flags for this guard so holding Right Command is not mistaken for a release.
- README now documents the Local Diagnostics entry and what it can diagnose.

### Tests
- Test count grew to 452. New coverage includes local diagnostics, Ollama install/service/model readiness states, current input target diagnostics, startup LLM/ASR warmup overlap, ASR kernel warmup, local Qwen snapshot loading including symlinked HuggingFace cache files, final-ASR preservation of the full captured buffer, adaptive streaming-preview cadence, final-ASR preference over preview-derived transcripts, missed push-to-talk keyup recovery, modifier-aware release-guard state checks, bounded Ollama generation budgets, Ollama chat prewarm, immediate paste verification, immediate Accessibility verification, paste-first app routing, quieter unverified insertion UX, one-time target process preparation, and focused input inspection.

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
