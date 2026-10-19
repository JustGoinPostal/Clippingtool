from __future__ import annotations

import json
from pathlib import Path

from app import config
from app.paths import APP_HOME, RESOURCE_ROOT, _legacy_config_payload


def test_runtime_root_is_creator_home_and_resources_are_mirrored():
    assert config.ROOT == APP_HOME
    assert config.CONFIG_PATH.parent == APP_HOME
    assert (APP_HOME / "app" / "static" / "index.html").exists()
    assert (APP_HOME / "config.example.json").exists()


def test_relative_media_paths_resolve_inside_creator_home():
    settings = config.Settings()
    assert settings.path("data/input") == APP_HOME / "data" / "input"
    assert settings.path("data/output") == APP_HOME / "data" / "output"
    assert settings.path("data/cache") == APP_HOME / "data" / "cache"


def test_new_install_uses_a_random_runelite_bridge_token():
    config.CONFIG_PATH.unlink(missing_ok=True)
    settings = config.load_settings()
    assert settings.runelite_bridge_token
    assert settings.runelite_bridge_token != "postal-local"
    assert len(settings.runelite_bridge_token) >= 24


def test_legacy_config_keeps_media_paths_but_moves_cache(tmp_path: Path):
    old = tmp_path / "old"
    (old / "data" / "input").mkdir(parents=True)
    (old / "data" / "output").mkdir(parents=True)
    (old / "config.json").write_text(json.dumps({
        "watch_folder": "data/input",
        "output_folder": "data/output",
        "cache_folder": "data/cache",
    }), encoding="utf-8")
    payload = _legacy_config_payload(old)
    assert payload is not None
    assert Path(payload["watch_folder"]).is_absolute()
    assert Path(payload["output_folder"]).is_absolute()
    assert payload["cache_folder"] == "data/cache"


def test_resource_root_is_separate_from_app_home_in_packaged_design():
    # Tests may intentionally point APP_HOME at a repo-local .pytest-home, but the
    # resource tree and persistent creator root must still be distinct paths.
    assert RESOURCE_ROOT.resolve() != APP_HOME.resolve()
