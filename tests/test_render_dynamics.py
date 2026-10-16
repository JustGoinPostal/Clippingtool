from app.config import Settings
from app.render import _corner_box, _focus_chain


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
