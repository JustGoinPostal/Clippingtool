from app.config import Settings
from app import render_fullscreen


def test_fullscreen_gameplay_uses_entire_vertical_frame(monkeypatch):
    s = Settings(layout="osrs_focus")
    monkeypatch.setattr(render_fullscreen, "_webcam_crop", lambda *args, **kwargs: None)
    graph, region, mode = render_fullscreen._full_game_filter(
        None, 0.0, {"event_type": "combat", "features_json": "{}"}, "C\\:/tmp/captions.ass", s, 22.0
    )
    assert mode == "gameplay_fullscreen"
    assert region == ""
    assert "scale=1080:1920" in graph
    assert "gblur" not in graph
    assert "overlay=" not in graph


def test_fullscreen_gameplay_only_adds_webcam_as_overlay(monkeypatch):
    s = Settings(layout="osrs_focus")
    monkeypatch.setattr(render_fullscreen, "_webcam_crop", lambda *args, **kwargs: ("top_right", "crop=320:180:900:20"))
    monkeypatch.setattr(render_fullscreen, "_reaction_only_source", lambda *args, **kwargs: False)
    graph, region, mode = render_fullscreen._full_game_filter(
        None, 0.0, {"event_type": "combat", "features_json": "{}"}, "C\\:/tmp/captions.ass", s, 22.0
    )
    assert mode == "gameplay_fullscreen"
    assert region == "top_right"
    assert "scale=1080:1920" in graph
    assert "overlay=" in graph
    assert "gblur" not in graph
