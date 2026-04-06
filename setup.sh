#!/bin/bash
# SpeakType Setup Script
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "╔══════════════════════════════════════╗"
echo "║     SpeakType Setup                  ║"
echo "║     AI Voice Input for Mac           ║"
echo "╚══════════════════════════════════════╝"
echo ""

# 1. Python venv (prefer 3.10-3.12 for MLX compatibility)
echo "▶ Setting up Python environment..."
PYTHON=""
for ver in python3.12 python3.11 python3.10; do
    if command -v "/opt/homebrew/bin/$ver" &>/dev/null; then
        PYTHON="/opt/homebrew/bin/$ver"
        break
    fi
done
[ -z "$PYTHON" ] && PYTHON="$(command -v python3)"
echo "  Using: $($PYTHON --version)"

if [ ! -d "venv" ]; then
    $PYTHON -m venv --clear venv
fi
echo "  ✓ Virtual environment ready"

# 2. Install deps
echo ""
echo "▶ Installing dependencies..."
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install -r requirements.txt -q 2>&1 | tail -3
echo "  ✓ Dependencies installed"

# 3. Ollama
echo ""
echo "▶ Setting up Ollama..."
OLLAMA_BIN="/opt/homebrew/opt/ollama/bin/ollama"
if [ ! -f "$OLLAMA_BIN" ]; then
    if command -v ollama &>/dev/null; then
        OLLAMA_BIN="ollama"
    elif command -v brew &>/dev/null; then
        echo "  Installing Ollama..."
        brew install ollama 2>&1 | tail -3
    else
        echo "  ✗ Install Ollama: https://ollama.ai"
        exit 1
    fi
fi

# Start Ollama if needed
if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
    echo "  Starting Ollama service..."
    OLLAMA_FLASH_ATTENTION="1" OLLAMA_KV_CACHE_TYPE="q8_0" $OLLAMA_BIN serve &>/dev/null &
    sleep 3
fi

# Pull LLM model
LLM_MODEL="huihui_ai/qwen3.5-abliterated:9b-Claude"
echo "  Pulling $LLM_MODEL..."
if $OLLAMA_BIN list 2>/dev/null | grep -q "$LLM_MODEL"; then
    echo "  ✓ LLM model ready"
else
    $OLLAMA_BIN pull "$LLM_MODEL"
    echo "  ✓ LLM model downloaded"
fi

# 4. ASR model
echo ""
echo "▶ Downloading ASR model (Qwen3-ASR-1.7B-8bit)..."
./venv/bin/python -c "
from huggingface_hub import snapshot_download
try:
    snapshot_download('mlx-community/Qwen3-ASR-1.7B-8bit')
    print('  ✓ ASR model ready (1.7B)')
except:
    try:
        snapshot_download('mlx-community/Qwen3-ASR-0.6B-4bit')
        print('  ✓ ASR model ready (0.6B fallback)')
    except Exception as e:
        print(f'  ⚠ Will download on first run: {e}')
"

# 5. Done
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║  Setup Complete!                                 ║"
echo "╠══════════════════════════════════════════════════╣"
echo "║                                                  ║"
echo "║  REQUIRED macOS permissions:                     ║"
echo "║  System Settings → Privacy & Security →          ║"
echo "║    ✓ Microphone   (for Terminal/iTerm)           ║"
echo "║    ✓ Accessibility (for Terminal/iTerm)          ║"
echo "║    ✓ Input Monitoring (for Terminal/iTerm)       ║"
echo "║                                                  ║"
echo "║  To start:  ./start.sh                           ║"
echo "║  To test:   ./start.sh --test                    ║"
echo "║                                                  ║"
echo "║  Push-to-talk: Hold Right ⌘ key, speak, release  ║"
echo "║                                                  ║"
echo "╚══════════════════════════════════════════════════╝"
