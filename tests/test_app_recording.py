"""Tests for recording lifecycle regressions in SpeakTypeApp."""

import threading
import time
from types import SimpleNamespace

from speaktype import app as app_mod


def _make_app():
    app = object.__new__(app_mod.SpeakTypeApp)
    app.config = {
        "sound_feedback": False,
        "streaming_preview": False,
        "sample_rate": 16000,
        "language": "auto",
        "plugins_enabled": False,
        "max_recording_seconds": None,
        "insert_method": "paste",
        "polish_enabled": True,
        "translate_enabled": False,
        "llm_model": "fake-model",
    }
    app._recording_start_time = time.time()
    app._is_processing = False
    app._recording_stop_lock = threading.Lock()
    app._recording_stop_requested = False
    app._last_insertion_text = None
    app._last_insertion_app = None
    app._last_insertion_bundle_id = None
    app._level_timer = None
    app._streaming_transcriber = None
    app._processing_thread = None
    app._permission_watch_thread = None
    app._permission_watch_stop = threading.Event()
    app._last_permission_status = None
    app._permission_restart_prompt_shown = False
    app.hotkey_listener = None
    app._plugin_manager = SimpleNamespace(run_hook=lambda *args, **kwargs: None)
    app._status_overlay = SimpleNamespace(
        show_recording=lambda: None,
        show_transcribing=lambda: None,
        show_done=lambda text, auto_hide_after=0.0: None,
        show_error=lambda text, auto_hide_after=0.0: None,
        hide=lambda delay=0.0: None,
        update_audio_level=lambda level: None,
        update_partial_text=lambda text: None,
    )
    app.asr = SimpleNamespace(_loaded=False)
    app.polish_engine = SimpleNamespace(prewarm_async=lambda: None)
    return app


def test_start_recording_does_not_show_overlay_when_recorder_fails(monkeypatch):
    app = _make_app()
    notifications = []
    shown = []

    app._status_overlay = SimpleNamespace(
        show_recording=lambda: shown.append(True),
        show_transcribing=lambda: None,
        show_done=lambda text, auto_hide_after=0.0: None,
        show_error=lambda text, auto_hide_after=0.0: None,
        hide=lambda delay=0.0: None,
        update_audio_level=lambda level: None,
        update_partial_text=lambda text: None,
    )
    app.recorder = SimpleNamespace(
        set_whisper_state_callback=lambda callback: None,
        set_stream_callback=lambda callback: None,
        start=lambda **kwargs: False,
        last_start_error=RuntimeError("mic unavailable"),
    )
    monkeypatch.setattr(app_mod.rumps, "notification", lambda title, subtitle, body: notifications.append((title, subtitle, body)))

    app_mod.SpeakTypeApp._start_recording(app)

    assert shown == []
    assert notifications == [("SpeakType", app_mod.t("notif_error"), "mic unavailable")]
    assert app._recording_start_time == 0


def test_handle_undo_last_refuses_cross_app_delete(monkeypatch):
    app = _make_app()
    deleted = []
    app._last_insertion_text = "hello"
    app._last_insertion_app = "Mail"
    app._last_insertion_bundle_id = "com.apple.mail"

    monkeypatch.setattr(app_mod, "get_active_app", lambda: {"name": "Notes", "bundle_id": "com.apple.Notes"})
    monkeypatch.setattr(app_mod, "delete_chars", lambda count: deleted.append(count))

    assert app_mod.SpeakTypeApp._handle_undo_last(app) is False
    assert deleted == []
    assert app._last_insertion_text == "hello"


def test_handle_edit_command_remembers_inserted_text(monkeypatch):
    app = _make_app()
    replaced = []
    app.polish_engine = SimpleNamespace(edit_text=lambda command, selected, tone: "rewritten")

    monkeypatch.setattr(app_mod, "get_selected_text", lambda: "original")
    monkeypatch.setattr(app_mod, "replace_selection", lambda text: replaced.append(text))

    result = app_mod.SpeakTypeApp._handle_edit_command(
        app,
        "rewrite this",
        "neutral",
        {"name": "Code", "bundle_id": "com.microsoft.VSCode"},
    )

    assert result is True
    assert replaced == ["rewritten"]
    assert app._last_insertion_text == "rewritten"
    assert app._last_insertion_bundle_id == "com.microsoft.VSCode"


def test_on_max_duration_reached_dispatches_to_main_thread():
    app = _make_app()
    dispatched = []
    app._bridge = SimpleNamespace(
        performSelectorOnMainThread_withObject_waitUntilDone_=lambda selector, obj, wait: dispatched.append((selector, wait))
    )

    app_mod.SpeakTypeApp._on_max_duration_reached(app)

    assert dispatched == [(b"handleMaxDurationReached:", False)]


def test_permission_refresh_runs_when_bundle_fingerprint_changes(monkeypatch):
    config = {
        "last_seen_version": "2.1.1",
        "last_seen_bundle_fingerprint": "old",
    }
    saved = []
    refreshed = []

    monkeypatch.setattr(app_mod, "APP_VERSION", "2.1.1")
    monkeypatch.setattr(app_mod, "get_running_bundle_path", lambda: "/Applications/SpeakType.app")
    monkeypatch.setattr(app_mod, "get_bundle_fingerprint", lambda bundle: "new")
    monkeypatch.setattr(app_mod, "save_config", lambda cfg: saved.append(dict(cfg)))
    monkeypatch.setattr(app_mod, "refresh_permissions_for_update", lambda bundle_id: refreshed.append(bundle_id))

    app_mod._refresh_permissions_after_bundle_update(config)

    assert config["last_seen_bundle_fingerprint"] == "new"
    assert config[app_mod.PERMISSION_RESTART_PENDING_KEY] is True
    assert saved and saved[-1]["last_seen_bundle_fingerprint"] == "new"
    assert saved[-1][app_mod.PERMISSION_RESTART_PENDING_KEY] is True
    assert refreshed == [app_mod.BUNDLE_IDENTIFIER]


def test_permission_refresh_skips_unchanged_bundle(monkeypatch):
    config = {
        "last_seen_version": "2.1.1",
        "last_seen_bundle_fingerprint": "same",
    }
    refreshed = []

    monkeypatch.setattr(app_mod, "APP_VERSION", "2.1.1")
    monkeypatch.setattr(app_mod, "get_running_bundle_path", lambda: "/Applications/SpeakType.app")
    monkeypatch.setattr(app_mod, "get_bundle_fingerprint", lambda bundle: "same")
    monkeypatch.setattr(app_mod, "save_config", lambda cfg: (_ for _ in ()).throw(AssertionError("unchanged bundle should not save")))
    monkeypatch.setattr(app_mod, "refresh_permissions_for_update", lambda bundle_id: refreshed.append(bundle_id))

    app_mod._refresh_permissions_after_bundle_update(config)

    assert refreshed == []


def test_permission_transition_detects_newly_complete_grant():
    previous = SimpleNamespace(all_granted=False)
    current = SimpleNamespace(all_granted=True)

    assert app_mod._permission_status_transitioned_to_granted(previous, current) is True
    assert app_mod._permission_status_transitioned_to_granted(current, current) is False


def test_permission_transition_detects_partial_new_grant_after_refresh():
    previous = SimpleNamespace(
        all_granted=False,
        accessibility=False,
        listen_event=False,
        post_event=False,
    )
    current = SimpleNamespace(
        all_granted=False,
        accessibility=True,
        listen_event=True,
        post_event=False,
    )

    assert app_mod._permission_status_has_new_grant(previous, current) is True
    assert app_mod._permission_status_has_new_grant(current, current) is False
    assert app_mod._permission_status_transitioned_to_granted(None, current) is False


def test_permission_restart_watcher_skips_when_permissions_already_granted(monkeypatch):
    app = _make_app()

    monkeypatch.setattr(app_mod, "get_permission_status", lambda: SimpleNamespace(all_granted=True))

    app_mod.SpeakTypeApp._start_permission_restart_watcher(app)

    assert app._permission_watch_thread is None


def test_permission_restart_watcher_prompts_if_refresh_pending_and_already_granted(monkeypatch):
    app = _make_app()
    app.config[app_mod.PERMISSION_RESTART_PENDING_KEY] = True
    dispatched = []
    saved = []
    app._bridge = SimpleNamespace(
        performSelectorOnMainThread_withObject_waitUntilDone_=lambda selector, obj, wait: dispatched.append((selector, wait))
    )

    monkeypatch.setattr(app_mod, "get_permission_status", lambda: SimpleNamespace(all_granted=True))
    monkeypatch.setattr(app_mod, "save_config", lambda cfg: saved.append(dict(cfg)))

    app_mod.SpeakTypeApp._start_permission_restart_watcher(app)

    assert app._permission_watch_thread is None
    assert app._permission_restart_prompt_shown is True
    assert app.config[app_mod.PERMISSION_RESTART_PENDING_KEY] is False
    assert saved[-1][app_mod.PERMISSION_RESTART_PENDING_KEY] is False
    assert dispatched == [(b"showPermissionRestartAlert:", False)]


def test_permission_restart_watcher_does_not_prompt_before_any_grant(monkeypatch):
    app = _make_app()
    app.config[app_mod.PERMISSION_RESTART_PENDING_KEY] = True
    dispatched = []
    saved = []
    app._bridge = SimpleNamespace(
        performSelectorOnMainThread_withObject_waitUntilDone_=lambda selector, obj, wait: dispatched.append((selector, wait))
    )

    monkeypatch.setattr(app_mod, "get_permission_status", lambda: SimpleNamespace(all_granted=False))
    monkeypatch.setattr(app_mod, "save_config", lambda cfg: saved.append(dict(cfg)))

    app_mod.SpeakTypeApp._start_permission_restart_watcher(app)

    assert app._permission_restart_prompt_shown is False
    assert app.config[app_mod.PERMISSION_RESTART_PENDING_KEY] is True
    assert saved == []
    assert dispatched == []
    assert app._permission_watch_thread is not None
    app._permission_watch_stop.set()


def test_start_level_monitor_dispatches_to_main_thread():
    app = _make_app()
    dispatched = []
    app._bridge = SimpleNamespace(
        performSelectorOnMainThread_withObject_waitUntilDone_=lambda selector, obj, wait: dispatched.append((selector, wait))
    )

    app_mod.SpeakTypeApp._start_level_monitor(app)

    assert dispatched == [(b"startLevelMonitor:", True)]


def test_stop_recording_is_idempotent():
    app = _make_app()
    stop_calls = []
    app.recorder = SimpleNamespace(
        is_recording=True,
        stop=lambda: stop_calls.append(True) or None,
        set_stream_callback=lambda callback: None,
    )

    app_mod.SpeakTypeApp._stop_recording(app)
    app_mod.SpeakTypeApp._stop_recording(app)

    assert stop_calls == [True]


def test_stop_recording_handles_missing_start_time_without_huge_duration(monkeypatch):
    app = _make_app()
    audio_input = object()
    thread_calls = []
    app._recording_start_time = 0
    app.asr = SimpleNamespace(backend="qwen")
    app.recorder = SimpleNamespace(
        is_recording=True,
        stop_audio=lambda: audio_input,
        stop=lambda: (_ for _ in ()).throw(AssertionError("stop() should not be called")),
        set_stream_callback=lambda callback: None,
    )
    app._stop_level_monitor = lambda: None
    app._status_overlay = SimpleNamespace(show_transcribing=lambda: None, hide=lambda delay=0.0: None)
    app._processing_thread = None

    class FakeThread:
        def __init__(self, target=None, args=(), daemon=None):
            thread_calls.append((target, args, daemon))

        def start(self):
            return None

    monkeypatch.setattr(app_mod.threading, "Thread", FakeThread)

    app_mod.SpeakTypeApp._stop_recording(app)

    assert len(thread_calls) == 1
    assert 0 <= thread_calls[0][1][1] < 1


def test_stop_recording_stops_streaming_transcriber_without_waiting(monkeypatch):
    app = _make_app()
    streaming_stop_calls = []
    app.recorder = SimpleNamespace(
        is_recording=True,
        stop=lambda: None,
        set_stream_callback=lambda callback: None,
    )
    app._streaming_transcriber = SimpleNamespace(
        stop=lambda wait=True: streaming_stop_calls.append(wait)
    )
    app._stop_level_monitor = lambda: None
    app._status_overlay = SimpleNamespace(show_transcribing=lambda: None, hide=lambda delay=0.0: None)
    app._processing_thread = None

    monkeypatch.setattr(app_mod.threading, "Thread", lambda target=None, args=(), daemon=None: SimpleNamespace(start=lambda: None))

    app_mod.SpeakTypeApp._stop_recording(app)

    assert streaming_stop_calls == [False]


def test_stop_recording_uses_in_memory_audio_for_qwen_without_plugins(monkeypatch):
    app = _make_app()
    thread_calls = []
    audio_input = object()
    app.asr = SimpleNamespace(backend="qwen")
    app.recorder = SimpleNamespace(
        is_recording=True,
        stop_audio=lambda: audio_input,
        stop=lambda: (_ for _ in ()).throw(AssertionError("stop() should not be called")),
        set_stream_callback=lambda callback: None,
    )
    app._stop_level_monitor = lambda: None
    app._status_overlay = SimpleNamespace(show_transcribing=lambda: None, hide=lambda delay=0.0: None)
    app._processing_thread = None

    class FakeThread:
        def __init__(self, target=None, args=(), daemon=None):
            thread_calls.append((target, args, daemon))

        def start(self):
            return None

    monkeypatch.setattr(app_mod.threading, "Thread", FakeThread)

    app_mod.SpeakTypeApp._stop_recording(app)

    assert len(thread_calls) == 1
    assert thread_calls[0][0] == app._process_audio
    assert thread_calls[0][1][0] is audio_input
    assert isinstance(thread_calls[0][1][1], float)
    assert thread_calls[0][2] is True


def test_stop_recording_shows_asr_cold_start_status(monkeypatch):
    app = _make_app()
    thread_calls = []
    messages = []
    audio_input = object()
    app.asr = SimpleNamespace(backend="qwen", _loaded=False)
    app.recorder = SimpleNamespace(
        is_recording=True,
        stop_audio=lambda: audio_input,
        stop=lambda: (_ for _ in ()).throw(AssertionError("stop() should not be called")),
        set_stream_callback=lambda callback: None,
    )
    app._stop_level_monitor = lambda: None
    app._status_overlay = SimpleNamespace(
        show_transcribing=lambda text="": messages.append(text),
        show_error=lambda text, auto_hide_after=0.0: None,
        hide=lambda delay=0.0: None,
    )
    app._processing_thread = None

    class FakeThread:
        def __init__(self, target=None, args=(), daemon=None):
            thread_calls.append((target, args, daemon))

        def start(self):
            return None

    monkeypatch.setattr(app_mod.threading, "Thread", FakeThread)

    app_mod.SpeakTypeApp._stop_recording(app)

    assert messages == [app_mod.t("overlay_asr_loading")]
    assert len(thread_calls) == 1


def test_stop_recording_shows_too_short_audio_hint():
    app = _make_app()
    errors = []
    app.asr = SimpleNamespace(backend="qwen", _loaded=True)
    app.recorder = SimpleNamespace(
        is_recording=True,
        stop_audio=lambda: None,
        stop=lambda: (_ for _ in ()).throw(AssertionError("stop() should not be called")),
        set_stream_callback=lambda callback: None,
        last_stop_reason="too_short",
        last_stop_message="Recording was too short",
    )
    app._stop_level_monitor = lambda: None
    app._status_overlay = SimpleNamespace(
        show_transcribing=lambda text="": None,
        show_error=lambda text, auto_hide_after=0.0: errors.append((text, auto_hide_after)),
        hide=lambda delay=0.0: None,
    )

    app_mod.SpeakTypeApp._stop_recording(app)

    assert errors == [(app_mod.t("overlay_audio_too_short"), 2.0)]
    assert app._is_processing is False


def test_stop_recording_keeps_file_path_flow_when_plugins_enabled(monkeypatch):
    app = _make_app()
    app.config["plugins_enabled"] = True
    thread_calls = []
    app.asr = SimpleNamespace(backend="qwen")
    app.recorder = SimpleNamespace(
        is_recording=True,
        stop_audio=lambda: (_ for _ in ()).throw(AssertionError("stop_audio() should not be called")),
        stop=lambda: "/tmp/fake.wav",
        set_stream_callback=lambda callback: None,
    )
    app._stop_level_monitor = lambda: None
    app._status_overlay = SimpleNamespace(show_transcribing=lambda: None, hide=lambda delay=0.0: None)
    app._processing_thread = None

    class FakeThread:
        def __init__(self, target=None, args=(), daemon=None):
            thread_calls.append((target, args, daemon))

        def start(self):
            return None

    monkeypatch.setattr(app_mod.threading, "Thread", FakeThread)

    app_mod.SpeakTypeApp._stop_recording(app)

    assert len(thread_calls) == 1
    assert thread_calls[0][0] == app._process_audio
    assert thread_calls[0][1][0] == "/tmp/fake.wav"
    assert isinstance(thread_calls[0][1][1], float)
    assert thread_calls[0][2] is True


def test_prime_pipeline_for_recording_starts_warm_paths(monkeypatch):
    app = _make_app()
    app.config["streaming_preview"] = True
    calls = []
    app.asr = SimpleNamespace(_loaded=False, load_async=lambda: calls.append("asr"))
    app.polish_engine = SimpleNamespace(prewarm_async=lambda: calls.append("llm"))

    started_threads = []

    class FakeThread:
        def __init__(self, target=None, args=(), kwargs=None, daemon=None, name=None):
            self._target = target
            self._args = args
            self._kwargs = kwargs or {}
            started_threads.append(name or "thread")

        def start(self):
            return None

    monkeypatch.setattr(app_mod.threading, "Thread", FakeThread)

    app_mod.SpeakTypeApp._prime_pipeline_for_recording(app)

    assert calls == ["asr", "llm"]
    assert started_threads


def test_process_audio_combines_polish_and_translate_when_plugins_disabled(monkeypatch):
    app = _make_app()
    app.config.update(
        {
            "translate_enabled": True,
            "translate_target": "zh",
            "voice_commands_enabled": False,
            "history_enabled": False,
            "context_aware_tone": False,
            "scene_prompts_enabled": False,
            "auto_punctuation": True,
            "filler_removal": True,
        }
    )

    combined_calls = []
    inserted = []
    remembered = []

    app.asr = SimpleNamespace(transcribe=lambda audio_path, language="auto": "hello world")
    app.polish_engine = SimpleNamespace(
        polish_and_translate=lambda text, **kwargs: combined_calls.append((text, kwargs)) or "你好，世界",
        polish=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("polish() should not be called")),
        translate=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("translate() should not be called")),
    )
    app.snippets = SimpleNamespace(match=lambda text: None)
    app.corrections = SimpleNamespace(apply=lambda text: text)
    app.history = SimpleNamespace(add_async=lambda **kwargs: None)
    app._status_overlay = SimpleNamespace(
        show_polishing=lambda text: None,
        show_done=lambda text: None,
        hide=lambda delay=0.0: None,
    )
    app._remember_last_insertion = lambda text, app_info: remembered.append((text, app_info))
    app._log_pipeline_latency = lambda marks: None

    monkeypatch.setattr(app_mod, "get_active_app", lambda: {"name": "Notes", "bundle_id": "com.apple.Notes"})
    monkeypatch.setattr(app_mod, "process_punctuation_commands", lambda text: text)
    monkeypatch.setattr(app_mod, "insert_text", lambda text, method, app_name="", bundle_id="": inserted.append((text, method, app_name, bundle_id)) or True)

    app_mod.SpeakTypeApp._process_audio(app, "/tmp/fake.wav", 1.0)

    assert combined_calls == [
        (
            "hello world",
            {
                "tone": "neutral",
                "target_lang": "zh",
                "auto_punctuation": True,
                "filler_removal": True,
                "scene": None,
                "scene_template": None,
            },
        )
    ]
    assert inserted == [("你好，世界", "paste", "Notes", "com.apple.Notes")]
    assert remembered == [("你好，世界", {"name": "Notes", "bundle_id": "com.apple.Notes"})]


def test_process_audio_notifies_once_when_polish_falls_back_unavailable(monkeypatch):
    app = _make_app()
    app.config.update(
        {
            "voice_commands_enabled": False,
            "history_enabled": False,
            "context_aware_tone": False,
            "scene_prompts_enabled": False,
            "auto_punctuation": True,
            "filler_removal": True,
        }
    )

    inserted = []
    notifications = []

    class FakePolishEngine:
        last_error = "Ollama is not running. Start with: ollama serve"

        def polish(self, text, **kwargs):
            return text

    app.asr = SimpleNamespace(transcribe=lambda audio_path, language="auto": "hello world")
    app.polish_engine = FakePolishEngine()
    app.snippets = SimpleNamespace(match=lambda text: None)
    app.corrections = SimpleNamespace(apply=lambda text: text)
    app.history = SimpleNamespace(add_async=lambda **kwargs: None)
    app._status_overlay = SimpleNamespace(
        show_polishing=lambda text: None,
        show_done=lambda text: None,
        hide=lambda delay=0.0: None,
    )
    app._remember_last_insertion = lambda text, app_info: None
    app._log_pipeline_latency = lambda marks: None

    monkeypatch.setattr(app_mod, "get_active_app", lambda: {"name": "Notes", "bundle_id": "com.apple.Notes"})
    monkeypatch.setattr(app_mod, "process_punctuation_commands", lambda text: text)
    monkeypatch.setattr(app_mod, "insert_text", lambda text, method, app_name="", bundle_id="": inserted.append(text) or True)
    monkeypatch.setattr(app_mod.rumps, "notification", lambda title, subtitle, body: notifications.append((title, subtitle, body)))

    app_mod.SpeakTypeApp._process_audio(app, "/tmp/fake.wav", 1.0)
    app_mod.SpeakTypeApp._process_audio(app, "/tmp/fake.wav", 1.0)

    assert inserted == ["hello world", "hello world"]
    assert notifications == [
        (
            "SpeakType",
            app_mod.t("notif_llm_unavail_title"),
            app_mod.t("notif_llm_ollama_not_running_body", model="fake-model"),
        )
    ]


def test_process_audio_shows_raw_insert_notice_when_polish_falls_back(monkeypatch):
    app = _make_app()
    app.config.update(
        {
            "voice_commands_enabled": False,
            "history_enabled": False,
            "context_aware_tone": False,
            "scene_prompts_enabled": False,
            "auto_punctuation": True,
            "filler_removal": True,
        }
    )
    notices = []

    class FakePolishEngine:
        last_error = "Ollama is not running. Start with: ollama serve"

        def polish(self, text, **kwargs):
            return text

    app.asr = SimpleNamespace(transcribe=lambda audio_path, language="auto": "hello world")
    app.polish_engine = FakePolishEngine()
    app.snippets = SimpleNamespace(match=lambda text: None)
    app.corrections = SimpleNamespace(apply=lambda text: text)
    app.history = SimpleNamespace(add_async=lambda **kwargs: None)
    app._status_overlay = SimpleNamespace(
        show_polishing=lambda text: None,
        show_done=lambda text, auto_hide_after=0.0: None,
        show_notice=lambda text, auto_hide_after=0.0: notices.append((text, auto_hide_after)),
        hide=lambda delay=0.0: None,
    )
    app._remember_last_insertion = lambda text, app_info: None
    app._log_pipeline_latency = lambda marks: None

    monkeypatch.setattr(app_mod, "get_active_app", lambda: {"name": "Notes", "bundle_id": "com.apple.Notes"})
    monkeypatch.setattr(app_mod, "process_punctuation_commands", lambda text: text)
    monkeypatch.setattr(app_mod, "insert_text", lambda text, method, app_name="", bundle_id="": True)
    monkeypatch.setattr(app_mod.rumps, "notification", lambda title, subtitle, body: None)

    app_mod.SpeakTypeApp._process_audio(app, "/tmp/fake.wav", 1.0)

    assert (
        app_mod.t("overlay_llm_ollama_not_running_raw"),
        2.2,
    ) in notices


def test_llm_fallback_notice_distinguishes_missing_model():
    app = _make_app()
    app.polish_engine = SimpleNamespace(
        model="fake-model",
        last_error="No Ollama LLM model is available. Available models: ['qwen3.5:4b']",
    )

    assert app_mod.SpeakTypeApp._llm_unavailable_notification_body(app) == app_mod.t(
        "notif_llm_model_missing_body",
        model="fake-model",
    )
    assert app_mod.SpeakTypeApp._llm_fallback_overlay_text(app) == app_mod.t(
        "overlay_llm_model_missing_raw",
        model="fake-model",
    )


def test_llm_fallback_notice_distinguishes_timeout():
    app = _make_app()
    app.config["ollama_url"] = "http://localhost:11434"
    app.polish_engine = SimpleNamespace(
        model="fake-model",
        last_error="Ollama request timed out",
    )

    assert app_mod.SpeakTypeApp._llm_unavailable_notification_body(app) == app_mod.t(
        "notif_llm_ollama_timeout_body",
        model="fake-model",
        url="http://localhost:11434",
    )
    assert app_mod.SpeakTypeApp._llm_fallback_overlay_text(app) == app_mod.t(
        "overlay_llm_ollama_timeout_raw"
    )


def test_process_audio_surfaces_unverified_insert(monkeypatch):
    app = _make_app()
    app.config.update(
        {
            "polish_enabled": False,
            "translate_enabled": False,
            "voice_commands_enabled": False,
            "history_enabled": False,
            "context_aware_tone": False,
        }
    )
    notices = []

    app.asr = SimpleNamespace(transcribe=lambda audio_path, language="auto": "hello")
    app.snippets = SimpleNamespace(match=lambda text: None)
    app.corrections = SimpleNamespace(apply=lambda text: text)
    app.history = SimpleNamespace(add_async=lambda **kwargs: None)
    app._status_overlay = SimpleNamespace(
        show_polishing=lambda text: None,
        show_done=lambda text, auto_hide_after=0.0: None,
        show_notice=lambda text, auto_hide_after=0.0: notices.append((text, auto_hide_after)),
        hide=lambda delay=0.0: None,
    )
    app._remember_last_insertion = lambda text, app_info: None
    app._log_pipeline_latency = lambda marks: None

    diagnostic = SimpleNamespace(success=True, verified=False, method="paste", reason="unverifiable_target")
    monkeypatch.setattr(app_mod, "get_active_app", lambda: {"name": "Chrome", "bundle_id": "com.google.Chrome"})
    monkeypatch.setattr(app_mod, "process_punctuation_commands", lambda text: text)
    monkeypatch.setattr(app_mod, "insert_text", lambda text, method, app_name="", bundle_id="": True)
    monkeypatch.setattr(app_mod, "get_last_insert_diagnostic", lambda: diagnostic)

    app_mod.SpeakTypeApp._process_audio(app, "/tmp/fake.wav", 1.0)

    assert (
        app_mod.t("overlay_insert_unverified", app="Chrome"),
        2.2,
    ) in notices


def test_process_audio_with_translate_disabled_never_calls_translate(monkeypatch):
    app = _make_app()
    app.config.update(
        {
            "translate_enabled": False,
            "translate_target": "en",
            "voice_commands_enabled": False,
            "history_enabled": False,
            "context_aware_tone": False,
            "scene_prompts_enabled": False,
            "auto_punctuation": True,
            "filler_removal": True,
        }
    )

    polish_calls = []
    inserted = []

    app.asr = SimpleNamespace(transcribe=lambda audio_path, language="auto": "中文内容")
    app.polish_engine = SimpleNamespace(
        last_error="",
        polish=lambda text, **kwargs: polish_calls.append((text, kwargs)) or "中文内容。",
        translate=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("translate() should not be called")),
        polish_and_translate=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("polish_and_translate() should not be called")),
    )
    app.snippets = SimpleNamespace(match=lambda text: None)
    app.corrections = SimpleNamespace(apply=lambda text: text)
    app.history = SimpleNamespace(add_async=lambda **kwargs: None)
    app._status_overlay = SimpleNamespace(
        show_polishing=lambda text: None,
        show_done=lambda text: None,
        hide=lambda delay=0.0: None,
    )
    app._remember_last_insertion = lambda text, app_info: None
    app._log_pipeline_latency = lambda marks: None

    monkeypatch.setattr(app_mod, "get_active_app", lambda: {"name": "Codex", "bundle_id": "com.openai.codex"})
    monkeypatch.setattr(app_mod, "process_punctuation_commands", lambda text: text)
    monkeypatch.setattr(app_mod, "insert_text", lambda text, method, app_name="", bundle_id="": inserted.append(text) or True)

    app_mod.SpeakTypeApp._process_audio(app, "/tmp/fake.wav", 1.0)

    assert polish_calls[0][0] == "中文内容"
    assert inserted == ["中文内容。"]


def test_process_audio_with_polish_disabled_skips_llm_even_when_translate_target_is_english(monkeypatch):
    app = _make_app()
    app.config.update(
        {
            "polish_enabled": False,
            "translate_enabled": False,
            "translate_target": "en",
            "voice_commands_enabled": False,
            "history_enabled": False,
            "context_aware_tone": False,
            "scene_prompts_enabled": False,
        }
    )

    inserted = []
    app.asr = SimpleNamespace(transcribe=lambda audio_path, language="auto": "中文内容")
    app.polish_engine = SimpleNamespace(
        polish=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("polish() should not be called")),
        translate=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("translate() should not be called")),
        polish_and_translate=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("polish_and_translate() should not be called")),
    )
    app.snippets = SimpleNamespace(match=lambda text: None)
    app.corrections = SimpleNamespace(apply=lambda text: text)
    app.history = SimpleNamespace(add_async=lambda **kwargs: None)
    app._status_overlay = SimpleNamespace(
        show_polishing=lambda text: None,
        show_done=lambda text: None,
        hide=lambda delay=0.0: None,
    )
    app._remember_last_insertion = lambda text, app_info: None
    app._log_pipeline_latency = lambda marks: None

    monkeypatch.setattr(app_mod, "get_active_app", lambda: {"name": "Codex", "bundle_id": "com.openai.codex"})
    monkeypatch.setattr(app_mod, "process_punctuation_commands", lambda text: text)
    monkeypatch.setattr(app_mod, "insert_text", lambda text, method, app_name="", bundle_id="": inserted.append(text) or True)

    app_mod.SpeakTypeApp._process_audio(app, "/tmp/fake.wav", 1.0)

    assert inserted == ["中文内容"]


def test_process_audio_notifies_when_insert_fails(monkeypatch):
    app = _make_app()
    app.config.update(
        {
            "polish_enabled": False,
            "translate_enabled": False,
            "voice_commands_enabled": False,
            "history_enabled": False,
            "context_aware_tone": False,
        }
    )
    notifications = []
    errors = []

    app.asr = SimpleNamespace(transcribe=lambda audio_path, language="auto": "hello")
    app.snippets = SimpleNamespace(match=lambda text: None)
    app.corrections = SimpleNamespace(apply=lambda text: text)
    app.history = SimpleNamespace(add_async=lambda **kwargs: (_ for _ in ()).throw(AssertionError("history should not be saved")))
    app._status_overlay = SimpleNamespace(
        show_polishing=lambda text: None,
        show_done=lambda text: None,
        show_error=lambda text, auto_hide_after=0.0: errors.append((text, auto_hide_after)),
        hide=lambda delay=0.0: None,
    )
    app._remember_last_insertion = lambda text, app_info: (_ for _ in ()).throw(AssertionError("failed insert should not be remembered"))
    app._log_pipeline_latency = lambda marks: None

    monkeypatch.setattr(app_mod, "get_active_app", lambda: {"name": "Codex", "bundle_id": "com.openai.codex"})
    monkeypatch.setattr(app_mod, "process_punctuation_commands", lambda text: text)
    monkeypatch.setattr(app_mod, "insert_text", lambda text, method, app_name="", bundle_id="": False)
    monkeypatch.setattr(app_mod.rumps, "notification", lambda title, subtitle, body: notifications.append((title, subtitle, body)))

    app_mod.SpeakTypeApp._process_audio(app, "/tmp/fake.wav", 1.0)

    assert errors == [(app_mod.t("overlay_insert_failed", app="Codex"), 3.0)]
    assert notifications == [
        (
            "SpeakType",
            app_mod.t("notif_insert_failed_title"),
            app_mod.t(
                "notif_insert_failed_body",
                app="Codex",
                hint=app_mod.t("insert_hint_generic"),
            ),
        )
    ]
