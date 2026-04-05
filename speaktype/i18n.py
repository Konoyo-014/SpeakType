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
