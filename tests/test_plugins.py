"""Tests for the plugin system."""

import pytest
from pathlib import Path
from unittest.mock import patch

from speaktype.plugins import PluginManager, HOOK_POINTS


class TestPluginManager:
    def test_load_empty_dir(self, tmp_path):
        pm = PluginManager(plugins_dir=str(tmp_path))
        pm.load_all()
        # Should create example plugin but not load it (starts with _)
        assert len(pm.get_plugins()) == 0
        assert (tmp_path / "_example_plugin.py").exists()

    def test_load_simple_plugin(self, tmp_path):
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text('''
PLUGIN_NAME = "Test"
PLUGIN_VERSION = "1.0"
PLUGIN_DESCRIPTION = "A test plugin"

def post_transcribe(text):
    return text.upper()
''')
        pm = PluginManager(plugins_dir=str(tmp_path))
        pm.load_all()
        plugins = pm.get_plugins()
        assert len(plugins) == 1
        assert plugins[0]["name"] == "Test"
        assert "post_transcribe" in plugins[0]["hooks"]

    def test_run_hook_transforms_data(self, tmp_path):
        plugin_file = tmp_path / "upper.py"
        plugin_file.write_text('''
def post_transcribe(text):
    return text.upper()
''')
        pm = PluginManager(plugins_dir=str(tmp_path))
        pm.load_all()
        result = pm.run_hook("post_transcribe", "hello")
        assert result == "HELLO"

    def test_run_hook_no_handlers(self, tmp_path):
        pm = PluginManager(plugins_dir=str(tmp_path))
        pm.load_all()
        result = pm.run_hook("post_transcribe", "hello")
        assert result == "hello"

    def test_run_hook_chain(self, tmp_path):
        (tmp_path / "a_first.py").write_text('''
def post_transcribe(text):
    return text + " A"
''')
        (tmp_path / "b_second.py").write_text('''
def post_transcribe(text):
    return text + " B"
''')
        pm = PluginManager(plugins_dir=str(tmp_path))
        pm.load_all()
        result = pm.run_hook("post_transcribe", "start")
        assert result == "start A B"

    def test_notification_hook(self, tmp_path):
        calls = []
        plugin_file = tmp_path / "notifier.py"
        plugin_file.write_text('''
import sys
def on_recording_start():
    # Side effect only
    pass
''')
        pm = PluginManager(plugins_dir=str(tmp_path))
        pm.load_all()
        # Should not raise
        pm.run_hook("on_recording_start")

    def test_disable_plugin(self, tmp_path):
        (tmp_path / "upper.py").write_text('''
PLUGIN_NAME = "Upper"
def post_transcribe(text):
    return text.upper()
''')
        pm = PluginManager(plugins_dir=str(tmp_path))
        pm.load_all()
        assert pm.run_hook("post_transcribe", "hello") == "HELLO"

        pm.set_enabled("upper", False)
        assert pm.run_hook("post_transcribe", "hello") == "hello"

    def test_reload_all_does_not_duplicate_plugins(self, tmp_path):
        (tmp_path / "upper.py").write_text('''
def post_transcribe(text):
    return text.upper()
''')
        pm = PluginManager(plugins_dir=str(tmp_path))
        pm.load_all()
        pm.reload_all()

        assert len(pm.get_plugins()) == 1
        assert pm.run_hook("post_transcribe", "hello") == "HELLO"

    def test_clear_unloads_plugins(self, tmp_path):
        (tmp_path / "upper.py").write_text('''
def post_transcribe(text):
    return text.upper()
''')
        pm = PluginManager(plugins_dir=str(tmp_path))
        pm.load_all()
        pm.clear()

        assert pm.get_plugins() == []
        assert pm.run_hook("post_transcribe", "hello") == "hello"

    def test_broken_plugin_does_not_crash(self, tmp_path):
        (tmp_path / "broken.py").write_text('''
def post_transcribe(text):
    raise RuntimeError("oops")
''')
        pm = PluginManager(plugins_dir=str(tmp_path))
        pm.load_all()
        # Should not raise — exception is caught, result unchanged
        result = pm.run_hook("post_transcribe", "hello")
        assert result == "hello"

    def test_pre_insert_none_skips(self, tmp_path):
        (tmp_path / "skipper.py").write_text('''
def pre_insert(text):
    if "skip" in text:
        return None
    return text
''')
        pm = PluginManager(plugins_dir=str(tmp_path))
        pm.load_all()
        assert pm.run_hook("pre_insert", "skip this") is None
        assert pm.run_hook("pre_insert", "keep this") == "keep this"
