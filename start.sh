#!/bin/bash
# Start SpeakType - AI Voice Input for Mac
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Activate venv
if [ ! -f "venv/bin/activate" ]; then
    echo "Run setup.sh first!"
    exit 1
fi
source venv/bin/activate

# Ensure Ollama is running
OLLAMA_BIN="/opt/homebrew/opt/ollama/bin/ollama"
[ ! -f "$OLLAMA_BIN" ] && OLLAMA_BIN="ollama"

if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
    echo "Starting Ollama..."
    OLLAMA_FLASH_ATTENTION="1" OLLAMA_KV_CACHE_TYPE="q8_0" $OLLAMA_BIN serve &>/dev/null &
    sleep 2
fi

echo "╔═══════════════════════════════════════╗"
echo "║  SpeakType v2.0                       ║"
echo "║  Push-to-talk: Hold Right ⌘           ║"
echo "║  Preferences: Click menubar icon → ⌘, ║"
echo "╚═══════════════════════════════════════╝"
echo ""

python main.py "$@"
