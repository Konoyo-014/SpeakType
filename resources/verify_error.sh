#!/bin/sh
# 辅助进程通过退出状态报告错误。
[ "${SPEAKTYPE_VERIFY_BUNDLE:-}" = "1" ] || [ "${SPEAKTYPE_MODEL_DOWNLOAD_WORKER:-}" = "1" ] || [ "${SPEAKTYPE_AUDIO_CAPTURE_WORKER:-}" = "1" ]
