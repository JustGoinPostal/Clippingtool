from app.config import Settings
from app.hooks import generate_hook
from app.quality import evaluate_render
from app.render import _focus_chain


def test_osrs_hooks_are_event_aware():
    assert "TWISTED BOW" in generate_hook({
        "event_type":"raid_reward",
        "title":"Twisted bow reward",
        "transcript":"no way bro twisted bow",
    })
    assert "SPEC" in generate_hook({"event_type":"big_hit","transcript":"that was huge"})
    assert "EXPECT" in generate_hook({"event_type":"pvp","transcript":"he is dead"})


def test_quality_score_is_bounded_and_has_breakdown():
    words=[
        {"start":10.0,"end":10.35,"word":"no"},
        {"start":10.4,"end":10.8,"word":"way"},
        {"start":11.0,"end":11.4,"word":"bro"},
        {"start":12.0,"end":12.5,"word":"purple"},
    ]
    result={"start":8.0,"end":30.0,"focus":"chat"}
    q=evaluate_render({"event_type":"raid_reward","score":94},words,result,"TWISTED BOW. NO WAY.")
    assert 0 <= q["score"] <= 100
    assert q["payoff"] >= 90
    assert q["hook"] >= 80
    assert "pacing" in q and "context" in q and "dead_air" in q


def test_dynamic_zoom_chain_can_be_disabled():
    s=Settings()
    s.dynamic_zoom_enabled=True
    chain=_focus_chain("combat",980,700,22.0,s)
    assert "zoompan" in chain
    s.dynamic_zoom_enabled=False
    chain=_focus_chain("combat",980,700,22.0,s)
    assert "zoompan" not in chain
