#!/bin/bash
# 安装 SpeakType 的本地运行依赖和模型。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
mkdir -p "${SCRIPT_DIR}/work/setup/temporary"
export TMPDIR="${SCRIPT_DIR}/work/setup/temporary/"

if [ -n "${SPEAKTYPE_PYTHON:-}" ]; then
    PYTHON="$SPEAKTYPE_PYTHON"
else
    PYTHON="${SCRIPT_DIR}/venv/bin/python"
    if [ ! -x "$PYTHON" ]; then
        BASE_PYTHON="$(command -v python3.10)"
        "$BASE_PYTHON" -m venv "${SCRIPT_DIR}/venv"
    fi
fi

if [[ "$PYTHON" != /* ]] || [ ! -x "$PYTHON" ]; then
    echo "SPEAKTYPE_PYTHON must be an executable absolute Python path: ${PYTHON}" >&2
    exit 1
fi
"$PYTHON" -c 'import platform, sys; assert sys.version_info[:2] == (3, 10), "SpeakType requires Python 3.10"; assert platform.system() == "Darwin" and platform.machine() == "arm64", "SpeakType requires Apple Silicon macOS"'
echo "Installing dependencies with ${PYTHON}"
"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install -r requirements.txt
"$PYTHON" -m pip check
"$PYTHON" scripts/verify_runtime.py

if command -v ollama >/dev/null 2>&1; then
    OLLAMA_BIN="$(command -v ollama)"
elif [ -x /opt/homebrew/opt/ollama/bin/ollama ]; then
    OLLAMA_BIN=/opt/homebrew/opt/ollama/bin/ollama
else
    brew install ollama
    OLLAMA_BIN="$(command -v ollama)"
fi

if ! curl --fail --silent --connect-timeout 2 --max-time 5 http://localhost:11434/api/tags >/dev/null; then
    if [ -d /Applications/Ollama.app ]; then
        open -gj /Applications/Ollama.app
    elif command -v brew >/dev/null 2>&1 && brew list --formula ollama >/dev/null 2>&1; then
        brew services start ollama
    else
        nohup "$OLLAMA_BIN" serve >"${SCRIPT_DIR}/work/setup/ollama.log" 2>&1 </dev/null &
    fi
    for attempt in {1..15}; do
        if curl --fail --silent --connect-timeout 2 --max-time 5 http://localhost:11434/api/tags >/dev/null; then
            break
        fi
        sleep 1
    done
    curl --fail --silent --connect-timeout 2 --max-time 5 http://localhost:11434/api/tags >/dev/null
fi

"$OLLAMA_BIN" pull huihui_ai/qwen3.5-abliterated:9b-Claude
"$PYTHON" -c 'from huggingface_hub import snapshot_download; snapshot_download("mlx-community/Qwen3-ASR-1.7B-8bit")'

echo "SpeakType dependencies and models are ready."
echo "Grant Microphone, Accessibility, and Input Monitoring permissions in System Settings > Privacy & Security."
echo "Run SpeakType: ${PYTHON} ${SCRIPT_DIR}/main.py"
