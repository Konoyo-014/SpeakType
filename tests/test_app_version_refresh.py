"""Tests for version-triggered permission refresh during startup."""

from speaktype import app


def test_existing_bundle_config_without_version_marker_triggers_refresh(monkeypatch, tmp_path):
    config = {"last_seen_version": ""}
    saved = []
    refreshed = []
    config_file = tmp_path / "config.json"
    config_file.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(app, "CONFIG_FILE", config_file)
    monkeypatch.setattr(app, "get_running_bundle_path", lambda: "/Applications/SpeakType.app")
    monkeypatch.setattr(app, "save_config", lambda value: saved.append(dict(value)))
    monkeypatch.setattr(app, "refresh_permissions_for_update", lambda bundle_id: refreshed.append(bundle_id))

    app._refresh_permissions_after_version_update(config)

    assert config["last_seen_version"] == app.__version__
    assert saved == [{"last_seen_version": app.__version__}]
    assert refreshed == [app.BUNDLE_IDENTIFIER]


def test_fresh_install_records_version_without_permission_refresh(monkeypatch, tmp_path):
    config = {"last_seen_version": ""}
    saved = []
    refreshed = []
    config_file = tmp_path / "config.json"

    monkeypatch.setattr(app, "CONFIG_FILE", config_file)
    monkeypatch.setattr(app, "get_running_bundle_path", lambda: "/Applications/SpeakType.app")
    monkeypatch.setattr(app, "save_config", lambda value: saved.append(dict(value)))
    monkeypatch.setattr(app, "refresh_permissions_for_update", lambda bundle_id: refreshed.append(bundle_id))

    app._refresh_permissions_after_version_update(config)

    assert config["last_seen_version"] == app.__version__
    assert saved == [{"last_seen_version": app.__version__}]
    assert refreshed == []


def test_bundled_version_change_saves_and_refreshes(monkeypatch, tmp_path):
    config = {"last_seen_version": "2.0.0"}
    saved = []
    refreshed = []
    config_file = tmp_path / "config.json"
    config_file.write_text('{"last_seen_version":"2.0.0"}', encoding="utf-8")

    monkeypatch.setattr(app, "CONFIG_FILE", config_file)
    monkeypatch.setattr(app, "get_running_bundle_path", lambda: "/Applications/SpeakType.app")
    monkeypatch.setattr(app, "save_config", lambda value: saved.append(dict(value)))
    monkeypatch.setattr(app, "refresh_permissions_for_update", lambda bundle_id: refreshed.append(bundle_id))

    app._refresh_permissions_after_version_update(config)

    assert config["last_seen_version"] == app.__version__
    assert saved == [{"last_seen_version": app.__version__}]
    assert refreshed == [app.BUNDLE_IDENTIFIER]


def test_source_version_change_skips_permission_reset(monkeypatch, tmp_path):
    config = {"last_seen_version": "2.0.0"}
    saved = []
    refreshed = []
    config_file = tmp_path / "config.json"
    config_file.write_text('{"last_seen_version":"2.0.0"}', encoding="utf-8")

    monkeypatch.setattr(app, "CONFIG_FILE", config_file)
    monkeypatch.setattr(app, "get_running_bundle_path", lambda: "")
    monkeypatch.setattr(app, "save_config", lambda value: saved.append(dict(value)))
    monkeypatch.setattr(app, "refresh_permissions_for_update", lambda bundle_id: refreshed.append(bundle_id))

    app._refresh_permissions_after_version_update(config)

    assert config["last_seen_version"] == app.__version__
    assert saved == [{"last_seen_version": app.__version__}]
    assert refreshed == []
