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
    "notif_llm_unavail_title": {"zh": "LLM 不可用", "en": "LLM Not Available"},
    "notif_llm_unavail_body": {
        "zh": "请运行: ollama pull {model}\n文本润色已禁用。",
        "en": "Run: ollama pull {model}\nText polishing disabled.",
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
    "notif_up_to_date_body": {"zh": "您正在运行最新版本 (v2.0)。", "en": "You are running the latest version (v2.0)."},
    "notif_about_subtitle": {"zh": "v2.0 — Mac AI 语音输入法", "en": "v2.0 — AI Voice Input for Mac"},
    "notif_cannot_test": {"zh": "录音/处理中，无法测试。", "en": "Cannot test while recording/processing."},
    "notif_error": {"zh": "错误", "en": "Error"},

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

    # --- Download status (app.py status bar) ---
    "notif_perm_missing_title": {"zh": "权限缺失", "en": "Missing Permissions"},
    "notif_perm_missing_body": {
        "zh": "SpeakType 缺少以下权限，无法正常工作：{missing}\n请在系统设置中授权。",
        "en": "SpeakType is missing required permissions: {missing}\nPlease grant access in System Settings.",
    },

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
        "zh": "文本润色使用本地大语言模型（通过 Ollama）。\n这是可选功能 — 不安装也能正常使用语音输入。",
        "en": "Text polishing uses a local LLM via Ollama.\nThis is optional — voice input works without it.",
    },
    "wizard_ollama_ok": {"zh": "✓ Ollama 已安装", "en": "✓ Ollama installed"},
    "wizard_ollama_missing": {"zh": "✗ 未检测到 Ollama", "en": "✗ Ollama not detected"},
    "wizard_ollama_install_hint": {"zh": "安装命令：", "en": "Install command:"},
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
