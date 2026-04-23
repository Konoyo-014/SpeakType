"""Internationalization support for SpeakType UI."""

_STRINGS = {
    # --- Menu items (app.py) ---
    "hotkey_prefix": {"zh": "快捷键：", "en": "Hotkey: "},
    "status_init": {"zh": "状态：初始化中...", "en": "Status: Initializing..."},
    "status_loading_asr": {"zh": "状态：加载语音识别模型...", "en": "Status: Loading ASR model..."},
    "status_asr_error": {"zh": "状态：语音识别错误", "en": "Status: ASR Error"},
    "status_ready": {"zh": "状态：就绪 ✓", "en": "Status: Ready ✓"},
    "menu_polish": {"zh": "文本润色", "en": "Polish Text"},
    "menu_voice_cmd": {"zh": "语音指令", "en": "Voice Commands"},
    "menu_context_tone": {"zh": "智能语气", "en": "Context-Aware Tone"},
    "menu_translate": {"zh": "转写后翻译", "en": "Translate After Transcription"},
    "menu_translate_to": {"zh": "翻译目标语言", "en": "Translate To"},
    "menu_dictation_mode": {"zh": "听写模式", "en": "Dictation Mode"},
    "mode_push_to_talk": {"zh": "按住说话", "en": "Push-to-Talk (Hold)"},
    "mode_toggle": {"zh": "按下开关", "en": "Toggle (Press)"},
    "menu_dictation_lang": {"zh": "听写语言", "en": "Dictation Language"},
    "lang_auto": {"zh": "自动检测", "en": "Auto Detect"},
    "menu_audio_device": {"zh": "音频设备", "en": "Audio Device"},
    "device_default": {"zh": "系统默认", "en": "System Default"},
    "menu_preferences": {"zh": "偏好设置...", "en": "Preferences..."},
    "menu_dict_snippets": {"zh": "词典与快捷短语...", "en": "Dictionary & Snippets..."},
    "menu_history_stats": {"zh": "历史与统计", "en": "History & Stats"},
    "menu_diagnostics": {"zh": "本地自检...", "en": "Local Diagnostics..."},
    "menu_test_mic": {"zh": "测试麦克风", "en": "Test Microphone"},
    "menu_open_config": {"zh": "打开配置文件夹", "en": "Open Config Folder"},
    "menu_check_updates": {"zh": "检查更新", "en": "Check for Updates"},
    "menu_about": {"zh": "关于 SpeakType", "en": "About SpeakType"},
    "menu_quit": {"zh": "退出 SpeakType", "en": "Quit SpeakType"},
    "menu_ui_language": {"zh": "界面语言", "en": "UI Language"},

    # --- Notifications (app.py) ---
    "notif_welcome_title": {"zh": "欢迎使用 SpeakType！", "en": "Welcome to SpeakType!"},
    "notif_welcome_subtitle": {"zh": "首次设置", "en": "First-time Setup"},
    "notif_welcome_body": {
        "zh": "按住 {hotkey} 开始听写。\n请在弹出提示时授予麦克风和辅助功能权限。\n使用偏好设置 (⌘,) 自定义选项。",
        "en": "Hold {hotkey} to start dictating.\nGrant Microphone and Accessibility access when prompted.\nUse Preferences (⌘,) to customize settings.",
    },
    "notif_asr_failed": {"zh": "语音识别加载失败", "en": "ASR Load Failed"},
    "notif_llm_unavail_title": {"zh": "文本润色暂时不可用", "en": "Text Polishing Temporarily Unavailable"},
    "notif_llm_unavail_body": {
        "zh": "文本润色已开启，但本地 Ollama 暂时不可用，所以这次已插入原始转写。\n请打开 Ollama 应用，或在终端运行：ollama serve。模型缺失时再运行：ollama pull {model}。",
        "en": "Text polishing is enabled, but local Ollama is temporarily unavailable, so raw transcription was inserted this time.\nOpen the Ollama app or run: ollama serve. If the model is missing, run: ollama pull {model}.",
    },
    "notif_llm_ollama_not_running_body": {
        "zh": "文本润色已开启，但本地 Ollama 没有运行，所以这次已插入原始转写。\n请打开 Ollama 应用；如果你用命令行安装，请在终端运行：ollama serve。随后如果提示模型缺失，再运行：ollama pull {model}。",
        "en": "Text polishing is enabled, but local Ollama is not running, so raw transcription was inserted this time.\nOpen the Ollama app; if you installed it from the command line, run: ollama serve. If the model is still missing, run: ollama pull {model}.",
    },
    "notif_llm_model_missing_body": {
        "zh": "文本润色已开启，但本地 Ollama 找不到模型 {model}，所以这次已插入原始转写。\n请保持 Ollama 运行，然后在终端运行：ollama pull {model}。",
        "en": "Text polishing is enabled, but local Ollama cannot find model {model}, so raw transcription was inserted this time.\nKeep Ollama running, then run: ollama pull {model}.",
    },
    "notif_llm_ollama_timeout_body": {
        "zh": "文本润色已开启，但 Ollama 没有及时响应，所以这次已插入原始转写。\n请确认 Ollama 已打开，地址是 {url}，模型 {model} 已安装。",
        "en": "Text polishing is enabled, but Ollama did not respond in time, so raw transcription was inserted this time.\nMake sure Ollama is open, the URL is {url}, and model {model} is installed.",
    },
    "notif_llm_ollama_unhealthy_body": {
        "zh": "文本润色已开启，但 Ollama 返回异常状态，所以这次已插入原始转写。\n请重启 Ollama 应用，或在终端重新运行：ollama serve。当前地址：{url}，模型：{model}。",
        "en": "Text polishing is enabled, but Ollama returned an unexpected status, so raw transcription was inserted this time.\nRestart the Ollama app or rerun: ollama serve. Current URL: {url}. Model: {model}.",
    },
    "notif_ready_title": {"zh": "就绪！", "en": "Ready!"},
    "notif_ready_body": {
        "zh": "{mode_str} {hotkey} 开始听写。",
        "en": "{mode_str} {hotkey} to dictate.",
    },
    "notif_ready_mode_toggle": {"zh": "切换", "en": "Toggle"},
    "notif_ready_mode_hold": {"zh": "按住", "en": "Hold"},
    "notif_settings_saved_title": {"zh": "设置已保存", "en": "Settings Saved"},
    "notif_settings_saved_body": {"zh": "偏好设置已更新。", "en": "Your preferences have been updated."},
    "notif_mic_test": {"zh": "麦克风测试", "en": "Mic Test"},
    "notif_mic_recording": {"zh": "正在录音 2 秒...", "en": "Recording for 2 seconds..."},
    "notif_mic_ok": {"zh": "✓ 录制了 {size} 字节，麦克风工作正常！", "en": "✓ Recorded {size} bytes. Microphone is working!"},
    "notif_mic_fail": {"zh": "✗ 未录到音频，请检查麦克风权限。", "en": "✗ No audio captured. Check microphone permissions."},
    "notif_config_reloaded": {"zh": "配置已重载", "en": "Config Reloaded"},
    "notif_config_reloaded_body": {"zh": "设置已更新。", "en": "Settings updated."},
    "notif_up_to_date_title": {"zh": "已是最新版本", "en": "Up to Date"},
    "notif_up_to_date_body": {"zh": "您正在运行最新版本 (v{version})。", "en": "You are running the latest version (v{version})."},
    "notif_update_available_title": {"zh": "发现新版本", "en": "Update Available"},
    "notif_update_available_body": {
        "zh": "新版本 v{latest} 已发布（当前 v{current}）。在菜单中点击「打开发布页」获取下载。",
        "en": "Version v{latest} is available (you have v{current}). Use the menu to open the release page.",
    },
    "notif_update_check_failed_title": {"zh": "更新检查失败", "en": "Update Check Failed"},
    "notif_update_check_failed_body": {"zh": "无法连接到发布服务器：{error}", "en": "Could not reach the release server: {error}"},
    "notif_about_subtitle": {"zh": "v{version} — Mac AI 语音输入法", "en": "v{version} — AI Voice Input for Mac"},
    "notif_cannot_test": {"zh": "录音/处理中，无法测试。", "en": "Cannot test while recording/processing."},
    "notif_error": {"zh": "错误", "en": "Error"},
    "notif_insert_failed_title": {"zh": "插入失败", "en": "Insertion Failed"},
    "notif_insert_failed_body": {
        "zh": "SpeakType 没能把文本插入到 {app}。{hint}",
        "en": "SpeakType could not insert text into {app}. {hint}",
    },
    "insert_hint_post_event": {
        "zh": "系统拒绝模拟输入。请在系统设置中重新授权输入监控，然后重启 SpeakType。",
        "en": "macOS rejected synthetic input. Re-grant Input Monitoring in System Settings, then restart SpeakType.",
    },
    "insert_hint_focus": {
        "zh": "没有检测到可写输入框。请点击目标输入框后重试。",
        "en": "No writable focused input was detected. Click the target text field and try again.",
    },
    "insert_hint_not_writable": {
        "zh": "目标输入框没有确认接收文本。请点回可编辑输入框后重试；网页聊天框可能需要重新聚焦。",
        "en": "The target input did not confirm that it accepted text. Refocus the editable field and try again; web chat boxes may need a fresh click.",
    },
    "insert_hint_generic": {
        "zh": "请确认目标窗口仍在前台，并确认辅助功能与输入监控权限已授权。",
        "en": "Make sure the target window is still focused and Accessibility/Input Monitoring permissions are granted.",
    },
    "overlay_insert_failed": {
        "zh": "插入失败：{app} 没有接收文本",
        "en": "Insertion failed: {app} did not receive text",
    },
    "overlay_insert_unverified": {
        "zh": "已发送到 {app}，但无法确认文本已进入输入框",
        "en": "Sent to {app}, but text insertion could not be verified",
    },
    "overlay_insert_unverified_llm_skipped": {
        "zh": "已发送原始转写到 {app}，但无法确认输入框已接收",
        "en": "Sent raw transcription to {app}, but insertion could not be verified",
    },
    "overlay_llm_skipped_raw": {
        "zh": "润色/翻译已临时跳过，已插入原始转写",
        "en": "Polish/translation was temporarily skipped; inserted raw transcription",
    },
    "overlay_llm_ollama_not_running_raw": {
        "zh": "Ollama 未运行，已插入原始转写。打开 Ollama 应用，或运行：ollama serve",
        "en": "Ollama is not running; inserted raw transcription. Open the Ollama app or run: ollama serve",
    },
    "overlay_llm_model_missing_raw": {
        "zh": "Ollama 缺少模型，已插入原始转写。运行：ollama pull {model}",
        "en": "Ollama model is missing; inserted raw transcription. Run: ollama pull {model}",
    },
    "overlay_llm_ollama_timeout_raw": {
        "zh": "Ollama 响应超时，已插入原始转写。确认 Ollama 已打开后重试",
        "en": "Ollama timed out; inserted raw transcription. Make sure Ollama is open and try again",
    },
    "overlay_llm_ollama_unhealthy_raw": {
        "zh": "Ollama 状态异常，已插入原始转写。重启 Ollama 后重试",
        "en": "Ollama returned an error; inserted raw transcription. Restart Ollama and try again",
    },
    "overlay_asr_loading": {
        "zh": "正在加载本地语音识别模型，首次启动可能需要一两分钟…",
        "en": "Loading the local speech recognition model. First launch can take a minute or two…",
    },
    "overlay_finalizing_preview": {
        "zh": "正在生成最终文本，实时预览可能会被校正",
        "en": "Finalizing transcription; the live preview may be corrected",
    },
    "overlay_empty_transcription": {
        "zh": "没有识别到文字：请再说一次",
        "en": "No words were recognized. Please try again.",
    },
    "overlay_no_audio": {
        "zh": "没有录到声音：请检查麦克风或输入设备",
        "en": "No audio was captured. Check the microphone or input device.",
    },
    "overlay_audio_too_short": {
        "zh": "录音太短：请按住快捷键后再开始说话",
        "en": "Recording was too short. Hold the hotkey before speaking.",
    },
    "overlay_audio_too_quiet": {
        "zh": "声音太小：请靠近麦克风或换输入设备",
        "en": "Audio was too quiet. Move closer to the microphone or choose another input.",
    },
    "overlay_mic_start_failed": {
        "zh": "麦克风打不开：请检查权限或输入设备",
        "en": "Could not open microphone. Check permissions or the input device.",
    },
    "overlay_processing_failed": {
        "zh": "处理失败：请查看通知或日志",
        "en": "Processing failed. Check the notification or log.",
    },

    # --- Local diagnostics (diagnostics.py / diagnostics_window.py) ---
    "diag_window_title": {"zh": "SpeakType 本地自检", "en": "SpeakType Local Diagnostics"},
    "diag_window_heading": {"zh": "本地运行状态", "en": "Local Runtime Status"},
    "diag_window_subtitle": {
        "zh": "只检查本机状态，不读取或上传听写内容。",
        "en": "Checks local state only. Dictation content is not read or uploaded.",
    },
    "diag_running": {"zh": "正在检查本地状态...", "en": "Checking local state..."},
    "diag_failed": {"zh": "自检失败：{error}", "en": "Diagnostics failed: {error}"},
    "diag_refresh": {"zh": "刷新", "en": "Refresh"},
    "diag_copy": {"zh": "复制报告", "en": "Copy Report"},
    "diag_close": {"zh": "关闭", "en": "Close"},
    "diag_report_header": {"zh": "SpeakType 本地自检报告", "en": "SpeakType Local Diagnostics Report"},
    "diag_action_prefix": {"zh": "建议：", "en": "Action:"},
    "diag_unknown_app": {"zh": "未知应用", "en": "Unknown app"},
    "diag_permissions_title": {"zh": "macOS 权限", "en": "macOS Permissions"},
    "diag_permissions_ok": {"zh": "辅助功能、输入监控和模拟按键权限都可用。", "en": "Accessibility, hotkey listening, and synthetic input permissions are available."},
    "diag_permissions_missing": {"zh": "缺少权限：{missing}。", "en": "Missing permissions: {missing}."},
    "diag_permissions_error": {"zh": "无法读取权限状态：{error}", "en": "Could not read permission state: {error}"},
    "diag_permissions_action": {
        "zh": "打开系统设置 > 隐私与安全性，授权后重启 SpeakType。",
        "en": "Open System Settings > Privacy & Security, grant access, then restart SpeakType.",
    },
    "diag_microphone_title": {"zh": "麦克风", "en": "Microphone"},
    "diag_microphone_ok": {"zh": "检测到 {count} 个输入设备。", "en": "Found {count} input device(s)."},
    "diag_microphone_missing": {"zh": "没有检测到可用输入设备。", "en": "No usable input device was found."},
    "diag_microphone_error": {"zh": "无法读取麦克风设备：{error}", "en": "Could not read microphone devices: {error}"},
    "diag_microphone_action": {"zh": "检查麦克风权限，或在菜单栏选择另一个输入设备。", "en": "Check microphone permission, or choose another input device from the menubar."},
    "diag_asr_title": {"zh": "本地语音识别模型", "en": "Local ASR Model"},
    "diag_asr_loaded": {"zh": "Qwen3-ASR 已加载：{model}", "en": "Qwen3-ASR is loaded: {model}"},
    "diag_asr_cached": {"zh": "Qwen3-ASR 已缓存，下一次加载不需要重新下载：{model}", "en": "Qwen3-ASR is cached and does not need to download again: {model}"},
    "diag_asr_not_cached": {"zh": "Qwen3-ASR 尚未缓存，首次使用会下载模型：{model}", "en": "Qwen3-ASR is not cached yet. First use will download: {model}"},
    "diag_asr_cache_error": {"zh": "无法确认 ASR 缓存状态：{error}", "en": "Could not confirm ASR cache state: {error}"},
    "diag_asr_action": {"zh": "保持网络可用后开始一次听写，或等待启动加载完成。", "en": "Keep the network available and start one dictation, or wait for startup loading to finish."},
    "diag_ollama_install_title": {"zh": "Ollama 安装", "en": "Ollama Installation"},
    "diag_ollama_install_ok": {"zh": "已找到 Ollama：{path}", "en": "Found Ollama: {path}"},
    "diag_ollama_install_missing": {"zh": "没有检测到 Ollama 命令行工具或桌面应用命令。", "en": "Could not find the Ollama command-line tool or app command."},
    "diag_ollama_install_action": {"zh": "安装 Ollama，或运行：brew install ollama", "en": "Install Ollama, or run: brew install ollama"},
    "diag_ollama_service_title": {"zh": "Ollama 本地服务", "en": "Ollama Local Service"},
    "diag_ollama_service_ok": {"zh": "Ollama 正在运行：{url}", "en": "Ollama is running: {url}"},
    "diag_ollama_service_missing": {"zh": "无法连接到 Ollama：{url}", "en": "Could not connect to Ollama: {url}"},
    "diag_ollama_service_missing_with_brew": {"zh": "无法连接到 Ollama；Homebrew 服务状态：{service}", "en": "Could not connect to Ollama. Homebrew service state: {service}"},
    "diag_ollama_service_missing_without_install": {"zh": "Ollama 未安装，因此本地服务不可用：{url}", "en": "Ollama is not installed, so the local service is unavailable: {url}"},
    "diag_ollama_service_error": {"zh": "Ollama 返回异常：{error}", "en": "Ollama returned an error: {error}"},
    "diag_ollama_service_action": {
        "zh": "打开 Ollama.app，或运行：brew services start ollama。临时测试可运行：ollama serve",
        "en": "Open Ollama.app, or run: brew services start ollama. For temporary testing, run: ollama serve",
    },
    "diag_ollama_model_title": {"zh": "Ollama 润色模型", "en": "Ollama Polish Model"},
    "diag_ollama_model_ok": {"zh": "已找到模型：{model}", "en": "Found model: {model}"},
    "diag_ollama_model_missing": {"zh": "Ollama 正在运行，但缺少模型：{model}", "en": "Ollama is running, but model is missing: {model}"},
    "diag_ollama_model_skipped": {"zh": "服务不可用，暂时无法检查模型：{model}", "en": "Service is unavailable, so the model cannot be checked yet: {model}"},
    "diag_ollama_model_action": {"zh": "保持 Ollama 运行，然后执行：ollama pull {model}", "en": "Keep Ollama running, then run: ollama pull {model}"},
    "diag_target_title": {"zh": "当前输入目标", "en": "Current Input Target"},
    "diag_target_ok": {"zh": "{app} 的当前焦点看起来可接收文本，控件类型：{role}", "en": "The current focus in {app} appears text-ready. Role: {role}"},
    "diag_target_no_focus": {"zh": "{app} 当前没有可读取的焦点输入控件。", "en": "{app} does not expose a focused input control right now."},
    "diag_target_not_writable": {"zh": "{app} 的当前焦点不确定是否可写，控件类型：{role}", "en": "The current focus in {app} may not be writable. Role: {role}"},
    "diag_target_post_event_denied": {"zh": "{app} 需要模拟按键权限才能插入文本。", "en": "{app} needs synthetic input permission for text insertion."},
    "diag_target_error": {"zh": "无法检查 {app} 的当前输入目标：{error}", "en": "Could not inspect the current input target in {app}: {error}"},
    "diag_target_action": {"zh": "点击一个可编辑输入框后刷新自检。", "en": "Click an editable text field, then refresh diagnostics."},

    # --- Settings window (settings_window.py) ---
    "settings_title": {"zh": "SpeakType 偏好设置", "en": "SpeakType Settings"},
    "settings_section_general": {"zh": "通用", "en": "General"},
    "settings_section_ai": {"zh": "AI 模型", "en": "AI Models"},
    "settings_section_features": {"zh": "功能", "en": "Features"},
    "settings_section_plugins": {"zh": "插件", "en": "Plugins"},
    "settings_section_system": {"zh": "系统", "en": "System"},
    "settings_hotkey": {"zh": "快捷键：", "en": "Hotkey:"},
    "settings_dictation_mode": {"zh": "听写模式：", "en": "Dictation Mode:"},
    "settings_language": {"zh": "听写语言：", "en": "Dictation Language:"},
    "settings_insert_method": {"zh": "输入方式：", "en": "Insert Method:"},
    "settings_audio_device": {"zh": "音频设备：", "en": "Audio Device:"},
    "settings_ui_language": {"zh": "界面语言：", "en": "UI Language:"},
    "settings_asr_backend": {"zh": "语音识别后端：", "en": "ASR Backend:"},
    "settings_qwen_model": {"zh": "Qwen ASR 模型：", "en": "Qwen ASR Model:"},
    "settings_whisper_model": {"zh": "Whisper 模型：", "en": "Whisper Model:"},
    "settings_llm_model": {"zh": "大语言模型：", "en": "LLM Model:"},
    "settings_ollama_url": {"zh": "Ollama 地址：", "en": "Ollama URL:"},
    "settings_cb_polish": {"zh": "启用文本润色 (LLM)", "en": "Enable Text Polishing (LLM)"},
    "settings_cb_voice_cmd": {"zh": "启用语音指令", "en": "Enable Voice Commands"},
    "settings_cb_tone": {"zh": "智能语气", "en": "Context-Aware Tone"},
    "settings_cb_sound": {"zh": "声音反馈", "en": "Sound Feedback"},
    "settings_cb_history": {"zh": "保存听写历史", "en": "Save Dictation History"},
    "settings_cb_translate": {"zh": "转写后翻译", "en": "Translate After Transcription"},
    "settings_translate_to": {"zh": "翻译目标语言：", "en": "Translate To:"},
    "settings_cb_streaming": {"zh": "录音时显示实时预览浮窗", "en": "Show Live Preview While Recording"},
    "settings_cb_plugins": {"zh": "启用插件系统", "en": "Enable Plugin System"},
    "settings_cb_auto_start": {"zh": "登录时启动", "en": "Start at Login"},
    "settings_btn_save": {"zh": "保存", "en": "Save"},
    "settings_btn_cancel": {"zh": "取消", "en": "Cancel"},
    "settings_insert_paste": {"zh": "粘贴 (⌘V) — 快速", "en": "Paste (Cmd+V) — Fast"},
    "settings_insert_type": {"zh": "逐字输入 — 兼容", "en": "Keystroke — Compatible"},

    # Hotkey display names
    "hotkey_right_cmd": {"zh": "右 ⌘（按住）", "en": "Right ⌘ (Hold)"},
    "hotkey_left_cmd": {"zh": "左 ⌘（按住）", "en": "Left ⌘ (Hold)"},
    "hotkey_right_alt": {"zh": "右 ⌥（按住）", "en": "Right ⌥ (Hold)"},
    "hotkey_right_ctrl": {"zh": "右 ⌃（按住）", "en": "Right ⌃ (Hold)"},
    "hotkey_ctrl_shift_space": {"zh": "⌃⇧Space（按住）", "en": "⌃⇧Space (Hold)"},
    "hotkey_f5": {"zh": "F5（按住）", "en": "F5 (Hold)"},
    "hotkey_f6": {"zh": "F6（按住）", "en": "F6 (Hold)"},

    # Dictation mode options
    "mode_opt_push": {"zh": "按住说话", "en": "Push-to-Talk (Hold key)"},
    "mode_opt_toggle": {"zh": "按下开关", "en": "Toggle (Press to start/stop)"},

    # UI language options
    "ui_lang_zh": {"zh": "中文", "en": "中文 (Chinese)"},
    "ui_lang_en": {"zh": "English", "en": "English"},

    # --- Stats window (stats_window.py) ---
    "stats_title": {"zh": "SpeakType — 听写统计", "en": "SpeakType — Dictation Statistics"},
    "stats_overview": {"zh": "概览", "en": "Overview"},
    "stats_total": {"zh": "总听写次数", "en": "Total Dictations"},
    "stats_words": {"zh": "总字数", "en": "Total Words"},
    "stats_duration": {"zh": "总时长", "en": "Total Duration"},
    "stats_avg_words": {"zh": "平均字数/次", "en": "Avg Words / Dictation"},
    "stats_avg_dur": {"zh": "平均时长/次", "en": "Avg Duration / Dictation"},
    "stats_activity": {"zh": "活动（最近 7 天）", "en": "Activity (Last 7 Days)"},
    "stats_top_apps": {"zh": "常用应用", "en": "Top Apps"},
    "stats_recent": {"zh": "最近听写", "en": "Recent Dictations"},
    "stats_btn_export": {"zh": "导出历史…", "en": "Export History\u2026"},
    "stats_export_done_title": {"zh": "导出完成", "en": "Export Complete"},
    "stats_export_done_body": {"zh": "已写入：{path}", "en": "Saved to: {path}"},
    "stats_export_failed_title": {"zh": "导出失败", "en": "Export Failed"},
    "stats_export_failed_body": {"zh": "{error}", "en": "{error}"},

    # --- Dictionary window (dict_window.py) ---
    "dict_title": {"zh": "SpeakType — 词典与快捷短语", "en": "SpeakType — Dictionary & Snippets"},
    "dict_section_words": {"zh": "自定义词典（确保正确识别的词语）", "en": "Custom Dictionary (words to always recognize correctly)"},
    "dict_section_snippets": {"zh": "快捷短语（说出触发词插入文本）", "en": "Snippets (say trigger phrase to insert text)"},
    "dict_placeholder_word": {"zh": "输入词语...", "en": "Enter a word or phrase..."},
    "dict_btn_add": {"zh": "添加", "en": "Add"},
    "dict_btn_remove": {"zh": "删除", "en": "Remove"},
    "dict_trigger": {"zh": "触发词：", "en": "Trigger:"},
    "dict_text": {"zh": "文本：", "en": "Text:"},
    "dict_placeholder_trigger": {"zh": "例如：我的邮箱", "en": "e.g., my email"},
    "dict_placeholder_text": {"zh": "例如：user@mail.com", "en": "e.g., user@mail.com"},
    "dict_btn_remove_selected": {"zh": "删除选中", "en": "Remove Selected"},
    "dict_btn_save": {"zh": "保存", "en": "Save"},
    "dict_btn_close": {"zh": "关闭", "en": "Close"},
    "dict_no_words": {"zh": "（无自定义词语）", "en": "(no custom words)"},
    "dict_no_snippets": {"zh": "（无快捷短语）", "en": "(no snippets)"},
    "dict_section_corrections": {
        "zh": "听写纠错（识别错误自动替换）",
        "en": "Corrections (replace mistranscribed phrases automatically)",
    },
    "dict_correction_wrong": {"zh": "识别为：", "en": "Heard:"},
    "dict_correction_right": {"zh": "改写为：", "en": "Replace with:"},
    "dict_correction_placeholder_wrong": {"zh": "例如：PI thon", "en": "e.g., PI thon"},
    "dict_correction_placeholder_right": {"zh": "例如：Python", "en": "e.g., Python"},
    "dict_no_corrections": {"zh": "（无纠错条目）", "en": "(no corrections)"},

    # --- Download status (app.py status bar) ---
    "notif_perm_missing_title": {"zh": "权限缺失", "en": "Missing Permissions"},
    "notif_perm_missing_body": {
        "zh": "请在系统设置里授权：{missing}。授权后重启 SpeakType。",
        "en": "Grant {missing} in System Settings, then restart SpeakType.",
    },
    "perm_name_accessibility": {"zh": "辅助功能", "en": "Accessibility"},
    "perm_name_input_monitoring": {"zh": "输入监控（监听热键）", "en": "Input Monitoring (hotkey listening)"},
    "perm_name_post_event": {"zh": "输入监控（模拟按键）", "en": "Input Monitoring (synthetic input)"},
    "perm_restart_title": {"zh": "需要重启以完成权限更新", "en": "Restart Required for Permissions"},
    "perm_restart_body": {
        "zh": "如果你刚完成授权，请重启 SpeakType，让热键和插入功能在当前版本里生效。",
        "en": "If you just granted permissions, restart SpeakType so hotkeys and insertion take effect in this build.",
    },
    "perm_restart_now": {"zh": "立即重启", "en": "Restart Now"},
    "perm_restart_later": {"zh": "稍后", "en": "Later"},

    "status_downloading_asr": {"zh": "下载语音模型 {pct:.0f}% ({size})", "en": "Downloading ASR {pct:.0f}% ({size})"},
    "status_loading_model": {"zh": "状态：加载模型中...", "en": "Status: Loading model..."},

    # --- Setup wizard (setup_wizard.py) ---
    "wizard_title": {"zh": "SpeakType 初始设置", "en": "SpeakType Setup"},
    "wizard_welcome_title": {"zh": "欢迎使用 SpeakType", "en": "Welcome to SpeakType"},
    "wizard_welcome_body": {
        "zh": "SpeakType 是一款 Mac 本地 AI 语音输入法。\n按住快捷键说话，润色后的文字即刻出现在光标处。\n\n接下来我们将完成几项初始设置。",
        "en": "SpeakType is an on-device AI voice input method for Mac.\nHold a key, speak, and polished text appears at the cursor.\n\nLet's walk through a few setup steps.",
    },
    "wizard_btn_start": {"zh": "开始设置", "en": "Get Started"},
    "wizard_btn_next": {"zh": "下一步", "en": "Next"},
    "wizard_btn_skip": {"zh": "跳过", "en": "Skip"},
    "wizard_btn_done": {"zh": "开始使用 SpeakType", "en": "Start Using SpeakType"},
    "wizard_btn_refresh": {"zh": "刷新状态", "en": "Refresh"},
    "wizard_btn_open_settings": {"zh": "打开系统设置", "en": "Open System Settings"},
    "wizard_btn_copy": {"zh": "复制命令", "en": "Copy Command"},

    "wizard_step_permissions": {"zh": "权限设置", "en": "Permissions"},
    "wizard_step_asr": {"zh": "语音识别模型", "en": "Speech Recognition Model"},
    "wizard_step_llm": {"zh": "文本润色（可选）", "en": "Text Polishing (Optional)"},
    "wizard_step_complete": {"zh": "设置完成", "en": "Setup Complete"},

    "wizard_mic_label": {"zh": "麦克风权限", "en": "Microphone Access"},
    "wizard_access_label": {"zh": "辅助功能权限", "en": "Accessibility Access"},
    "wizard_perm_ok": {"zh": "✓ 已授权", "en": "✓ Granted"},
    "wizard_perm_missing": {"zh": "✗ 未授权", "en": "✗ Not Granted"},
    "wizard_perm_body": {
        "zh": "SpeakType 需要以下权限才能正常工作：\n• 麦克风 — 录制语音\n• 辅助功能 — 在光标处插入文字",
        "en": "SpeakType needs these permissions to work:\n• Microphone — to record your voice\n• Accessibility — to insert text at the cursor",
    },

    "wizard_asr_body": {
        "zh": "首次使用需要下载语音识别模型（约 2 GB）。\n下载完成后将自动缓存，之后无需再次下载。",
        "en": "A speech recognition model (~2 GB) needs to be downloaded.\nIt will be cached locally after the first download.",
    },
    "wizard_asr_cached": {"zh": "✓ 模型已缓存，无需下载", "en": "✓ Model cached, no download needed"},
    "wizard_asr_downloading": {"zh": "正在下载... {pct:.0f}% ({size})", "en": "Downloading... {pct:.0f}% ({size})"},
    "wizard_asr_done": {"zh": "✓ 下载完成", "en": "✓ Download complete"},
    "wizard_asr_error": {"zh": "✗ 下载失败：{error}", "en": "✗ Download failed: {error}"},

    "wizard_llm_body": {
        "zh": "文本润色完全在本机通过 Ollama 运行。\n如果 Ollama 没有启动，SpeakType 会先插入原始转写，并告诉你怎么启动。",
        "en": "Text polishing runs fully on this Mac through Ollama.\nIf Ollama is not running, SpeakType inserts raw transcription first and tells you how to start it.",
    },
    "wizard_ollama_ok": {"zh": "✓ Ollama 已安装", "en": "✓ Ollama installed"},
    "wizard_ollama_missing": {"zh": "✗ 未检测到 Ollama", "en": "✗ Ollama not detected"},
    "wizard_ollama_install_hint": {"zh": "安装命令：", "en": "Install command:"},
    "wizard_ollama_running_ok": {"zh": "✓ Ollama 正在运行", "en": "✓ Ollama running"},
    "wizard_ollama_running_missing": {"zh": "✗ Ollama 未运行", "en": "✗ Ollama not running"},
    "wizard_ollama_start_hint": {"zh": "启动方式：打开 Ollama 应用，或运行命令：", "en": "Start Ollama by opening the app, or run:"},
    "wizard_model_ok": {"zh": "✓ LLM 模型已就绪", "en": "✓ LLM model ready"},
    "wizard_model_missing": {"zh": "✗ 未检测到 LLM 模型", "en": "✗ LLM model not found"},
    "wizard_model_pull_hint": {"zh": "拉取命令：", "en": "Pull command:"},

    "wizard_complete_body": {
        "zh": "初始设置已完成！\n\n按住 {hotkey} 开始语音输入。\n可在菜单栏点击 🎙 图标进入偏好设置。",
        "en": "Setup is complete!\n\nHold {hotkey} to start dictating.\nClick the 🎙 icon in the menubar for preferences.",
    },
}

_current_lang = "zh"


def set_language(lang: str):
    """Set the UI language. Accepts 'zh' or 'en'."""
    global _current_lang
    _current_lang = lang if lang in ("zh", "en") else "zh"


def get_language() -> str:
    return _current_lang


def t(key: str, **kwargs) -> str:
    """Get a translated string by key. Supports {placeholder} formatting."""
    entry = _STRINGS.get(key)
    if not entry:
        return key
    text = entry.get(_current_lang, entry.get("en", key))
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text
