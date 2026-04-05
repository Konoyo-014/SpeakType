# SpeakType

[English](README.md)

**macOS 本地语音输入法。** 按住快捷键，说话，润色后的文字即刻出现在光标处 -- 适用于任何应用程序。

> 语音识别基于 Apple Silicon 上的 Qwen3-ASR，文本润色基于 Ollama 本地推理。无云端 API，数据不离开你的 Mac。

## 功能特性

- **按住说话与切换听写** -- 按住右 Command（可自定义）进行录音；松开即转写并插入文字
- **AI 文本润色** -- 去除语气词、修正语法、保持语气风格（由本地 LLM 通过 Ollama 驱动）
- **实时流式预览** -- 浮动窗口实时显示转写内容
- **上下文感知语气** -- 根据当前活跃应用自动调整正式程度（邮件 vs Slack vs 代码编辑器）
- **转写后翻译** -- 支持翻译为英语、中文、日语、韩语、西班牙语、法语或德语
- **语音指令** -- 说"换行"、"句号"、"缩短"、"修正语法"、"翻译成英文"等
- **Whisper 兼容** -- 可在 Qwen3-ASR 和 OpenAI Whisper 后端之间切换
- **音频设备选择** -- 从菜单栏选择麦克风
- **自定义词典与文本片段** -- 定义始终正确识别的词语；设置触发短语快速插入文本
- **插件系统** -- 使用 Python 插件扩展功能（`~/.speaktype/plugins/`）
- **听写历史与统计** -- 内置使用分析面板
- **原生 macOS 菜单栏应用** -- 无 Electron，无 Dock 图标

## 快速开始

### 前置要求

- macOS 13+（Ventura 或更高版本），Apple Silicon（M1/M2/M3/M4）
- Python 3.10
- Ollama（可选，用于文本润色）
- 约 4 GB 磁盘空间（用于 ASR 和 LLM 模型）

### 安装步骤

**1. 克隆仓库**

```bash
git clone https://github.com/speaktype/speaktype.git
cd speaktype
```

**2. 创建虚拟环境并安装依赖**

```bash
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**3. 安装 Ollama 并拉取 LLM 模型（可选，用于文本润色）**

```bash
brew install ollama
ollama serve &
ollama pull huihui_ai/qwen3.5-abliterated:9b-Claude
```

文本润色是可选功能。不安装 Ollama 时，SpeakType 会直接插入原始转写文本。

**4. 运行 SpeakType**

```bash
python main.py
```

首次启动时，macOS 会请求以下权限：
- **麦克风权限** -- 用于语音录制
- **辅助功能权限** -- 用于通过键盘模拟插入文字

请在 **系统设置 > 隐私与安全性** 中授予这两项权限。

### 关于 ASR 模型

语音识别模型（`mlx-community/Qwen3-ASR-1.7B-8bit`）会在首次运行时由 mlx-audio 从 HuggingFace 自动下载（约 2 GB）。

**中国大陆用户：** HuggingFace 在大陆无法直接访问，请设置镜像后再启动：

```bash
export HF_ENDPOINT=https://hf-mirror.com
python main.py
```

建议将此环境变量写入 `~/.zshrc` 以永久生效：

```bash
echo 'export HF_ENDPOINT=https://hf-mirror.com' >> ~/.zshrc
source ~/.zshrc
```

Ollama 模型下载如遇网络问题，可尝试设置代理：

```bash
export HTTPS_PROXY=http://127.0.0.1:7890  # 替换为你的代理地址
ollama pull huihui_ai/qwen3.5-abliterated:9b-Claude
```

### 构建 .app 包（可选）

```bash
source venv/bin/activate
python setup.py py2app --alias
```

应用包将创建在 `dist/SpeakType.app`。

## 使用方法

### 基本听写

| 操作 | 方法 |
|---|---|
| 听写（按住说话） | 按住右 Command，说话，松开 |
| 听写（切换模式） | 按一次右 Command 开始，再按一次停止 |
| 更改快捷键 | 偏好设置 > 快捷键 |

### 语音指令

**标点与结构**（在听写过程中直接说出）：

| 指令 | 结果 |
|---|---|
| "句号" / "period" | 。 / . |
| "逗号" / "comma" | ， / , |
| "问号" / "question mark" | ？ / ? |
| "感叹号" / "exclamation mark" | ！ / ! |
| "冒号" / "分号" | ： / ； |
| "换行" / "新行" | 换行 |
| "新段落" / "下一段" | 双换行 |

**编辑指令**（先选中文本，再说出指令）：

| 指令 | 效果 |
|---|---|
| "缩短" / "make it shorter" | 精简所选文本 |
| "正式一点" / "make it more formal" | 调整为正式语气 |
| "随意一点" / "make it more casual" | 调整为随意语气 |
| "修正语法" / "fix grammar" | 修正语法错误 |
| "翻译成[语言]" / "translate to [language]" | 翻译所选内容 |
| "总结一下" / "summarize this" | 总结所选内容 |
| "回复" / "create a reply" | 针对所选内容起草回复 |

### 文本润色

当 Ollama 运行并加载了 LLM 模型时，SpeakType 会自动润色转写结果：去除语气词、修正语法、根据当前应用调整语气。可从菜单栏开关此功能。

### 翻译

从菜单栏启用转写后翻译。支持的目标语言：英语、中文、日语、韩语、西班牙语、法语、德语。翻译过程中会保留专业术语。

### 文本片段

定义触发短语，说出即可展开为预设文本。例如，说"我的邮箱"即可插入你的邮箱地址。从菜单栏的"词典与片段"管理。

## 配置

所有设置存储在 `~/.speaktype/config.json`。可通过偏好设置窗口（Command+,）或直接编辑文件修改。

主要配置项：

| 设置项 | 默认值 | 说明 |
|---|---|---|
| `hotkey` | `"right_cmd"` | 按住说话快捷键。选项：`right_cmd`、`left_cmd`、`fn`、`right_alt`、`right_ctrl`、`ctrl+shift+space`、`f5`、`f6` |
| `dictation_mode` | `"push_to_talk"` | `"push_to_talk"`（按住说话）或 `"toggle"`（按下切换） |
| `asr_backend` | `"qwen"` | `"qwen"`（Qwen3-ASR via mlx-audio）或 `"whisper"`（OpenAI Whisper） |
| `asr_model` | `"mlx-community/Qwen3-ASR-1.7B-8bit"` | Qwen ASR 的 HuggingFace 模型 ID |
| `llm_model` | `"huihui_ai/qwen3.5-abliterated:9b-Claude"` | 用于文本润色的 Ollama 模型 |
| `ollama_url` | `"http://localhost:11434"` | Ollama API 地址 |
| `polish_enabled` | `true` | 启用/禁用 LLM 文本润色 |
| `language` | `"auto"` | ASR 语言：`"auto"`、`"en"`、`"zh"`、`"ja"`、`"ko"` |
| `translate_enabled` | `false` | 启用转写后翻译 |
| `translate_target` | `"en"` | 翻译目标语言 |
| `streaming_preview` | `false` | 显示实时转写浮动窗口 |
| `voice_commands_enabled` | `true` | 启用语音指令处理 |
| `context_aware_tone` | `true` | 根据应用调整润色语气 |
| `insert_method` | `"paste"` | `"paste"`（剪贴板 + Cmd+V）或 `"type"`（逐字输入） |
| `plugins_enabled` | `false` | 启用插件系统 |
| `max_recording_seconds` | `360` | 最长录音时间（6 分钟） |
| `sound_feedback` | `true` | 录音开始/停止时播放提示音 |

### 自定义词典

添加 ASR 应始终正确识别的词语。存储在 `~/.speaktype/custom_dictionary.json`。通过菜单栏的"词典与片段"管理。

## 插件系统

将 `.py` 文件放入 `~/.speaktype/plugins/` 目录，并在偏好设置中启用插件。

### 可用钩子

| 钩子 | 签名 | 用途 |
|---|---|---|
| `pre_transcribe` | `(audio_path) -> audio_path` | 在 ASR 之前修改音频 |
| `post_transcribe` | `(raw_text) -> text` | 在 ASR 之后修改文本 |
| `pre_polish` | `(text, tone) -> (text, tone)` | 在 LLM 润色之前修改文本/语气 |
| `post_polish` | `(polished_text) -> text` | 在 LLM 润色之后修改文本 |
| `pre_insert` | `(text) -> text or None` | 修改或跳过插入（返回 None 跳过） |
| `post_insert` | `(text) -> None` | 插入后的副作用操作 |
| `on_recording_start` | `() -> None` | 通知：录音开始 |
| `on_recording_stop` | `() -> None` | 通知：录音停止 |

### 插件示例

```python
# ~/.speaktype/plugins/filler_remover.py
PLUGIN_NAME = "Filler Remover"
PLUGIN_VERSION = "1.0"

def post_transcribe(text):
    """在 ASR 转写后去除语气词。"""
    for filler in ["um", "uh", "like", "you know"]:
        text = text.replace(f" {filler} ", " ")
    return text
```

以 `_` 开头的插件文件（如 `_example_plugin.py`）会被忽略。

## 架构

```
按下快捷键
  -> 录制音频 (sounddevice)
  -> ASR: Qwen3-ASR via mlx-audio（或 Whisper）
  -> 语音指令检测 / 片段匹配
  -> LLM 润色 via Ollama（可选）
  -> 翻译（可选）
  -> 在光标处插入文字 (CGEvent + NSPasteboard)
```

所有处理均在本地设备上运行。音频文件在转写完成后立即删除。

**核心组件：**

- **ASR**：`mlx-community/Qwen3-ASR-1.7B-8bit`，通过 mlx-audio 运行，支持 Whisper 回退
- **LLM**：`huihui_ai/qwen3.5-abliterated:9b-Claude`，通过 Ollama 本地推理
- **文字插入**：CGEvent 键盘模拟 + NSPasteboard 剪贴板
- **界面**：rumps（NSStatusItem 菜单栏）、AppKit（原生设置窗口）

## 常见问题

### SpeakType 没有出现在菜单栏

请确保已授予辅助功能权限。前往 **系统设置 > 隐私与安全性 > 辅助功能**，添加 SpeakType（如果从源码运行，则添加终端 / 你的 IDE）。

### 麦克风无法工作

1. 检查 **系统设置 > 隐私与安全性 > 麦克风**，确保已允许 SpeakType（或终端）。
2. 使用菜单栏中的"测试麦克风"功能验证麦克风是否在录制音频。
3. 尝试从菜单栏选择特定音频设备，而不是使用"系统默认"。

### ASR 模型下载失败

模型从 HuggingFace 下载。如果你在代理后面，请在运行前设置 `HTTP_PROXY` 和 `HTTPS_PROXY` 环境变量。

### 文本润色不工作

1. 验证 Ollama 是否在运行：`curl http://localhost:11434/api/tags`
2. 验证模型是否已拉取：`ollama list` 应显示 `huihui_ai/qwen3.5-abliterated:9b-Claude`
3. 如果没有，运行：`ollama pull huihui_ai/qwen3.5-abliterated:9b-Claude`

### 文字没有插入到应用中

部分应用会阻止模拟键盘输入。尝试在配置中将 `insert_method` 改为 `"type"`，或为目标应用授予辅助功能权限。

### 日志文件

每次运行的日志写入 `~/.speaktype/speaktype.log`。查看此文件获取详细错误信息。

## 开发

```bash
# 以调试模式运行
source venv/bin/activate
python main.py  # 日志输出到 ~/.speaktype/speaktype.log

# 快速管道测试（录制 3 秒，转写，润色）
python main.py --test

# 运行测试
python -m pytest tests/ -v

# 构建 .app 包
python setup.py py2app --alias
```

## 贡献

请参阅 [CONTRIBUTING.md](CONTRIBUTING.md) 了解贡献指南、完整的插件钩子 API 和开发环境配置。

## 许可证

[MIT](LICENSE)
