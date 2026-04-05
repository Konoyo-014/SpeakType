#!/bin/bash
# build_dmg.sh — Build SpeakType.app and package it as a DMG installer.
#
# Usage:
#   ./build_dmg.sh          # Build .app + .dmg
#   ./build_dmg.sh --app    # Build .app only (skip DMG)
#
# Prerequisites:
#   - Python 3.10 virtual environment at ./venv
#   - py2app installed: pip install py2app
#   - create-dmg (optional, for DMG): brew install create-dmg

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="SpeakType"
VERSION="2.0.1"
DMG_NAME="${APP_NAME}-${VERSION}"
DIST_DIR="dist"
APP_PATH="${DIST_DIR}/${APP_NAME}.app"

echo "=== Building ${APP_NAME} v${VERSION} ==="

# --- Step 1: Activate venv ---
if [ -f "./venv/bin/activate" ]; then
    source ./venv/bin/activate
    echo "[1/5] Virtual environment activated"
else
    echo "ERROR: venv not found. Run ./setup.sh first."
    exit 1
fi

# --- Step 2: Clean previous build ---
echo "[2/5] Cleaning previous build..."
rm -rf build/ "${DIST_DIR}/"
mkdir -p "${DIST_DIR}"

# --- Step 3: Build .app with py2app ---
echo "[3/5] Building ${APP_NAME}.app with py2app..."
python3 setup.py py2app --alias 2>&1 | tail -5

# site.py circular import fix is handled automatically by setup.py's atexit hook

echo "  Built: ${APP_PATH}"

if [ "${1:-}" = "--app" ]; then
    echo "=== Done (--app mode, skipping DMG) ==="
    exit 0
fi

# --- Step 4: Create DMG ---
echo "[4/5] Creating DMG installer..."

if command -v create-dmg &>/dev/null; then
    create-dmg \
        --volname "${APP_NAME}" \
        --volicon "resources/icon.icns" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon-size 100 \
        --icon "${APP_NAME}.app" 175 190 \
        --hide-extension "${APP_NAME}.app" \
        --app-drop-link 425 190 \
        --no-internet-enable \
        "${DIST_DIR}/${DMG_NAME}.dmg" \
        "${APP_PATH}" \
        2>&1 | tail -3
else
    # Fallback: use hdiutil directly
    echo "  create-dmg not found, using hdiutil fallback..."
    STAGING_DIR=$(mktemp -d)
    cp -R "${APP_PATH}" "${STAGING_DIR}/"
    ln -s /Applications "${STAGING_DIR}/Applications"

    hdiutil create -volname "${APP_NAME}" \
        -srcfolder "${STAGING_DIR}" \
        -ov -format UDZO \
        "${DIST_DIR}/${DMG_NAME}.dmg"

    rm -rf "${STAGING_DIR}"
fi

echo "  Created: ${DIST_DIR}/${DMG_NAME}.dmg"

# --- Step 5: Summary ---
echo ""
echo "=== Build Complete ==="
echo "  App:  ${APP_PATH}"
echo "  DMG:  ${DIST_DIR}/${DMG_NAME}.dmg"
ls -lh "${DIST_DIR}/${DMG_NAME}.dmg" 2>/dev/null || true
