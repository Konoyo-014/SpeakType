"""Tests for hotkey state handling."""

from speaktype.hotkey import HotkeyListener


class _FakeBackend:
    name = "fake"

    def __init__(self, dispatch_event):
        self._dispatch_event = dispatch_event
        self.running = False

    @property
    def is_running(self):
        return self.running

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def emit(self, event_type, key_name):
        self._dispatch_event(event_type, key_name)


class TestHotkeyListener:
    def _make_listener(self, **kwargs):
        holder = {}

        def factory(dispatch_event):
            backend = _FakeBackend(dispatch_event)
            holder["backend"] = backend
            return backend

        listener = HotkeyListener(backend_factory=factory, **kwargs)
        listener._dispatch_callback = lambda callback, *args: callback(*args) if callback else None
        listener.start()
        return listener, holder["backend"]

    def test_push_to_talk_single_key(self):
        events = []
        listener, backend = self._make_listener(
            hotkey_name="right_cmd",
            on_press=lambda: events.append("press"),
            on_release=lambda: events.append("release"),
        )

        backend.emit("down", "cmd_r")
        backend.emit("down", "cmd_r")
        backend.emit("up", "cmd_r")

        assert events == ["press", "release"]
        assert listener.backend_name == "fake"
        assert not listener.is_active
        listener.stop()
        assert not listener.is_running

    def test_toggle_mode_toggles_once_per_press(self):
        states = []
        listener, backend = self._make_listener(
            hotkey_name="f5",
            mode="toggle",
            on_toggle=lambda is_active: states.append(is_active),
        )

        backend.emit("down", "f5")
        backend.emit("down", "f5")
        backend.emit("up", "f5")
        backend.emit("down", "f5")
        backend.emit("up", "f5")

        assert states == [True, False]
        assert not listener.is_active
        listener.stop()

    def test_combo_hotkey_requires_all_parts(self):
        events = []
        listener, backend = self._make_listener(
            hotkey_name="ctrl+shift+space",
            on_press=lambda: events.append("press"),
            on_release=lambda: events.append("release"),
        )

        backend.emit("down", "ctrl_r")
        backend.emit("down", "shift_l")
        assert events == []

        backend.emit("down", "space")
        assert events == ["press"]
        assert listener.is_active

        backend.emit("up", "space")
        assert events == ["press", "release"]
        assert not listener.is_active
        listener.stop()
