from app.config import Settings
from app import render_fullscreen


def test_fullscreen_gameplay_uses_entire_vertical_frame_without_webcam(monkeypatch):
    s = Settings(layout="osrs_focus", webcam_manual_enabled=False, webcam_region="auto")
    monkeypatch.setattr(render_fullscreen, "_webcam_crop", lambda *args, **kwargs: None)
    graph, region, mode, focus_points = render_fullscreen._full_game_filter(
        None, 0.0, {"event_type": "combat", "features_json": "{}"}, "C\\:/tmp/captions.ass", s, 22.0
    )
    assert mode == "gameplay_fullscreen"
    assert region == ""
    assert focus_points == 0
    assert "scale=1080:1920" in graph
    assert "gblur" not in graph
    assert "overlay=" not in graph
    assert "x='(iw-ow)/2'" in graph


def test_auto_uses_calibrated_postal_webcam_not_detector(monkeypatch):
    s = Settings(layout="osrs_focus", webcam_region="auto", webcam_manual_enabled=True)
    monkeypatch.setattr(render_fullscreen, "_source_size", lambda *args, **kwargs: (1280, 720))
    monkeypatch.setattr(
        render_fullscreen,
        "_webcam_crop",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("heuristic webcam detector must not run")),
    )
    graph, region, mode, focus_points = render_fullscreen._full_game_filter(
        None, 0.0, {"event_type": "combat", "features_json": "{}"}, "C\\:/tmp/captions.ass", s, 22.0
    )
    assert mode == "gameplay_fullscreen"
    assert region == "manual"
    assert focus_points == 0
    # 1280x720 normalized from the supplied OBS frame: x=.720, y=0, w=.280, h=.340
    assert "crop=358:245:922:0" in graph
    assert "overlay=345:54" in graph
    # The real camera is ~1.46:1, not 16:9. A 390px overlay should be ~267px tall.
    assert "scale=390:267" in graph


def test_manual_webcam_crop_scales_with_source_resolution(monkeypatch):
    s = Settings(layout="osrs_focus", webcam_region="manual", webcam_manual_enabled=True)
    monkeypatch.setattr(render_fullscreen, "_source_size", lambda *args, **kwargs: (1920, 1080))
    crop = render_fullscreen._manual_webcam_crop(None, s)
    assert crop is not None
    region, expr, aspect = crop
    assert region == "manual"
    assert expr == "crop=538:367:1382:0"
    assert 1.45 < aspect < 1.48


def test_explicit_webcam_region_puts_camera_top_center(monkeypatch):
    s = Settings(layout="osrs_focus", webcam_region="top_right")
    monkeypatch.setattr(render_fullscreen, "_webcam_crop", lambda *args, **kwargs: ("top_right", "crop=320:180:900:20"))
    monkeypatch.setattr(render_fullscreen, "_reaction_only_source", lambda *args, **kwargs: False)
    graph, region, mode, focus_points = render_fullscreen._full_game_filter(
        None, 0.0, {"event_type": "combat", "features_json": "{}"}, "C\\:/tmp/captions.ass", s, 22.0
    )
    assert mode == "gameplay_fullscreen"
    assert region == "top_right"
    assert focus_points == 0
    assert "scale=1080:1920" in graph
    assert "overlay=345:54" in graph
    assert "gblur" not in graph


def test_runelite_focus_points_drive_crop_expression(monkeypatch):
    s = Settings(layout="osrs_focus", webcam_manual_enabled=False, webcam_region="auto", dynamic_zoom_enabled=False)
    events=[
        {"time":2.0,"event_type":"bridge_focus","payload":{"focus_x_ratio":0.30,"focus_y_ratio":0.50}},
        {"time":8.0,"event_type":"big_hit","payload":{"focus_x_ratio":0.72,"focus_y_ratio":0.48}},
    ]
    graph, region, mode, focus_points = render_fullscreen._full_game_filter(
        None,0.0,{"event_type":"big_hit","features_json":"{}"},"C\\:/tmp/captions.ass",s,12.0,game_events=events
    )
    assert region == ""
    assert mode == "gameplay_fullscreen"
    assert focus_points == 2
    assert "iw*(" in graph
    assert "0.300000" in graph
    assert "0.720000" in graph
    assert "(iw-ow)/2" not in graph


def test_reward_and_chat_signals_never_frame_osrs_chat():
    assert render_fullscreen._shorts_focus_mode({"event_type": "drop", "features_json": "{}"}) == "center"
    assert render_fullscreen._shorts_focus_mode({"event_type": "chat", "features_json": "{}"}) == "center"
    assert render_fullscreen._shorts_focus_mode({"event_type": "speech", "features_json": '{"chat_change": 1.0}'}) == "center"


def test_gameplay_crop_happens_before_dynamic_zoom_and_stays_centered_without_tracking():
    s = Settings(layout="osrs_focus", dynamic_zoom_enabled=True)
    chain = render_fullscreen._gameplay_chain("center", 1080, 1920, 22.0, s)
    assert chain.index("crop=") < chain.index("zoompan")
    assert "x='(iw-ow)/2'" in chain
    assert "x='iw/2-(iw/zoom/2)'" in chain
    assert "y='ih/2-(ih/zoom/2)'" in chain
    assert "sin(on/65)" not in chain
    assert "cos(on/80)" not in chain
