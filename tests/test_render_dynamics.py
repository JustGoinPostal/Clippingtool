import numpy as np
from app.config import Settings
from app import render
from app.render import _corner_box, _focus_chain, _focus_crop, _pick_webcam_region


def test_short_defaults_are_vertical_1080p():
    s = Settings()
    assert s.render_width == 1080
    assert s.render_height == 1920
    assert s.render_height / s.render_width == 16 / 9


def test_webcam_corner_boxes_stay_inside_source():
    for region in ("top_left", "top_right", "bottom_left", "bottom_right"):
        x, y, w, h = _corner_box(region, 1920, 1080, 0.30)
        assert x >= 0 and y >= 0
        assert w > 0 and h > 0
        assert x + w <= 1920
        assert y + h <= 1080


def test_dynamic_focus_chain_has_repeating_beats_and_payoff():
    s = Settings()
    chain = _focus_chain("combat", 980, 700, 38.0, s)
    assert "zoompan" in chain
    assert "mod(on" in chain
    assert "between(on" in chain
    assert "sin(on/55)" in chain


def test_black_scene_with_facecam_switches_to_reaction(monkeypatch):
    s = Settings(webcam_region="top_right")
    frame = np.zeros((180, 320, 3), dtype=np.uint8)
    x, y, w, h = _corner_box("top_right", 320, 180, s.webcam_crop_width_ratio)
    frame[y:y+h, x:x+w] = 145
    monkeypatch.setattr(render, "_sample_frames", lambda *args, **kwargs: [frame.copy(), frame.copy()])
    assert render._reaction_only_source(None, 0.0, s, "top_right") is True


def test_normal_gameplay_scene_does_not_switch_to_reaction(monkeypatch):
    s = Settings(webcam_region="top_right")
    frame = np.full((180, 320, 3), 90, dtype=np.uint8)
    monkeypatch.setattr(render, "_sample_frames", lambda *args, **kwargs: [frame.copy(), frame.copy()])
    assert render._reaction_only_source(None, 0.0, s, "top_right") is False


def test_ambiguous_webcam_scores_are_rejected():
    scores={"top_left":0.10,"top_right":0.11,"bottom_left":0.09,"bottom_right":0.08}
    assert _pick_webcam_region(scores) is None


def test_clear_webcam_score_is_selected():
    scores={"top_left":0.18,"top_right":0.52,"bottom_left":0.07,"bottom_right":0.03}
    assert _pick_webcam_region(scores) == "top_right"


def test_center_crop_avoids_outer_left_overlay_area():
    crop=_focus_crop("center")
    assert "iw*0.12" in crop
    assert "iw*0.76" in crop
