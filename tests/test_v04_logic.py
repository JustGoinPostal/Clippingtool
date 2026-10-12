from app.config import Settings
from app.render import focus_mode, variant_window, tighten_dead_air


def test_focus_modes():
    assert focus_mode({"event_type":"pvp_kill","features_json":"{}"}) == "combat"
    assert focus_mode({"event_type":"player_death","features_json":"{}"}) == "combat"
    assert focus_mode({"event_type":"raid_reward","features_json":"{}"}) == "chat"
    assert focus_mode({"event_type":"rare_drop","features_json":"{}"}) == "chat"
    assert focus_mode({"event_type":"speech","features_json":"{\"ui_change\":0.8}"}) == "ui"


def test_variant_window():
    s=Settings()
    a,b=variant_window({"start":10,"end":80},"short",s)
    assert round(b-a,2) == 22.0
    assert 10 <= a < b <= 80


def test_dead_air_is_conservative():
    s=Settings()
    words=[{"start":20.0,"end":20.5,"word":"hello"},{"start":25.0,"end":25.5,"word":"world"}]
    a,b=tighten_dead_air(words,10,40,{"event_type":"reaction"},s)
    assert a > 10 and b < 40
    assert tighten_dead_air(words,10,40,{"event_type":"pvp_kill"},s) == (10,40)
