import atexit
from copy import deepcopy
import threading
import time

import AppKit
import objc
import Quartz
from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
from Foundation import NSObject, NSMakeRect, NSMakeSize, NSThread, NSURL
from PyObjCTools.AppHelper import callAfter

from .model_manager import (
    CancelToken,
    DownloadCancelled,
    OllamaUpdateRequired,
    download_asr,
    inspect_asr,
    inspect_ollama,
    pull_ollama,
    start_installed_ollama,
)
from .permissions import (
    get_permission_status,
    microphone_is_authorized,
    request_microphone_if_needed,
)
from .polish import ollama_model_is_available


LABELS = {
    "title": ("准备 SpeakType", "Get SpeakType ready"),
    "subtitle": ("检查权限与本地模型，完成后即可开始听写。下载期间可以返回主窗口。", "Prepare permissions and local models for dictation. Downloads continue when you return to the main window."),
    "permissions": ("系统权限", "System permissions"),
    "microphone": ("麦克风", "Microphone"),
    "accessibility": ("辅助功能", "Accessibility"),
    "listen": ("输入监控", "Input Monitoring"),
    "allowed": ("已允许", "Allowed"),
    "needs_access": ("待授权", "Needs access"),
    "mic_settings": ("麦克风设置…", "Microphone settings…"),
    "access_settings": ("辅助功能设置…", "Accessibility settings…"),
    "listen_settings": ("输入监控设置…", "Input Monitoring settings…"),
    "permission_note": ("更改权限后请刷新状态；系统要求时需要重新启动 SpeakType。", "Refresh after changing permissions. Restart SpeakType when macOS requires it."),
    "refresh": ("刷新状态", "Refresh status"),
    "asr_title": ("语音识别模型", "Speech recognition model"),
    "asr_note": ("下载完成后，语音识别可以在本机离线运行。", "Recognition runs on this Mac and works offline after download."),
    "checking": ("正在检查…", "Checking…"),
    "cached": ("模型缓存完整", "Complete model cache"),
    "missing_cache": ("本机尚未完整下载这个模型。", "This model has not been fully downloaded on this Mac."),
    "download": ("下载模型", "Download model"),
    "retry": ("重试下载", "Retry download"),
    "repair_asr": ("重新下载完整模型", "Redownload model"),
    "repair_asr_note": ("重新下载完整模型并验证缓存文件。官方缓存由下载工具管理。", "Download the complete model again and verify its cache files. The official download tool manages cached files."),
    "cancel": ("取消下载", "Cancel download"),
    "check_cache": ("重新检查缓存", "Check cache again"),
    "ollama_title": ("润色与翻译（可选）", "Polish and translation (optional)"),
    "polish": ("启用润色", "Enable polish"),
    "translation": ("启用翻译", "Enable translation"),
    "dictation_only": ("仅使用语音识别", "Use dictation only"),
    "service_ready": ("Ollama 服务已连接，已安装 {count} 个模型。", "Ollama is connected. Installed models: {count}."),
    "service_stopped": ("Ollama 服务尚未连接。{detail}", "Ollama is not connected. {detail}"),
    "start_ollama": ("启动 Ollama", "Start Ollama"),
    "install_ollama": ("安装 Ollama…", "Install Ollama…"),
    "refresh_service": ("刷新服务", "Refresh service"),
    "starting_service": ("正在启动 Ollama…", "Starting Ollama…"),
    "model": ("使用的模型", "Selected model"),
    "not_installed": ("尚未下载", "not downloaded"),
    "installed": ("已安装", "installed"),
    "model_installed": ("所选模型已安装，可以使用润色和翻译。", "The selected model is installed and ready for polish and translation."),
    "model_missing": ("下载所选模型，或选择已经安装的模型。", "Download the selected model or choose an installed model."),
    "optional_off": ("润色与翻译已关闭，可以直接使用语音识别。", "Polish and translation are off. Dictation can run without Ollama."),
    "preparing": ("正在准备下载…", "Preparing download…"),
    "downloading": ("正在下载模型…", "Downloading model…"),
    "validating": ("正在验证下载文件…", "Validating downloaded files…"),
    "cancelling": ("正在取消下载…", "Cancelling download…"),
    "cancelled": ("下载已取消，已保存的缓存可以用于重试。", "Download cancelled. Cached files are preserved for retry."),
    "complete": ("下载完成并已验证。", "Download completed and verified."),
    "failed": ("操作失败：{detail}", "Operation failed: {detail}"),
    "error_details": ("错误详情…", "Error details…"),
    "error_title": ("模型准备失败", "Model preparation failed"),
    "error_note": ("可以选择下面的完整错误内容，或点击复制错误。关闭后可以检查设置并重试。", "Select the complete error below or copy it with the button. Close this window to check settings and retry."),
    "copy_error": ("复制错误", "Copy error"),
    "close_error": ("关闭", "Close"),
    "update_ollama": ("更新 Ollama…", "Update Ollama…"),
    "try": ("试用录音", "Try dictation"),
    "back": ("返回主窗口", "Back to main window"),
    "need_mic": ("允许麦克风后即可录音。", "Allow microphone access to record speech."),
    "need_asr": ("完整下载语音识别模型后即可开始听写。", "Finish downloading the speech recognition model to begin dictation."),
    "need_llm": ("下载或选择可用的 Ollama 模型；也可以关闭润色与翻译。", "Download or select an available Ollama model, or turn off polish and translation."),
    "need_input": ("语音识别已就绪；全局快捷键与自动输入还需要系统权限。", "Recognition is ready. Global shortcuts and automatic insertion still need system permissions."),
    "ready": ("准备完成，可以开始听写。", "Ready to start dictation."),
    "download_continues": ("模型正在后台准备，返回主窗口后会继续下载。", "Models are being prepared in the background. Downloads continue in the main window."),
}

SETTINGS_URLS = {
    "microphone": "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone",
    "accessibility": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
    "listen": "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent",
}
OLLAMA_INSTALL_URL = "https://ollama.com/download/mac"


def format_bytes(value):
    amount = max(0, int(value))
    if amount >= 1024 ** 3:
        return f"{amount / 1024 ** 3:.2f} GB"
    if amount >= 1024 ** 2:
        return f"{amount / 1024 ** 2:.1f} MB"
    return f"{amount / 1024:.1f} KB"


class _SetupCenterDelegate(NSObject):
    def initWithController_(self, controller):
        self = objc.super(_SetupCenterDelegate, self).init()
        if self is not None:
            self.controller = controller
        return self

    def onMicrophone_(self, sender):
        self.controller._open_permission("microphone")

    def onAccessibility_(self, sender):
        self.controller._open_permission("accessibility")

    def onListen_(self, sender):
        self.controller._open_permission("listen")

    def onRefresh_(self, sender):
        self.controller.refresh()

    def onDownloadASR_(self, sender):
        self.controller._download_asr()

    def onCancelASR_(self, sender):
        self.controller._cancel_transfer("asr")

    def onASRError_(self, sender):
        self.controller._show_error("asr")

    def onService_(self, sender):
        self.controller._service_action()

    def onDownloadOllama_(self, sender):
        self.controller._download_ollama()

    def onCancelOllama_(self, sender):
        self.controller._cancel_transfer("ollama")

    def onOllamaError_(self, sender):
        self.controller._show_error("ollama")

    def onFeatureChange_(self, sender):
        self.controller._change_features()

    def onDictationOnly_(self, sender):
        self.controller._change_config({"polish_enabled": False, "translate_enabled": False})

    def onModel_(self, sender):
        index = int(sender.indexOfSelectedItem())
        self.controller._change_config({"llm_model": self.controller._model_choices[index]})

    def onTest_(self, sender):
        self.controller._test()

    def onBack_(self, sender):
        self.controller._back()

    def windowShouldClose_(self, sender):
        self.controller.close()
        return False

    def windowDidBecomeKey_(self, notification):
        self.controller.refresh()


class SetupCenterController:
    WINDOW_WIDTH = 1000
    WINDOW_HEIGHT = 720

    def __init__(self, config, on_change, on_test, on_ready=None):
        if not callable(on_change) or not callable(on_test):
            raise TypeError("Setup center requires callable on_change and on_test callbacks")
        if on_ready is not None and not callable(on_ready):
            raise TypeError("on_ready must be callable")
        self.config = deepcopy(config)
        self.on_change = on_change
        self.on_test = on_test
        self.on_ready = on_ready
        self.window = None
        self._delegate = None
        self._controls = {}
        self._localized = []
        self._model_choices = []
        self._permissions = None
        self._microphone = False
        self._asr_snapshot = {"cached": False, "path": None, "size_bytes": 0}
        self._ollama_snapshot = {"running": False, "installed": False, "models": [], "error": ""}
        self._tasks = {"asr": None, "ollama": None}
        self._states = {"asr": "checking", "ollama": "checking"}
        self._errors = {"asr": "", "ollama": ""}
        self._progress = {"asr": None, "ollama": None}
        self._task_models = {"asr": None, "ollama": None}
        self._task_workers = {"asr": None, "ollama": None}
        self._epochs = {"asr": 0, "ollama": 0}
        self._checking = {"asr": False, "ollama": False}
        self._starting_service = False
        self._ollama_update_required = False
        self._asr_cache_error = False
        self._error_alert = None
        self._error_view = None
        self._workers = set()
        self._worker_lock = threading.Lock()
        self._shutting_down = False
        atexit.register(self.shutdown)

    def _text(self, key, **values):
        index = 0 if self.config.get("ui_language", "zh") == "zh" else 1
        return LABELS[key][index].format(**values)

    @property
    def input_permissions_ready(self):
        return self._permissions is not None and self._permissions.all_granted

    @property
    def ready_for_dictation(self):
        language_features = bool(self.config.get("polish_enabled") or self.config.get("translate_enabled"))
        model_ready = self._selected_model_is_installed()
        return bool(self._microphone and self._asr_snapshot["cached"] and
                    (not language_features or (self._ollama_snapshot["running"] and model_ready)))

    def show(self):
        if self._shutting_down:
            raise RuntimeError("A shutting-down setup center cannot be shown")
        if not NSThread.isMainThread():
            raise RuntimeError("Show the setup center on the main thread")
        if self.window is None:
            self._build_window()
        self.window.makeKeyAndOrderFront_(None)
        AppKit.NSApp.activateIgnoringOtherApps_(True)
        self.refresh()

    def close(self):
        if self.window is not None:
            self.window.orderOut_(None)

    def shutdown(self):
        self._shutting_down = True
        for token in self._tasks.values():
            if token is not None:
                token.cancel()

    def resume_after_shutdown(self):
        if not NSThread.isMainThread():
            raise RuntimeError("Resume the setup center on the main thread")
        self._shutting_down = False
        for kind, token in self._tasks.items():
            if token is None:
                continue
            worker = self._task_workers[kind]
            if worker is not None and worker.is_alive():
                self._states[kind] = "cancelling"
            else:
                self._tasks[kind] = None
                self._task_workers[kind] = None
                self._task_models[kind] = None
                self._states[kind] = "cancelled"
                self._errors[kind] = ""
        self.refresh()

    @property
    def worker_threads(self):
        with self._worker_lock:
            return tuple(self._workers)

    def _start_worker(self, target, name):
        if self._shutting_down:
            raise RuntimeError("A shutting-down setup center cannot start background work")

        def run():
            try:
                target()
            finally:
                with self._worker_lock:
                    self._workers.discard(threading.current_thread())

        worker = threading.Thread(target=run, name=name, daemon=True)
        with self._worker_lock:
            self._workers.add(worker)
        worker.start()
        return worker

    def refresh(self, config=None):
        if self._shutting_down:
            return
        if not NSThread.isMainThread():
            raise RuntimeError("Refresh the setup center on the main thread")
        if config is not None:
            previous_model = self.config.get("asr_model")
            previous_url = self.config.get("ollama_url")
            self.config = deepcopy(config)
            if previous_model != self.config.get("asr_model"):
                self._asr_snapshot = {"cached": False, "path": None, "size_bytes": 0}
                self._asr_cache_error = False
                self._epochs["asr"] += 1
                self._checking["asr"] = False
            if previous_url != self.config.get("ollama_url"):
                self._ollama_snapshot = {"running": False, "installed": False, "models": [], "error": ""}
                self._epochs["ollama"] += 1
                self._checking["ollama"] = False
            self._localize()
        self._permissions = get_permission_status()
        self._microphone = microphone_is_authorized()
        model = str(self.config["asr_model"])
        url = str(self.config["ollama_url"])
        self._refresh_snapshot("asr", lambda: inspect_asr(model))
        self._refresh_snapshot("ollama", lambda: inspect_ollama(url))
        self._render()

    def apply_config(self, config):
        self.refresh(config)

    def _build_window(self):
        style = AppKit.NSWindowStyleMaskTitled | AppKit.NSWindowStyleMaskClosable | AppKit.NSWindowStyleMaskMiniaturizable
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, self.WINDOW_WIDTH, self.WINDOW_HEIGHT), style, AppKit.NSBackingStoreBuffered, False)
        self.window.setTitle_(self._text("title"))
        self.window.setReleasedWhenClosed_(False)
        self.window.setTabbingMode_(AppKit.NSWindowTabbingModeDisallowed)
        self.window.setAppearance_(AppKit.NSAppearance.appearanceNamed_(AppKit.NSAppearanceNameAqua))
        self.window.setBackgroundColor_(AppKit.NSColor.whiteColor())
        self.window.center()
        self._delegate = _SetupCenterDelegate.alloc().initWithController_(self)
        self.window.setDelegate_(self._delegate)
        root = self.window.contentView()
        self._label(root, "title", "heading", 24, 664, 952, 32, size=25, bold=True)
        self._label(root, "subtitle", "subtitle", 24, 626, 952, 34)
        self._box(root, 24, 366, 456, 246)
        self._box(root, 500, 366, 476, 246)
        self._box(root, 24, 112, 952, 236)
        self._label(root, "permissions", "permissions.title", 44, 576, 410, 24, size=17, bold=True)
        rows = (("microphone", "mic_settings", b"onMicrophone:", 532),
                ("accessibility", "access_settings", b"onAccessibility:", 488),
                ("listen", "listen_settings", b"onListen:", 444))
        for name, button_key, action, y in rows:
            self._label(root, name, f"permission.{name}.name", 44, y, 116, 22)
            self._label(root, None, f"permission.{name}.status", 166, y, 98, 22)
            self._button(root, button_key, f"permission.{name}.open", action, 272, y - 4, 188)
        self._label(root, "permission_note", "permissions.note", 44, 380, 416, 48, size=12, secondary=True)
        self._label(root, "asr_title", "asr.title", 520, 576, 436, 24, size=17, bold=True)
        self._label(root, None, "asr.model", 520, 548, 316, 22, size=12, secondary=True)
        self._button(root, "error_details", "asr.error", b"onASRError:", 844, 544, 112)
        self._label(root, None, "asr.status", 520, 498, 436, 44)
        self._bar(root, "asr.progress", 520, 480, 436)
        self._label(root, None, "asr.detail", 520, 452, 436, 24, size=12, secondary=True)
        self._button(root, "download", "asr.download", b"onDownloadASR:", 520, 408, 154)
        self._button(root, "cancel", "asr.cancel", b"onCancelASR:", 680, 408, 118)
        self._button(root, "check_cache", "asr.refresh", b"onRefresh:", 804, 408, 152)
        self._label(root, "asr_note", "asr.note", 520, 378, 436, 25, size=11, secondary=True)
        self._label(root, "ollama_title", "ollama.title", 44, 312, 912, 24, size=17, bold=True)
        self._checkbox(root, "polish", "polish.enabled", 44, 278, 174)
        self._checkbox(root, "translation", "translation.enabled", 228, 278, 196)
        self._button(root, "dictation_only", "dictation.only", b"onDictationOnly:", 746, 274, 210)
        self._label(root, None, "ollama.service", 44, 232, 690, 40, size=12)
        self._button(root, "start_ollama", "ollama.service.action", b"onService:", 746, 232, 210)
        self._label(root, "model", "ollama.model.label", 44, 198, 110, 24)
        popup = AppKit.NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(158, 194, 492, 30), False)
        popup.setTarget_(self._delegate)
        popup.setAction_(b"onModel:")
        popup.setIdentifier_("setup.ollama.model")
        root.addSubview_(popup)
        self._controls["ollama.model"] = popup
        self._button(root, "download", "ollama.download", b"onDownloadOllama:", 660, 194, 172)
        self._button(root, "cancel", "ollama.cancel", b"onCancelOllama:", 840, 194, 116)
        self._bar(root, "ollama.progress", 44, 174, 912)
        self._label(root, None, "ollama.detail", 44, 124, 784, 44, size=12, secondary=True)
        self._button(root, "error_details", "ollama.error", b"onOllamaError:", 840, 132, 116)
        self._label(root, None, "summary", 24, 66, 952, 32)
        self._button(root, "refresh", "refresh", b"onRefresh:", 24, 22, 164)
        self._button(root, "try", "test", b"onTest:", 600, 22, 174)
        self._button(root, "back", "back", b"onBack:", 786, 22, 190)
        self._render()

    def _box(self, root, x, y, width, height):
        box = AppKit.NSBox.alloc().initWithFrame_(NSMakeRect(x, y, width, height))
        box.setBoxType_(AppKit.NSBoxCustom)
        box.setTitle_("")
        box.setTitlePosition_(AppKit.NSNoTitle)
        box.setBorderType_(AppKit.NSLineBorder)
        box.setBorderColor_(AppKit.NSColor.separatorColor())
        box.setFillColor_(AppKit.NSColor.whiteColor())
        box.setCornerRadius_(8)
        root.addSubview_(box)

    def _label(self, root, key, name, x, y, width, height, size=13, bold=False, secondary=False):
        field = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, width, height))
        field.setEditable_(False)
        field.setSelectable_(True)
        field.setBezeled_(False)
        field.setDrawsBackground_(False)
        field.setUsesSingleLineMode_(False)
        field.setLineBreakMode_(AppKit.NSLineBreakByWordWrapping)
        field.setFont_(AppKit.NSFont.systemFontOfSize_weight_(size, AppKit.NSFontWeightSemibold if bold else AppKit.NSFontWeightRegular))
        field.setTextColor_(AppKit.NSColor.secondaryLabelColor() if secondary else AppKit.NSColor.labelColor())
        field.setIdentifier_(f"setup.{name}")
        field.setStringValue_(self._text(key) if key is not None else "")
        root.addSubview_(field)
        self._controls[name] = field
        if key is not None:
            self._localized.append((field, key, "setStringValue_"))
        return field

    def _button(self, root, key, name, action, x, y, width):
        button = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(x, y, width, 32))
        button.setTitle_(self._text(key))
        button.setBezelStyle_(AppKit.NSBezelStyleRounded)
        button.setTarget_(self._delegate)
        button.setAction_(action)
        button.setIdentifier_(f"setup.{name}")
        root.addSubview_(button)
        self._controls[name] = button
        self._localized.append((button, key, "setTitle_"))
        return button

    def _checkbox(self, root, key, name, x, y, width):
        button = self._button(root, key, name, b"onFeatureChange:", x, y, width)
        button.setButtonType_(AppKit.NSButtonTypeSwitch)
        return button

    def _bar(self, root, name, x, y, width):
        bar = AppKit.NSProgressIndicator.alloc().initWithFrame_(NSMakeRect(x, y, width, 14))
        bar.setStyle_(AppKit.NSProgressIndicatorStyleBar)
        bar.setMinValue_(0)
        bar.setMaxValue_(100)
        bar.setIndeterminate_(False)
        bar.setIdentifier_(f"setup.{name}")
        root.addSubview_(bar)
        self._controls[name] = bar

    def _localize(self):
        if self.window is None:
            return
        self.window.setTitle_(self._text("title"))
        for view, key, setter in self._localized:
            getattr(view, setter)(self._text(key))
        if self._error_alert is not None:
            self._error_alert.setMessageText_(self._text("error_title"))
            self._error_alert.setInformativeText_(self._text("error_note"))
            self._error_alert.buttons()[0].setTitle_(self._text("close_error"))
            self._error_alert.buttons()[1].setTitle_(self._text("copy_error"))

    def _render(self):
        if self.window is None:
            return
        permission_values = {"microphone": self._microphone,
                             "accessibility": bool(self._permissions and self._permissions.accessibility and self._permissions.post_event),
                             "listen": bool(self._permissions and self._permissions.listen_event)}
        for name, allowed in permission_values.items():
            field = self._controls[f"permission.{name}.status"]
            field.setStringValue_(self._text("allowed" if allowed else "needs_access"))
            field.setTextColor_(AppKit.NSColor.systemGreenColor() if allowed else AppKit.NSColor.systemOrangeColor())
        self._controls["polish.enabled"].setState_(1 if self.config.get("polish_enabled") else 0)
        self._controls["translation.enabled"].setState_(1 if self.config.get("translate_enabled") else 0)
        self._controls["asr.model"].setStringValue_(str(self._task_models["asr"] or self.config["asr_model"]))
        self._render_transfer("asr")
        self._render_service()
        self._render_transfer("ollama")
        self._controls["test"].setEnabled_(self.ready_for_dictation)
        if any(self._tasks.values()):
            key = "download_continues"
        elif not self._microphone:
            key = "need_mic"
        elif not self._asr_snapshot["cached"]:
            key = "need_asr"
        elif not self.ready_for_dictation:
            key = "need_llm"
        elif not self.input_permissions_ready:
            key = "need_input"
        else:
            key = "ready"
        self._controls["summary"].setStringValue_(self._text(key))

    def _render_service(self):
        snapshot = self._ollama_snapshot
        if self._starting_service:
            status = self._text("starting_service")
        elif snapshot["running"]:
            status = self._text("service_ready", count=len(snapshot["models"]))
        elif self._checking["ollama"]:
            status = self._text("checking")
        else:
            status = self._text("service_stopped", detail=snapshot.get("error", ""))
        field = self._controls["ollama.service"]
        field.setStringValue_(status)
        field.setToolTip_(status)
        action = "update_ollama" if self._ollama_update_required else "refresh_service" if snapshot["running"] else "start_ollama" if snapshot["installed"] else "install_ollama"
        self._controls["ollama.service.action"].setTitle_(self._text(action))
        self._controls["ollama.service.action"].setEnabled_(not self._starting_service)
        configured = str(self.config["llm_model"])
        models = snapshot["models"]
        self._model_choices = [model["name"] for model in models]
        titles = [f"{model['name']} ({format_bytes(model.get('size', 0))})" for model in models]
        if configured not in self._model_choices:
            self._model_choices.insert(0, configured)
            marker = self._text("installed" if self._selected_model_is_installed() else "not_installed")
            titles.insert(0, f"{configured} ({marker})")
        popup = self._controls["ollama.model"]
        popup.removeAllItems()
        popup.addItemsWithTitles_(titles)
        popup.selectItemAtIndex_(self._model_choices.index(configured))
        popup.setEnabled_(self._tasks["ollama"] is None)

    def _render_transfer(self, kind):
        state = self._states[kind]
        token = self._tasks[kind]
        progress = self._progress[kind]
        cached = self._asr_snapshot["cached"] if kind == "asr" else self._selected_model_is_installed()
        detail = ""
        percentage = 100.0 if cached else 0.0
        indeterminate = token is not None and (progress is None or progress.total <= 0)
        if state == "failed":
            text = self._text("failed", detail=self._errors[kind])
        elif token is not None:
            text = self._text(state) if state in ("preparing", "downloading", "validating", "cancelling") else progress.message
            if kind == "ollama":
                text = f"{self._task_models[kind]}: {text}"
            if progress is not None and progress.total > 0:
                percentage = progress.percent
                detail = f"{percentage:.1f}%  ·  {format_bytes(progress.completed)} / {format_bytes(progress.total)}"
        elif state == "cancelled":
            text = self._text("cancelled")
        elif state == "complete":
            text = self._text("complete")
            percentage = 100.0
        elif self._checking[kind]:
            text = self._text("checking")
        elif kind == "asr":
            text = self._text("cached" if cached else "missing_cache")
            if cached:
                detail = format_bytes(self._asr_snapshot["size_bytes"])
        elif not (self.config.get("polish_enabled") or self.config.get("translate_enabled")):
            text = self._text("optional_off")
        else:
            text = self._text("model_installed" if cached else "model_missing")
        if state in ("failed", "cancelled") and progress is not None and progress.total > 0:
            percentage = progress.percent
            detail = f"{percentage:.1f}%  ·  {format_bytes(progress.completed)} / {format_bytes(progress.total)}"
        bar = self._controls[f"{kind}.progress"]
        bar.setIndeterminate_(indeterminate)
        if indeterminate:
            bar.startAnimation_(None)
        else:
            bar.stopAnimation_(None)
            bar.setDoubleValue_(percentage)
        status = self._controls["asr.status" if kind == "asr" else "ollama.detail"]
        status.setStringValue_(text if kind == "asr" or not detail else f"{text}\n{detail}")
        status.setToolTip_(text)
        status.setTextColor_(AppKit.NSColor.systemRedColor() if state == "failed" else AppKit.NSColor.labelColor())
        self._controls[f"{kind}.error"].setHidden_(state != "failed" or not self._errors[kind])
        if kind == "asr":
            self._controls["asr.detail"].setStringValue_(detail)
        download = self._controls[f"{kind}.download"]
        label = "repair_asr" if kind == "asr" and self._asr_cache_error else "retry" if state in ("failed", "cancelled") else "download"
        download.setTitle_(self._text(label))
        download.setToolTip_(self._text("repair_asr_note") if label == "repair_asr" else None)
        download.setEnabled_(token is None and not self._checking[kind] and not cached and
                             (kind == "asr" or self._ollama_snapshot["running"]))
        self._controls[f"{kind}.cancel"].setEnabled_(token is not None and state != "cancelling")

    def _refresh_snapshot(self, kind, operation):
        if self._tasks[kind] is not None or self._checking[kind]:
            return
        self._checking[kind] = True
        self._epochs[kind] += 1
        epoch = self._epochs[kind]

        def inspect():
            try:
                snapshot = operation()
            except Exception as error:
                callAfter(self._snapshot_failed, kind, epoch, str(error))
            else:
                callAfter(self._snapshot_ready, kind, epoch, snapshot)

        self._start_worker(inspect, f"SpeakType-{kind}-status")

    def _snapshot_ready(self, kind, epoch, snapshot):
        if epoch != self._epochs[kind]:
            return
        self._checking[kind] = False
        if kind == "asr":
            self._asr_snapshot = snapshot
            self._asr_cache_error = False
        else:
            self._ollama_snapshot = snapshot
        if self._states[kind] == "checking":
            self._states[kind] = "idle"
        if (kind == "asr" and snapshot["cached"]) or (kind == "ollama" and self._selected_model_is_installed()):
            self._states[kind] = "idle"
            self._errors[kind] = ""
        if not self._shutting_down:
            self._render()

    def _snapshot_failed(self, kind, epoch, error):
        if epoch != self._epochs[kind]:
            return
        self._checking[kind] = False
        self._states[kind] = "failed"
        self._errors[kind] = error
        if kind == "asr":
            self._asr_snapshot = {"cached": False, "path": None, "size_bytes": 0}
            self._asr_cache_error = True
        else:
            self._ollama_snapshot.update({"running": False, "models": [], "error": error})
        if not self._shutting_down:
            self._render()

    def _start_transfer(self, kind, operation, model):
        if self._tasks[kind] is not None:
            return
        token = CancelToken()
        self._epochs[kind] += 1
        self._checking[kind] = False
        self._tasks[kind] = token
        self._task_models[kind] = model
        self._states[kind] = "preparing"
        self._errors[kind] = ""
        self._progress[kind] = None
        self._render()

        def run():
            last_update = 0.0

            def progress(value):
                nonlocal last_update
                now = time.monotonic()
                if value.state == "downloading" and now - last_update < 0.1:
                    return
                last_update = now
                callAfter(self._transfer_progress, kind, token, value)

            try:
                operation(progress, token)
            except DownloadCancelled:
                callAfter(self._transfer_finished, kind, token, "cancelled", "")
            except Exception as error:
                callAfter(self._transfer_finished, kind, token, "failed", error)
            else:
                callAfter(self._transfer_finished, kind, token, "complete", "")

        self._task_workers[kind] = self._start_worker(run, f"SpeakType-{kind}-download")

    def _transfer_progress(self, kind, token, progress):
        if self._shutting_down:
            return
        if self._tasks[kind] is not token or self._states[kind] == "cancelling":
            return
        self._progress[kind] = progress
        self._states[kind] = progress.state
        self._render()

    def _transfer_finished(self, kind, token, state, error):
        if self._tasks[kind] is not token:
            return
        model = self._task_models[kind]
        self._tasks[kind] = None
        self._task_workers[kind] = None
        self._task_models[kind] = None
        configured = self.config["asr_model" if kind == "asr" else "llm_model"]
        if state == "complete" and model != configured:
            state = "idle"
        self._states[kind] = state
        self._errors[kind] = str(error)
        if isinstance(error, OllamaUpdateRequired):
            self._ollama_update_required = True
        elif kind == "ollama" and state == "complete":
            self._ollama_update_required = False
        if self._shutting_down:
            return
        self._render()
        self.refresh()

    def _cancel_transfer(self, kind):
        token = self._tasks[kind]
        if token is not None:
            self._states[kind] = "cancelling"
            self._render()
            self._start_worker(token.cancel, f"SpeakType-{kind}-cancel")

    def _download_asr(self):
        model = str(self.config["asr_model"])
        force = self._asr_cache_error
        self._start_transfer("asr", lambda callback, token: download_asr(model, callback, token, force=force), model)

    def _download_ollama(self):
        url = str(self.config["ollama_url"])
        model = str(self.config["llm_model"])
        self._start_transfer("ollama", lambda callback, token: pull_ollama(url, model, callback, token), model)

    def _change_features(self):
        self._change_config({"polish_enabled": bool(self._controls["polish.enabled"].state()),
                             "translate_enabled": bool(self._controls["translation.enabled"].state())})

    def _change_config(self, patch):
        self.on_change(dict(patch))
        self.config.update(patch)
        if "llm_model" in patch and self._tasks["ollama"] is None:
            self._states["ollama"] = "idle"
            self._errors["ollama"] = ""
        self._render()

    def _selected_model_is_installed(self):
        return ollama_model_is_available(str(self.config["llm_model"]), [model["name"] for model in self._ollama_snapshot["models"]])

    def _open_permission(self, name):
        if name == "microphone":
            request_microphone_if_needed()
        elif name == "accessibility":
            status = get_permission_status()
            if not status.accessibility:
                AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
            if not status.post_event:
                Quartz.CGRequestPostEventAccess()
        elif name == "listen":
            if not get_permission_status().listen_event:
                Quartz.CGRequestListenEventAccess()
        self._open_url(SETTINGS_URLS[name])

    def _open_url(self, url):
        if not AppKit.NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(url)):
            raise RuntimeError(f"macOS could not open {url}")

    def _show_error(self, kind):
        error = self._errors[kind]
        if not error:
            return
        if self._error_alert is not None:
            self._error_alert.window().makeKeyAndOrderFront_(None)
            return
        alert = AppKit.NSAlert.alloc().init()
        alert.setAlertStyle_(AppKit.NSAlertStyleCritical)
        alert.setMessageText_(self._text("error_title"))
        alert.setInformativeText_(self._text("error_note"))
        alert.addButtonWithTitle_(self._text("close_error"))
        alert.addButtonWithTitle_(self._text("copy_error"))
        scroll = AppKit.NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 0, 560, 240))
        scroll.setHasVerticalScroller_(True)
        scroll.setBorderType_(AppKit.NSBezelBorder)
        view = AppKit.NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, 540, 240))
        view.setEditable_(False)
        view.setSelectable_(True)
        view.setFont_(AppKit.NSFont.systemFontOfSize_(12))
        view.setHorizontallyResizable_(False)
        view.setVerticallyResizable_(True)
        view.textContainer().setWidthTracksTextView_(True)
        view.setTextContainerInset_(NSMakeSize(10, 10))
        view.setString_(error)
        scroll.setDocumentView_(view)
        alert.setAccessoryView_(scroll)
        self._error_alert = alert
        self._error_view = view

        def completed(response):
            if response == AppKit.NSAlertSecondButtonReturn:
                pasteboard = AppKit.NSPasteboard.generalPasteboard()
                pasteboard.clearContents()
                if not pasteboard.setString_forType_(error, AppKit.NSPasteboardTypeString):
                    raise RuntimeError("macOS could not copy the model preparation error")
            self._error_alert = None
            self._error_view = None

        alert.beginSheetModalForWindow_completionHandler_(self.window, completed)

    def _service_action(self):
        if self._ollama_update_required:
            self._open_url(OLLAMA_INSTALL_URL)
            return
        if self._ollama_snapshot["running"]:
            self.refresh()
            return
        if not self._ollama_snapshot["installed"]:
            self._open_url(OLLAMA_INSTALL_URL)
            return
        if self._starting_service:
            return
        self._starting_service = True
        self._render()
        url = str(self.config["ollama_url"])

        def start():
            try:
                start_installed_ollama(url)
            except Exception as error:
                callAfter(self._service_started, str(error))
            else:
                callAfter(self._service_started, "")

        self._start_worker(start, "SpeakType-Ollama-start")

    def _service_started(self, error):
        self._starting_service = False
        if self._shutting_down:
            return
        if error:
            self._ollama_snapshot["error"] = error
            self._render()
        else:
            self.refresh()

    def _test(self):
        if self.ready_for_dictation:
            self.close()
            self.on_test()

    def _back(self):
        self.close()
        if self.on_ready is not None:
            self.on_ready()
