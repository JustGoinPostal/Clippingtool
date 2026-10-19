from app.config import Settings
from app.osrs_story import build_story_events, story_window
from app.osrs_story_apply import apply_story_intelligence


def test_pvp_finish_combines_spec_kill_and_loot():
    events = [
        {"time": 100.0, "event_type": "big_hit", "confidence": 1.0, "payload": {"name": "Target", "amount": 72}},
        {"time": 106.0, "event_type": "pvp_kill", "confidence": 1.25, "payload": {"name": "Target", "last_confirmed_damage": 31}},
        {"time": 108.0, "event_type": "player_loot", "confidence": 1.0, "payload": {"source": "Target", "total_value": 50_000_000}},
    ]
    stories = build_story_events(events)
    kills = [x for x in stories if x["event_type"] == "pvp_kill"]
    assert len(kills) == 1
    kill = kills[0]
    assert kill["payload"]["moment_archetype"] == "high_value_pk"
    assert kill["payload"]["biggest_setup_hit"] == 72
    assert kill["payload"]["loot_value"] == 50_000_000
    assert kill["payload"]["story_start"] <= 98.0
    assert kill["payload"]["story_end"] >= 112.0
    assert not any(x["event_type"] in {"big_hit", "player_loot"} for x in stories)


def test_reward_signals_collapse_into_one_reveal():
    events = [
        {"time": 40.0, "event_type": "loot", "payload": {"source": "Chambers of Xeric", "total_value": 150_000_000}},
        {"time": 41.5, "event_type": "collection_log", "payload": {"message": "New item added to your collection log"}},
        {"time": 42.0, "event_type": "rare_drop", "payload": {"name": "Twisted bow", "rare": True}},
    ]
    stories = build_story_events(events)
    reward = [x for x in stories if x["event_type"] in {"collection_log", "rare_drop", "raid_reward"}]
    assert len(reward) == 1
    assert reward[0]["payload"]["moment_archetype"] == "reward_reveal"
    assert set(reward[0]["payload"]["source_event_types"]) >= {"collection_log", "rare_drop"}


def test_pvp_story_window_is_short_form_shaped():
    s = Settings()
    event = {
        "time": 100.0,
        "event_type": "pvp_kill",
        "payload": {"story_start": 91.0, "story_end": 113.0, "moment_archetype": "pvp_finish"},
    }
    segments = [
        {"start": 90.0, "end": 94.0, "text": "he is actually running"},
        {"start": 104.0, "end": 109.0, "text": "there it is"},
        {"start": 110.0, "end": 114.0, "text": "no way bro"},
    ]
    start, end = story_window(segments, event, 200.0, s)
    assert 18.0 <= end - start <= 34.0
    assert start <= 100.0 <= end
    assert end >= 113.0


def test_story_pass_promotes_exact_osrs_context_without_losing_clip():
    s = Settings(max_candidates=10)
    candidates = [{
        "start": 90.0,
        "end": 120.0,
        "score": 70.0,
        "base_score": 70.0,
        "personal_score": 0.0,
        "reason": "audio reaction",
        "transcript": "he is running no way sit",
        "event_type": "pvp",
        "features": {"audio": 0.8},
    }]
    events = [
        {"time": 99.0, "event_type": "big_hit", "payload": {"name": "Target", "amount": 66}},
        {"time": 104.0, "event_type": "pvp_kill", "payload": {"name": "Target"}, "confidence": 1.25},
        {"time": 106.0, "event_type": "player_loot", "payload": {"source": "Target", "total_value": 30_000_000}},
    ]
    transcript = {"segments": [
        {"start": 94.0, "end": 100.0, "text": "he is running"},
        {"start": 101.0, "end": 108.0, "text": "no way sit"},
        {"start": 109.0, "end": 113.0, "text": "thirty mil"},
    ]}
    out = apply_story_intelligence(candidates, events, transcript, 180.0, s)
    assert out
    best = out[0]
    assert best["event_type"] == "pvp_kill"
    assert best["story_archetype"] == "high_value_pk"
    assert best["features"]["osrs_story"] == 1.0
    assert best["features"]["high_value"] == 1.0
    assert 18.0 <= best["end"] - best["start"] <= 34.0
