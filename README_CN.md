# SpeakType

[English](README.md)

按住右 Command 说话，松开后把文字插入当前光标位置。SpeakType 在 Mac 本机运行 Qwen3-ASR，并通过本地 Ollama 模型提供可选的润色和翻译。

## 安装

需要 **macOS 14 或更高版本，以及搭载 Apple Silicon 的 Mac**。DMG 已包含 Python 运行环境和应用依赖。

1. 打开 [GitHub 最新发布页面](https://github.com/Konoyo-014/SpeakType/releases/latest)，下载附件中的 `SpeakType-*.dmg`。
2. 打开 DMG，把 **SpeakType** 拖动到 **Applications（应用程序）**，然后从应用程序文件夹启动。
3. 按照设置窗口的提示准备语音识别模型。首次下载需要网络连接。
4. 根据系统提示，在 **系统设置 > 隐私与安全性** 中授予 SpeakType **麦克风、辅助功能、输入监控** 权限。权限更改后，按照应用提示重新启动 SpeakType。
5. 点击可编辑的文本输入框，按住 **右 Command** 说话，然后松开快捷键。

SpeakType 会显示在菜单栏中。点击麦克风图标可以修改设置或打开 **本地自检**。如果 macOS 要求批准打开下载的应用，可以在 **系统设置 > 隐私与安全性 > 仍要打开** 中批准 SpeakType。

### 启用润色与翻译

打开本机 Ollama 应用，并安装 **偏好设置 > AI 模型** 中选择的模型。默认模型的安装命令为：

```bash
ollama pull huihui_ai/qwen3.5-abliterated:9b-Claude
```

通过 Homebrew 安装 Ollama 时，可以运行 `brew services start ollama`，让本地服务在后台持续运行。`ollama serve` 会在当前终端中运行服务，关闭终端窗口后服务会停止。SpeakType 默认连接 `http://localhost:11434`。

Ollama 暂时不可用时，SpeakType 会插入转写文本，并提示本次跳过了润色或翻译。**本地自检** 会显示当前模型以及安装模型所需的命令。

设置向导与本地自检会核对设置中的 Ollama 服务地址与完整模型标签。语音识别模型的配置、分词文件和权重通过缓存检查后，下载才会显示完成。跳过尚未安装的可选 Ollama 模型后，保存的设置会关闭润色与翻译。

## 听写与恢复文本

| 操作 | 方法 |
|---|---|
| 按住快捷键听写 | 按住右 Command，说话，然后松开 |
| 按键切换录音 | 在偏好设置中选择切换模式；按一次开始，再按一次停止 |
| 修改快捷键或麦克风 | 使用偏好设置或菜单中的麦克风选项 |
| 复制最近一次结果 | 菜单栏 > 复制最近听写 |
| 再次插入最近一次结果 | 先点击目标输入框，再选择“再次插入最近听写” |
| 查找以前的结果 | 菜单栏 > 听写历史 |

**听写历史** 支持搜索原始转写、最终文本、应用名称、时间和插入结果。选择一条记录后，可以查看完整的原始转写与最终文本，再点击 **复制原始转写** 或 **复制最终文本**。窗口还提供刷新功能，以及 TXT、Markdown、CSV、JSON 导出功能。使用次数和时长可以在独立的 **听写统计** 中查看。

开启 **保存听写历史** 后，SpeakType 会在本地模型处理前保存原始转写，并在尝试插入前保存最终文本。历史记录会显示以下状态：

| 状态 | 含义 |
|---|---|
| 尚未确认 | 文本已经保存，插入操作尚未确认 |
| 已插入 | 辅助功能接口已经在目标输入框中读取到插入文本 |
| 已发送（未验证） | 输入事件已经发送，但目标应用提供的信息不足以验证插入结果 |
| 插入失败 | SpeakType 没有完成插入操作 |

插入失败时，可以从历史记录复制文本，也可以选择 **复制最近听写**。状态显示为 **已发送（未验证）** 时，请先查看目标输入框，再决定是否再次插入，避免出现重复内容。关闭历史记录后，当前会话仍然保留最近一次结果，可以复制或再次插入。

## 语音指令

在菜单中开启 **语音指令**，即可使用口述标点和编辑指令。

| 口述内容 | 输出 |
|---|---|
| `句号`、`逗号`、`问号`、`感叹号` | `。`、`，`、`？`、`！` |
| `冒号`、`分号` | `：`、`；` |
| `左引号` / `右引号` | 双引号 |
| `左单引号` / `右单引号` | 单引号 |
| `左括号` / `右括号` | 圆括号 |
| `左方括号` / `右方括号` | 方括号 |
| `左书名号` / `右书名号` | 书名号 |
| `换行`、`新段落`、`tab` | 换行、段落间空行、制表符 |

可以连续口述引号、括号和结尾标点。例如，`他说左引号你好右引号句号` 会生成 `他说“你好”。`；`说明左括号补充右括号句号` 会生成 `说明（补充）。`。英文也支持连续指令：`open quote hello close quote period` 会生成 `"hello".`。

编辑所选文本时，先选中内容，再说出完整指令，例如 `缩短`、`正式一点`、`修正语法`、`翻译成英文`、`总结一下` 或 `回复`。编辑功能使用本地 Ollama 模型。

`撤销刚才`、`undo that` 和 `scratch that` 可以删除已验证的插入内容。执行时，输入框、完整正文和光标位置必须与插入完成时一致。程序通过辅助功能接口精确选择并删除对应内容，再验证删除后的正文；包含 emoji 的文本也使用正确的字符范围。移动光标、选择其他内容、修改正文、切换文档，或者目标无法提供可读取的辅助功能文本时，程序会保留当前正文。

## 词语与快捷短语

**自适应热词** 会从用户对 SpeakType 刚插入文本的即时修改中学习可重复使用的术语。应用只会在一段有限时间内观察当前输入框中刚插入的文本；切换应用后会停止观察。密码输入框、不可读取的输入框、无关输入以及单纯追加的内容不会用于学习。Ollama 本地模型提出术语后，程序会检查术语是否得到修改后文本的支持，再保存到 `~/.speaktype/hotwords.json`。

后续听写会根据应用、场景、语言、置信度和最近使用情况选择一组相关词语。当前 Qwen3-ASR 接口支持上下文参数时，这些词语会传入语音识别；本地润色与翻译也会使用这些词语。可以打开菜单中的 **自学习热词** 查看已学习词语和当前启用情况。

**词典与快捷短语** 可以管理自定义词语、纠错和固定文本。纠错会保留替换文本中的反斜杠，并优先匹配较长的词语。快捷短语支持 `{date}`、`{time}`、`{datetime}`、`{clipboard}` 和 `{env:NAME}`；剪贴板与环境变量内容只在触发词精确匹配时展开。

## 其他设置

- **文本润色** 可以去除语气词、修正语法，并根据当前应用选择语气。提示会要求保持原文语言，重试也会保留原来的语言要求。此功能需要设置中选择的本地 Ollama 模型。
- **转写后翻译** 支持英语、中文、日语、韩语、西班牙语、法语和德语。
- **实时预览** 会在录音过程中显示识别进度，最终转写结果用于插入文本。
- **自动调整低音量录音** 会检测轻声说话，并自动提高录音增益。
- **本地自检** 会检查输入权限、麦克风、模型、Ollama、热词和当前输入框，并提供具体的本地修复步骤。
- **偏好设置** 提供中英文界面、按住说话或按键切换、麦克风选择等选项；默认单次录音上限为六分钟。

## v2.3.0 的更新

- 新增可搜索的原生听写历史窗口，可以查看和复制完整的原始转写与最终文本，查看插入结果，刷新和导出记录。
- 在润色前保留原始转写，在插入前保存最终文本；菜单可以复制或再次插入最近一次结果。
- 支持连续口述中英文引号、括号和标点。
- 安全撤销会核对输入框、完整正文和 UTF-16 光标位置，再精确选择与删除已验证的插入内容。
- 润色保持输入语言；权限检查读取真实麦克风授权；模型检查核对完整 Ollama 标签，并在确认语音模型缓存完整后显示下载完成。
- 连续插入文本时，剪贴板恢复操作会保留用户新复制的内容。
- 纠错保留反斜杠并优先处理较长词语；保存文件中的格式或字段错误会明确报告。
- 独立应用构建会检查 ad hoc 代码签名和内置运行依赖，最低系统版本为 macOS 14。

具体功能和已完成的验证见 [v2.3.0 发布说明](docs/releases/v2.3.0.md)。

## 设置与本地文件

偏好设置保存在 `~/.speaktype/config.json`。听写历史、热词、纠错、快捷短语和自定义词典也保存在 `~/.speaktype/`。JSON 格式或字段类型不符合要求时，程序会明确报告错误，并保留原文件。

| 设置项 | 默认值 | 用途 |
|---|---|---|
| `hotkey` | `"right_cmd"` | 支持 `right_cmd`、`left_cmd`、`fn`、`right_alt`、`right_ctrl`、`ctrl+shift+space`、`f5`、`f6` |
| `dictation_mode` | `"push_to_talk"` | 按住说话；`"toggle"` 表示按键切换 |
| `audio_device` | `null` | 系统默认、设备名称或设备编号 |
| `asr_model` | `"mlx-community/Qwen3-ASR-1.7B-8bit"` | 本地 Qwen3-ASR 模型 |
| `language` | `"auto"` | 语音识别语言 |
| `llm_model` | `"huihui_ai/qwen3.5-abliterated:9b-Claude"` | 本地 Ollama 模型 |
| `ollama_url` | `"http://localhost:11434"` | Ollama 服务地址 |
| `polish_enabled` | `true` | 文本润色 |
| `auto_punctuation` | `true` | 允许润色添加标点 |
| `filler_removal` | `true` | 润色时去除语气词 |
| `context_aware_tone` | `true` | 根据应用选择语气 |
| `translate_enabled` / `translate_target` | `false` / `"en"` | 翻译输出文本 |
| `voice_commands_enabled` | `true` | 标点与编辑指令 |
| `streaming_preview` | `true` | 显示识别进度 |
| `history_enabled` / `history_max_entries` | `true` / `1000` | 保存历史及数量上限 |
| `insert_method` | `"paste"` | 通过剪贴板插入；`"type"` 表示发送键盘事件 |
| `max_recording_seconds` | `360` | 单次录音时长上限 |
| `sound_feedback` | `true` | 录音开始与停止时的提示音 |
| `hotword_learning_enabled` | `true` | 从即时修改中学习术语 |
| `hotword_context_enabled` | `true` | 在识别和润色中使用已学习词语 |
| `hotword_auto_corrections_enabled` | `true` | 保存高置信度的纠错关系 |
| `hotword_observation_seconds` | `18` | 观察修改的时长 |
| `hotword_observation_stable_seconds` | `1.2` | 等待修改稳定的时长 |
| `hotword_max_context_terms` | `30` | 单次请求使用的热词数量上限 |
| `plugins_enabled` | `false` | 启用本地 Python 插件 |
| `ui_language` | `"zh"` | `"zh"` 或 `"en"` |

## 常见问题

**录音或快捷键没有响应：** 打开 **本地自检**，检查系统设置中的麦克风、辅助功能和输入监控权限，并选择需要使用的麦克风。权限更改后，按照提示重新启动 SpeakType。

**文字没有出现在输入框中：** 打开 **听写历史** 或选择 **复制最近听写**，然后把结果粘贴到可编辑输入框。再次插入前，先检查记录中的插入状态。

**润色或翻译被跳过：** 打开 Ollama，确认 **偏好设置 > AI 模型** 中的模型已经安装，并使用 **本地自检** 显示的命令安装缺少的模型。本地语言模型暂时不可用时，听写仍然可以使用。

**保存文件被拒绝读取：** 根据报告的格式或字段错误修正对应的 JSON 文件，然后重新启动应用。SpeakType 会保留文件内容。运行日志位于 `~/.speaktype/speaktype.log`。

## 从源码运行

源码运行需要 Apple Silicon Mac 和 Python 3.10。在仓库目录中执行：

```bash
git clone https://github.com/Konoyo-014/SpeakType.git
cd SpeakType
python3.10 -m venv venv
./venv/bin/python -m pip install -r requirements.txt
./venv/bin/python -m pip check
./venv/bin/python scripts/verify_runtime.py
./venv/bin/python main.py
```

设置窗口可以下载语音识别模型。从源码启动时，系统可能要求给终端或开发工具授予权限。需要 Hugging Face 镜像时，请在同一个终端中把 `HF_ENDPOINT` 设置为所用镜像地址，再启动应用。

`./setup.sh` 还会准备 Ollama 并下载默认的语音识别与润色模型。Ollama 尚未安装时，该脚本需要通过 Homebrew 安装 Ollama。

### 验证与构建

```bash
PYTHONPATH=. ./venv/bin/python scripts/validate_core.py
PYTHONPATH=. ./venv/bin/python scripts/validate_clipboard.py
PYTHONPATH=. ./venv/bin/python scripts/validate_history_ui.py
./venv/bin/python scripts/verify_runtime.py

./build_dmg.sh --app
./build_dmg.sh
```

构建环境需要安装 `requirements-build.txt`。通过 `SPEAKTYPE_PYTHON` 指定 Python 3.10 解释器的绝对路径；该解释器需要支持 macOS 14 或更早系统，并提供动态 zlib 扩展。本次发布使用 conda-forge Python 3.10.19，以及 `requirements-build.txt` 固定的官方 macOS 14 MLX wheel。构建脚本会先检查解释器。构建过程在 `work/` 中保存中间文件和日志，生成 `dist/SpeakType.app` 与 `dist/SpeakType-2.3.0.dmg`，使用 ad hoc 代码签名，检查完整应用包的签名，并执行内置运行环境的依赖检查。DMG 提供应用程序文件夹的快捷方式。

### Python 插件

把插件文件放入 `~/.speaktype/plugins/`，然后在偏好设置中启用。文件名以 `_` 开头的插件会被忽略。

| 插件函数 | 参数与返回值 |
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

## 许可证

[MIT](LICENSE)
