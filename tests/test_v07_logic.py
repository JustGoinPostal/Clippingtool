from datetime import datetime

from app.covers import select_cover_ms
from app.distribution import similarity, _local_slots
from app.config import Settings


def test_cover_selection_is_event_aware():
    render={"render_start":0.0,"render_end":40.0}
    reward=select_cover_ms({"event_type":"raid_reward"},render)
    reaction=select_cover_ms({"event_type":"reaction"},render)
    combat=select_cover_ms({"event_type":"pvp_kill"},render)
    assert 0 < reaction < combat < reward < 40000


def test_similarity_catches_repetitive_clip_text():
    a="twisted bow purple no way chambers of xeric huge drop"
    b="no way huge twisted bow purple drop from chambers of xeric"
    c="vengeance pvp smite loot key wilderness"
    assert similarity(a,b) > 0.70
    assert similarity(a,c) < 0.25


def test_local_slots_are_sorted_and_future():
    start=datetime.now().astimezone().replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
    slots=_local_slots(start,2,["12:00","18:30"])
    assert len(slots)==4
    assert slots==sorted(slots)
    assert slots[0]>=start


def test_v07_settings_defaults():
    s=Settings()
    assert s.instagram_graph_version=="v26.0"
    assert s.youtube_set_thumbnail is True
    assert s.distribution_slots
    assert 0 < s.duplicate_similarity_threshold < 1
