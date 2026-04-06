#!/bin/bash
# build_dmg.sh — Build SpeakType.app and package it as a DMG installer.
#
# Usage:
#   ./build_dmg.sh          # Build .app + .dmg
#   ./build_dmg.sh --app    # Build .app only (skip DMG)
#   SPEAKTYPE_BUILD_VERSION=2.0.1d1 ./build_dmg.sh --app  # Build a uniquely versioned debug app
#
# Prerequisites:
#   - Python 3.10 virtual environment at ./venv
#   - py2app installed: pip install py2app
#   - create-dmg (optional, for DMG): brew install create-dmg

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="SpeakType"
BASE_VERSION="$(awk -F'"' '/__version__ =/ {print $2}' speaktype/__init__.py)"
BUILD_VERSION="${SPEAKTYPE_BUILD_VERSION:-$BASE_VERSION}"
DMG_NAME="${APP_NAME}-${BUILD_VERSION}"
DIST_DIR="dist"
APP_PATH="${DIST_DIR}/${APP_NAME}.app"
SIGNING_IDENTITY_COUNT="$(security find-identity -v -p codesigning 2>/dev/null | awk '/valid identities found/{print $1}')"

echo "=== Building ${APP_NAME} v${BUILD_VERSION} ==="

if [ "${SIGNING_IDENTITY_COUNT:-0}" = "0" ]; then
    echo "WARNING: No local code signing identity found."
    echo "         py2app will produce an ad-hoc signed app, and macOS may require"
    echo "         re-granting Accessibility/Input Monitoring after rebuilding."
fi

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

# --- Step 3: Build standalone .app with py2app ---
echo "[3/5] Building standalone ${APP_NAME}.app with py2app..."
SPEAKTYPE_BUILD_VERSION="${BUILD_VERSION}" python3 setup.py py2app 2>&1 | tail -5

# site.py circular import fix is handled automatically by setup.py's atexit hook

echo "  Built: ${APP_PATH}"

if [ "${1:-}" = "--app" ]; then
    echo "=== Done (--app mode, skipping DMG) ==="
    exit 0
fi

# --- Step 4: Create DMG ---
echo "[4/5] Creating DMG installer..."

STAGING_DIR=$(mktemp -d)
trap 'rm -rf "${STAGING_DIR}"' EXIT
ditto "${APP_PATH}" "${STAGING_DIR}/${APP_NAME}.app"
ln -s /Applications "${STAGING_DIR}/Applications"

if command -v create-dmg &>/dev/null; then
    create-dmg \
        --volname "${APP_NAME}" \
        --volicon "resources/SpeakType.icns" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon-size 100 \
        --icon "${APP_NAME}.app" 175 190 \
        --hide-extension "${APP_NAME}.app" \
        --app-drop-link 425 190 \
        --no-internet-enable \
        "${DIST_DIR}/${DMG_NAME}.dmg" \
        "${STAGING_DIR}" \
        2>&1 | tail -3
else
    # Fallback: use hdiutil directly
    echo "  create-dmg not found, using hdiutil fallback..."
    hdiutil create -volname "${APP_NAME}" \
        -srcfolder "${STAGING_DIR}" \
        -ov -format UDZO \
        "${DIST_DIR}/${DMG_NAME}.dmg"
fi

rm -rf "${STAGING_DIR}"
trap - EXIT

echo "  Created: ${DIST_DIR}/${DMG_NAME}.dmg"

# --- Step 5: Summary ---
echo ""
echo "=== Build Complete ==="
echo "  App:  ${APP_PATH}"
echo "  DMG:  ${DIST_DIR}/${DMG_NAME}.dmg"
ls -lh "${DIST_DIR}/${DMG_NAME}.dmg" 2>/dev/null || true
