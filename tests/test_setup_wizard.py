from speaktype import setup_wizard
from speaktype.i18n import set_language
from speaktype.setup_wizard import (
    SetupWizardController,
    command_for_copy_sender,
    copy_confirmation_title,
    setup_wizard_asr_state_label_height,
    setup_wizard_download_error_text,
    setup_wizard_download_status_text,
    setup_wizard_llm_labels,
)


class _FakeSender:
    def __init__(self, tag):
        self._tag = tag

    def tag(self):
        return self._tag


def test_command_for_copy_sender_uses_button_specific_command():
    commands = {
        1: "ollama serve",
        2: "ollama pull huihui_ai/qwen3.5-abliterated:9b-Claude",
    }

    assert command_for_copy_sender(_FakeSender(1), "", commands) == "ollama serve"
    assert command_for_copy_sender(_FakeSender(2), "", commands).startswith("ollama pull")


def test_command_for_copy_sender_falls_back_for_missing_sender():
    assert command_for_copy_sender(None, "brew install ollama", {}) == "brew install ollama"


def test_setup_wizard_llm_labels_are_localized():
    set_language("zh")

    labels = setup_wizard_llm_labels()

    assert labels["service"] == "Ollama 本地服务"
    assert labels["model"] == "润色模型"
    assert copy_confirmation_title() == "已复制"


def test_setup_wizard_download_status_text_is_localized():
    try:
        set_language("zh")
        assert setup_wizard_download_status_text("Starting...") == "正在准备"
        assert setup_wizard_download_status_text("") == "正在准备"

        set_language("en")
        assert setup_wizard_download_status_text("Starting...") == "Starting"
    finally:
        set_language("zh")


def test_setup_wizard_download_error_text_is_user_readable():
    try:
        set_language("zh")
        assert "下载组件不兼容" in setup_wizard_download_error_text(
            "Unknown argument(s): {'name': 'huggingface_hub.snapshot_download'}"
        )
        assert "网络或 Hugging Face" in setup_wizard_download_error_text("HTTP 500 connection timed out")
        assert "没找到" in setup_wizard_download_error_text("404 not found")
    finally:
        set_language("zh")


def test_setup_wizard_asr_state_label_height_expands_for_long_errors():
    assert setup_wizard_asr_state_label_height("未检测到本地语音识别模型") == 22
    assert setup_wizard_asr_state_label_height("x" * 60) == 42
    assert setup_wizard_asr_state_label_height("x" * 120) == 60


def test_setup_wizard_starts_asr_download_only_after_action(monkeypatch):
    controller = object.__new__(SetupWizardController)
    controller._download_thread = None
    controller._asr_download_state = "idle"
    controller._asr_download_error = "previous"
    events = []
    controller._show_step = lambda: events.append(("show", controller._asr_download_state))
    controller._do_download = lambda: events.append("download")

    class FakeThread:
        def __init__(self, target=None, daemon=None):
            self._target = target
            self._started = False

        def is_alive(self):
            return self._started

        def start(self):
            self._started = True
            events.append("thread_start")
            self._target()

    monkeypatch.setattr(setup_wizard.threading, "Thread", FakeThread)

    assert controller._asr_download_state == "idle"

    controller._start_asr_download()

    assert controller._asr_download_state == "running"
    assert controller._asr_download_error == ""
    assert events == [("show", "running"), "thread_start", "download"]


def test_setup_wizard_error_update_rebuilds_full_asr_error_state(monkeypatch):
    controller = object.__new__(SetupWizardController)
    events = []
    controller._progress_bar = object()
    controller._progress_label = object()
    controller._asr_download_state = "running"
    controller._asr_download_error = ""
    controller._show_step = lambda: events.append((controller._asr_download_state, controller._asr_download_error))

    controller._update_progress_ui(-1, "404 not found")

    assert controller._asr_download_state == "error"
    assert controller._asr_download_error == "404 not found"
    assert events == [("error", "404 not found")]
