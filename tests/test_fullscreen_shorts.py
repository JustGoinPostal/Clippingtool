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
    assert "x='(iw-ow)/2'" in graph


def test_auto_webcam_never_overlays_guessed_runelite_ui(monkeypatch):
    s = Settings(layout="osrs_focus", webcam_region="auto")
    monkeypatch.setattr(
        render_fullscreen,
        "_webcam_crop",
        lambda *args, **kwargs: ("bottom_left", "crop=320:180:10:500"),
    )
    graph, region, mode = render_fullscreen._full_game_filter(
        None, 0.0, {"event_type": "combat", "features_json": "{}"}, "C\\:/tmp/captions.ass", s, 22.0
    )
    assert mode == "gameplay_fullscreen"
    assert region == ""
    assert "overlay=" not in graph
    assert "crop=320:180:10:500" not in graph


def test_explicit_webcam_region_puts_camera_top_center(monkeypatch):
    s = Settings(layout="osrs_focus", webcam_region="top_right")
    monkeypatch.setattr(render_fullscreen, "_webcam_crop", lambda *args, **kwargs: ("top_right", "crop=320:180:900:20"))
    monkeypatch.setattr(render_fullscreen, "_reaction_only_source", lambda *args, **kwargs: False)
    graph, region, mode = render_fullscreen._full_game_filter(
        None, 0.0, {"event_type": "combat", "features_json": "{}"}, "C\\:/tmp/captions.ass", s, 22.0
    )
    assert mode == "gameplay_fullscreen"
    assert region == "top_right"
    assert "scale=1080:1920" in graph
    assert "overlay=345:54" in graph
    assert "gblur" not in graph


def test_reward_and_chat_signals_never_frame_osrs_chat():
    assert render_fullscreen._shorts_focus_mode({"event_type": "drop", "features_json": "{}"}) == "center"
    assert render_fullscreen._shorts_focus_mode({"event_type": "chat", "features_json": "{}"}) == "center"
    assert render_fullscreen._shorts_focus_mode({"event_type": "speech", "features_json": '{"chat_change": 1.0}'}) == "center"


def test_gameplay_crop_happens_before_dynamic_zoom_and_stays_centered():
    s = Settings(layout="osrs_focus", dynamic_zoom_enabled=True)
    chain = render_fullscreen._gameplay_chain("center", 1080, 1920, 22.0, s)
    assert chain.index("crop=") < chain.index("zoompan")
    assert "x='(iw-ow)/2'" in chain
    assert "x='iw/2-(iw/zoom/2)'" in chain
    assert "y='ih/2-(ih/zoom/2)'" in chain
    assert "sin(on/65)" not in chain
    assert "cos(on/80)" not in chain
