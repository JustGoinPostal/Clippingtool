from app.config import Settings
from app.osrs_context import context_from_text, enrich_encounter_context
from app.osrs_story_apply import apply_story_intelligence


def test_maps_major_raid_encounters():
    assert context_from_text("Great Olm")["activity_key"]=="cox"
    assert context_from_text("Verzik Vitur")["activity_key"]=="tob"
    assert context_from_text("Akkha")["activity_key"]=="toa"
    assert context_from_text("TzKal-Zuk")["activity_key"]=="inferno"
    assert context_from_text("Sol Heredit")["activity_key"]=="colosseum"


def test_target_context_carries_to_nearby_exact_event():
    rows=enrich_encounter_context([
        {"time":100.0,"event_type":"bridge_state","payload":{"target_name":"Verzik Vitur","target_type":"npc"}},
        {"time":104.0,"event_type":"big_hit","payload":{"amount":72,"attributed_to_local":True}},
    ])
    hit=rows[1]
    assert hit["payload"]["activity_key"]=="tob"
    assert hit["payload"]["activity"]=="Theatre of Blood"
    assert hit["payload"]["encounter"]=="Verzik Vitur"


def test_explicit_reward_context_overrides_old_target_context():
    rows=enrich_encounter_context([
        {"time":10.0,"event_type":"bridge_state","payload":{"target_name":"Verzik Vitur"}},
        {"time":20.0,"event_type":"loot","payload":{"source":"Chambers of Xeric","total_value":1000000}},
    ])
    reward=rows[1]
    assert reward["payload"]["activity_key"]=="cox"
    assert reward["payload"]["activity"]=="Chambers of Xeric"


def test_story_clip_persists_encounter_context():
    s=Settings(max_candidates=10)
    candidates=[{"start":90.0,"end":125.0,"score":74.0,"base_score":74.0,"reason":"combat","transcript":"","event_type":"gameplay","features":{}}]
    events=[
        {"time":98.0,"event_type":"bridge_state","payload":{"target_name":"Great Olm","target_type":"npc"}},
        {"time":104.0,"event_type":"big_hit","payload":{"name":"Great Olm","amount":60,"attributed_to_local":True}},
        {"time":108.0,"event_type":"boss_kill","payload":{"name":"Great Olm","actor_type":"npc","attributed_to_local":True},"confidence":1.2},
    ]
    out=apply_story_intelligence(candidates,events,{"segments":[{"start":100,"end":112,"text":"Olm is dead let's go"}]},180.0,s)
    boss=next(x for x in out if x["event_type"]=="boss_kill")
    assert boss["event_context"]["activity_key"]=="cox"
    assert boss["event_context"]["activity"]=="Chambers of Xeric"
    assert boss["event_context"]["encounter"]=="Great Olm"
    assert boss["features"]["encounter_context"]==1.0
    assert "Great Olm" in boss["reason"]
