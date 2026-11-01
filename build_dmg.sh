#!/bin/bash
# 使用指定的 Python 环境构建独立应用，并验证签名和实际运行依赖。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ "$#" -gt 1 ] || { [ "$#" -eq 1 ] && [ "$1" != "--app" ]; }; then
    echo "Usage: ./build_dmg.sh [--app]" >&2
    exit 2
fi

PYTHON="${SPEAKTYPE_PYTHON:-${SCRIPT_DIR}/venv/bin/python}"
if [[ "$PYTHON" != /* ]] || [ ! -x "$PYTHON" ]; then
    echo "SPEAKTYPE_PYTHON must be an executable absolute Python path: ${PYTHON}" >&2
    exit 1
fi
"$PYTHON" -c 'import platform, sys; assert sys.version_info[:2] == (3, 10), "SpeakType builds require Python 3.10"; assert platform.system() == "Darwin" and platform.machine() == "arm64", "SpeakType builds require Apple Silicon macOS"'

mkdir -p "${SCRIPT_DIR}/work"
BUILD_RUN_DIR="$(mktemp -d "${SCRIPT_DIR}/work/build.XXXXXX")"
BUILD_LOG="${BUILD_RUN_DIR}/build.log"
export TMPDIR="${BUILD_RUN_DIR}/temporary/"
export PYTHONDONTWRITEBYTECODE=1
mkdir -p "$TMPDIR"
exec > >(tee -a "$BUILD_LOG") 2>&1

finish_build() {
    status=$?
    trap - EXIT
    if [ "$status" -ne 0 ]; then
        echo "Build failed. Full log: ${BUILD_LOG}" >&2
    else
        rm -rf "${BUILD_RUN_DIR}/temporary" "${BUILD_RUN_DIR}/clean" "${BUILD_RUN_DIR}/installer"
        echo "Full log: ${BUILD_LOG}"
    fi
    exit "$status"
}
trap finish_build EXIT

BASE_VERSION="$("$PYTHON" -c 'from speaktype import __version__; print(__version__)')"
BUILD_VERSION="${SPEAKTYPE_BUILD_VERSION:-$BASE_VERSION}"
APP_PATH="${SCRIPT_DIR}/dist/SpeakType.app"
DMG_PATH="${SCRIPT_DIR}/dist/SpeakType-${BUILD_VERSION}.dmg"

echo "Building SpeakType ${BUILD_VERSION} with ${PYTHON}"
echo "Build log: ${BUILD_LOG}"
"$PYTHON" -m pip check
"$PYTHON" -c 'import py2app; print("py2app:", py2app.__version__)'
"$PYTHON" scripts/verify_build_environment.py
"$PYTHON" scripts/verify_runtime.py

rm -rf "${SCRIPT_DIR}/build" "$APP_PATH"
mkdir -p "${SCRIPT_DIR}/dist"
echo "Building the standalone application. Detailed output: ${BUILD_LOG}"
SPEAKTYPE_BUILD_VERSION="$BUILD_VERSION" "$PYTHON" setup.py py2app >>"$BUILD_LOG" 2>&1

CLEAN_APP_PATH="${BUILD_RUN_DIR}/clean/SpeakType.app"
mkdir -p "${BUILD_RUN_DIR}/clean"
ditto --norsrc --noextattr --noqtn "$APP_PATH" "$CLEAN_APP_PATH"
rm -rf "$APP_PATH"
mv "$CLEAN_APP_PATH" "$APP_PATH"
xattr -cr "$APP_PATH"
codesign --force --deep --sign - "$APP_PATH"
codesign --verify --deep --strict "$APP_PATH"
SPEAKTYPE_VERIFY_BUNDLE=1 env -u PYTHONDONTWRITEBYTECODE "$APP_PATH/Contents/MacOS/verify_runtime"
codesign --verify --deep --strict "$APP_PATH"
"$PYTHON" scripts/verify_bundle.py "$APP_PATH" --version "$BASE_VERSION" --build-version "$BUILD_VERSION" --source "${SCRIPT_DIR}/speaktype"
echo "Verified application: ${APP_PATH}"

if [ "${1:-}" = "--app" ]; then
    exit 0
fi

INSTALLER_DIR="${BUILD_RUN_DIR}/installer"
mkdir -p "$INSTALLER_DIR"
ditto --norsrc --noextattr --noqtn "$APP_PATH" "${INSTALLER_DIR}/SpeakType.app"
ln -s /Applications "${INSTALLER_DIR}/Applications"
codesign --verify --deep --strict "${INSTALLER_DIR}/SpeakType.app"

BUILT_DMG_PATH="${BUILD_RUN_DIR}/SpeakType-${BUILD_VERSION}.dmg"
hdiutil create -volname SpeakType -srcfolder "$INSTALLER_DIR" -format UDZO "$BUILT_DMG_PATH"
hdiutil verify "$BUILT_DMG_PATH"
mv -f "$BUILT_DMG_PATH" "$DMG_PATH"
shasum -a 256 "$DMG_PATH"
echo "Verified installer: ${DMG_PATH}"
