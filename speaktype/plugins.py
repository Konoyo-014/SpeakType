"""Plugin system for SpeakType extensibility."""

import importlib.util
import logging
from pathlib import Path
from .config import CONFIG_DIR, ensure_config_dir

logger = logging.getLogger("speaktype.plugins")

PLUGINS_DIR = CONFIG_DIR / "plugins"

# Hook points that plugins can register for
HOOK_POINTS = [
    "pre_transcribe",    # (audio_path) -> audio_path or None to skip
    "post_transcribe",   # (raw_text) -> modified text
    "pre_polish",        # (text, tone) -> (text, tone)
    "post_polish",       # (polished_text) -> modified text
    "pre_insert",        # (text) -> modified text or None to skip insertion
    "post_insert",       # (text) -> None (for side effects like logging)
    "on_recording_start",  # () -> None
    "on_recording_stop",   # () -> None
]


class Plugin:
    """Represents a loaded plugin."""

    def __init__(self, name: str, module, metadata: dict):
        self.name = name
        self.module = module
        self.metadata = metadata
        self.enabled = True
        self.hooks = {}

        # Discover hooks
        for hook in HOOK_POINTS:
            fn = getattr(module, hook, None)
            if callable(fn):
                self.hooks[hook] = fn


class PluginManager:
    """Discovers, loads, and manages plugins."""

    def __init__(self, plugins_dir: str = ""):
        self._plugins: list[Plugin] = []
        self._hooks: dict[str, list] = {h: [] for h in HOOK_POINTS}
        self._plugins_dir = Path(plugins_dir) if plugins_dir else PLUGINS_DIR

    def load_all(self):
        """Discover and load all plugins from the plugins directory."""
        ensure_config_dir()
        self._plugins_dir.mkdir(parents=True, exist_ok=True)

        # Create example plugin if directory is empty
        example = self._plugins_dir / "_example_plugin.py"
        if not any(self._plugins_dir.glob("*.py")):
            self._write_example_plugin(example)

        for path in sorted(self._plugins_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                self._load_plugin(path)
            except Exception as e:
                logger.error(f"Failed to load plugin {path.name}: {e}")

        # Build hook chain
        self._hooks = {h: [] for h in HOOK_POINTS}
        for plugin in self._plugins:
            if not plugin.enabled:
                continue
            for hook_name, fn in plugin.hooks.items():
                self._hooks[hook_name].append((plugin.name, fn))

        names = [p.name for p in self._plugins if p.enabled]
        if names:
            logger.info(f"Loaded {len(names)} plugin(s): {', '.join(names)}")

    def _load_plugin(self, path: Path):
        """Load a single plugin from a .py file."""
        name = path.stem
        spec = importlib.util.spec_from_file_location(f"speaktype_plugin_{name}", str(path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        metadata = {
            "name": getattr(module, "PLUGIN_NAME", name),
            "version": getattr(module, "PLUGIN_VERSION", "0.1"),
            "description": getattr(module, "PLUGIN_DESCRIPTION", ""),
            "author": getattr(module, "PLUGIN_AUTHOR", ""),
        }

        plugin = Plugin(name, module, metadata)
        self._plugins.append(plugin)

    def run_hook(self, hook_name: str, *args):
        """Execute all registered handlers for a hook point.

        For hooks that transform data (pre/post), the output of each handler
        is passed as input to the next. For notification hooks (on_*), all
        handlers are called but return values are ignored.
        """
        handlers = self._hooks.get(hook_name, [])
        if not handlers:
            return args[0] if args else None

        is_notification = hook_name.startswith("on_")
        result = args[0] if args else None

        for plugin_name, fn in handlers:
            try:
                if is_notification:
                    fn(*args)
                else:
                    out = fn(*args) if len(args) > 1 else fn(result)
                    # Propagate return value including None (used by pre_insert to skip).
                    # Plugins MUST return a value from transform hooks.
                    result = out
                    if len(args) > 1:
                        args = (result, *args[1:])
            except Exception as e:
                logger.warning(f"Plugin '{plugin_name}' hook '{hook_name}' failed: {e}")
                # On error, keep previous result unchanged

        return result

    def get_plugins(self) -> list[dict]:
        """Return info about all loaded plugins."""
        return [
            {
                "name": p.metadata["name"],
                "version": p.metadata["version"],
                "description": p.metadata["description"],
                "author": p.metadata["author"],
                "enabled": p.enabled,
                "hooks": list(p.hooks.keys()),
                "file": p.name,
            }
            for p in self._plugins
        ]

    def set_enabled(self, plugin_name: str, enabled: bool):
        """Enable or disable a plugin by name."""
        for p in self._plugins:
            if p.name == plugin_name or p.metadata["name"] == plugin_name:
                p.enabled = enabled
                # Rebuild hook chain
                self._hooks = {h: [] for h in HOOK_POINTS}
                for plugin in self._plugins:
                    if not plugin.enabled:
                        continue
                    for hook_name, fn in plugin.hooks.items():
                        self._hooks[hook_name].append((plugin.name, fn))
                return True
        return False

    def _write_example_plugin(self, path: Path):
        """Write an example plugin file for reference."""
        path.write_text('''\
"""Example SpeakType plugin — rename this file (remove the leading underscore) to activate.

Place .py files in ~/.speaktype/plugins/ to extend SpeakType.
Each plugin can define hook functions that are called at various points
in the dictation pipeline.

Available hooks:
    pre_transcribe(audio_path) -> audio_path
    post_transcribe(raw_text) -> text
    pre_polish(text, tone) -> (text, tone)
    post_polish(polished_text) -> text
    pre_insert(text) -> text or None (None skips insertion)
    post_insert(text) -> None
    on_recording_start() -> None
    on_recording_stop() -> None
"""

PLUGIN_NAME = "Example Plugin"
PLUGIN_VERSION = "1.0"
PLUGIN_DESCRIPTION = "An example plugin that logs each dictation."
PLUGIN_AUTHOR = "SpeakType"


def post_transcribe(text):
    """Called after ASR transcription. Return modified text."""
    # Example: log every transcription
    # import logging
    # logging.getLogger("speaktype.plugin.example").info(f"Transcribed: {text}")
    return text
''', encoding="utf-8")
