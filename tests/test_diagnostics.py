"""Tests for local readiness diagnostics."""

from speaktype import diagnostics
from speaktype import diagnostics_window
from speaktype.inserter import FocusedInputDiagnostic


class _FakeSubview:
    def __init__(self):
        self.removed = False

    def removeFromSuperview(self):
        self.removed = True


class _FakeRowsView:
    def __init__(self):
        self._subviews = [_FakeSubview()]
        self.added = []
        self.frame = None

    def subviews(self):
        return list(self._subviews)

    def addSubview_(self, view):
        self.added.append(view)

    def setFrame_(self, frame):
        self.frame = frame


def test_check_ollama_reports_missing_install_without_network(monkeypatch):
    called = []

    monkeypatch.setattr(diagnostics, "find_ollama_binary", lambda: "")
    monkeypatch.setattr(
        diagnostics,
        "_ollama_tags",
        lambda url: called.append(url) or ([], ""),
    )

    items = diagnostics.check_ollama(
        {
            "llm_model": "qwen2.5:3b",
            "ollama_url": "http://localhost:11434",
        }
    )

    assert [item.key for item in items] == [
        "ollama_install",
        "ollama_service",
        "ollama_model",
    ]
    assert [item.status for item in items] == ["warn", "warn", "warn"]
    assert called == []


def test_check_ollama_reports_running_model(monkeypatch):
    monkeypatch.setattr(diagnostics, "find_ollama_binary", lambda: "/opt/homebrew/bin/ollama")
    monkeypatch.setattr(
        diagnostics,
        "_ollama_tags",
        lambda url: ([{"name": "qwen2.5:3b"}], ""),
    )

    items = diagnostics.check_ollama(
        {
            "llm_model": "qwen2.5:3b",
            "ollama_url": "http://localhost:11434",
        }
    )

    assert [item.status for item in items] == ["ok", "ok", "ok"]


def test_check_ollama_reports_missing_model(monkeypatch):
    monkeypatch.setattr(diagnostics, "find_ollama_binary", lambda: "/opt/homebrew/bin/ollama")
    monkeypatch.setattr(
        diagnostics,
        "_ollama_tags",
        lambda url: ([{"name": "llama3.2:3b"}], ""),
    )

    items = diagnostics.check_ollama(
        {
            "llm_model": "qwen2.5:3b",
            "ollama_url": "http://localhost:11434",
        }
    )

    assert items[-1].key == "ollama_model"
    assert items[-1].status == "fail"
    assert "ollama pull" in items[-1].action


def test_check_target_input_reports_post_event_denied(monkeypatch):
    monkeypatch.setattr(
        diagnostics,
        "get_active_app",
        lambda: {"name": "Codex", "bundle_id": "com.openai.codex"},
    )
    monkeypatch.setattr(
        diagnostics,
        "inspect_focused_input",
        lambda app_name="", bundle_id="": FocusedInputDiagnostic(
            app_name=app_name,
            bundle_id=bundle_id,
            has_focused_element=True,
            role="AXTextArea",
            has_value=True,
            selected_text_readable=True,
            post_event_allowed=False,
            likely_writable=False,
            reason="post_event_denied",
        ),
    )

    item = diagnostics.check_target_input()

    assert item.key == "target_input"
    assert item.status == "fail"
    assert "Codex" in item.detail


def test_check_hotwords_reports_learning_state(monkeypatch):
    class FakeHotwordStore:
        def get_all(self):
            return [{"term": "Qwen3-ASR", "active": True}, {"term": "mlx-audio", "active": False}]

    monkeypatch.setattr(diagnostics, "HotwordStore", FakeHotwordStore)

    item = diagnostics.check_hotwords(
        {
            "hotword_learning_enabled": True,
            "hotword_context_enabled": True,
        }
    )

    assert item.key == "hotwords"
    assert item.status == "ok"
    assert "2" in item.detail
    assert "1" in item.detail


def test_render_diagnostics_text_includes_status_and_action():
    items = [
        diagnostics.DiagnosticItem(
            key="ollama_model",
            status="fail",
            title="Ollama model",
            detail="Missing qwen2.5:3b",
            action="ollama pull qwen2.5:3b",
        )
    ]

    text = diagnostics.render_diagnostics_text(items)

    assert "[FAIL] Ollama model" in text
    assert "Missing qwen2.5:3b" in text
    assert "ollama pull qwen2.5:3b" in text


def test_diagnostics_window_summary_is_localized():
    items = [
        diagnostics.DiagnosticItem("ok", "ok", "OK", "ready"),
        diagnostics.DiagnosticItem("warn", "warn", "Warn", "attention"),
        diagnostics.DiagnosticItem("fail", "fail", "Fail", "broken"),
    ]

    summary = diagnostics_window.diagnostics_summary_text(items, "fallback")

    assert "正常 1" in summary
    assert "注意 1" in summary
    assert "失败 1" in summary


def test_diagnostics_window_empty_rows_reset_document_height():
    controller = diagnostics_window.DiagnosticsWindowController({})
    rows = _FakeRowsView()
    controller._rows_view = rows
    controller._label = lambda *args, **kwargs: object()
    controller._font_weight = lambda name: 0.0

    controller._render_rows([], "正在检查本地状态...")

    assert rows._subviews[0].removed is True
    assert rows.added
    assert rows.frame.size.height == 364
