#!/bin/sh
# 验证和下载进程通过退出状态报告错误。
[ "${SPEAKTYPE_VERIFY_BUNDLE:-}" = "1" ] || [ "${SPEAKTYPE_MODEL_DOWNLOAD_WORKER:-}" = "1" ]
