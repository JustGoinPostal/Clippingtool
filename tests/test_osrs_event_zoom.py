from app.config import Settings
from app.framing import focus_y_ratio_expression, zoompan_y_expression
from app.render_fullscreen import _gameplay_chain


def test_vertical_focus_expression_tracks_y_axis():
    rows=[
        {"time":1.0,"x":0.50,"y":0.25,"exact":0.0},
        {"time":5.0,"x":0.50,"y":0.75,"exact":1.0},
    ]
    expr=focus_y_ratio_expression(rows)
    assert "0.250000" in expr
    assert "0.750000" in expr
    zoom_expr=zoompan_y_expression(rows,30.0)
    assert "on/30.000000" in zoom_expr
    assert "ih-ih/zoom" in zoom_expr


def test_exact_runelite_event_replaces_generic_periodic_zoom_pulses():
    s=Settings(dynamic_zoom_enabled=True)
    rows=[
        {"time":2.0,"x":0.45,"y":0.55,"exact":0.0},
        {"time":11.0,"x":0.62,"y":0.40,"exact":1.0},
    ]
    chain=_gameplay_chain("combat",1080,1920,20.0,s,focus_keyframes=rows)
    assert "between(on" in chain
    assert "mod(on" not in chain
    assert "on/30.000000" in chain


def test_no_exact_event_keeps_subtle_fallback_motion():
    s=Settings(dynamic_zoom_enabled=True)
    rows=[
        {"time":2.0,"x":0.45,"y":0.55,"exact":0.0},
        {"time":8.0,"x":0.52,"y":0.50,"exact":0.0},
    ]
    chain=_gameplay_chain("center",1080,1920,20.0,s,focus_keyframes=rows)
    assert "mod(on" in chain
