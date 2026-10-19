from app.config import Settings
from app.hooks import generate_hook
from app.metadata import make_metadata
from app.osrs_events import event_strength, normalize_event_type
from app.osrs_story import build_story_events
from app.osrs_story_apply import apply_story_intelligence


def test_close_pvp_escape_requires_low_hp_movement_disengage_and_survival():
    events=[
        {"time":9.0,"event_type":"bridge_state","payload":{"hp":70,"hp_max":99,"hp_ratio":0.70,"recent_pvp":True,"recent_pvp_opponent":"PKer","target_type":"player","world_x":100,"world_y":100}},
        {"time":10.0,"event_type":"big_hit_taken","payload":{"amount":61,"opponent_type":"player","opponent_name":"PKer"}},
        {"time":11.0,"event_type":"bridge_state","payload":{"hp":28,"hp_max":99,"hp_ratio":0.28,"recent_pvp":True,"recent_pvp_opponent":"PKer","target_type":"player","world_x":101,"world_y":100}},
        {"time":15.0,"event_type":"bridge_state","payload":{"hp":7,"hp_max":99,"hp_ratio":0.071,"recent_pvp":True,"recent_pvp_opponent":"PKer","target_type":"player","world_x":106,"world_y":101}},
        {"time":20.0,"event_type":"bridge_state","payload":{"hp":12,"hp_max":99,"hp_ratio":0.12,"recent_pvp":True,"recent_pvp_opponent":"PKer","world_x":111,"world_y":102}},
        {"time":23.0,"event_type":"bridge_state","payload":{"hp":20,"hp_max":99,"hp_ratio":0.20,"recent_pvp":True,"recent_pvp_opponent":"PKer","world_x":114,"world_y":102}},
    ]
    stories=build_story_events(events)
    escapes=[x for x in stories if x["event_type"]=="pvp_escape"]
    assert len(escapes)==1
    escape=escapes[0]
    assert escape["payload"]["moment_archetype"]=="pvp_escape"
    assert escape["payload"]["lowest_hp"]==7
    assert escape["payload"]["tiles_moved"] >= 12
    assert escape["payload"]["inferred"] is True
    assert escape["confidence"] < 1.0


def test_escape_is_not_created_if_the_player_dies():
    events=[
        {"time":10.0,"event_type":"big_hit_taken","payload":{"amount":61,"opponent_type":"player","opponent_name":"PKer"}},
        {"time":11.0,"event_type":"bridge_state","payload":{"hp":20,"hp_max":99,"hp_ratio":0.20,"recent_pvp":True,"target_type":"player","world_x":100,"world_y":100}},
        {"time":14.0,"event_type":"bridge_state","payload":{"hp":5,"hp_max":99,"hp_ratio":0.05,"recent_pvp":True,"world_x":108,"world_y":100}},
        {"time":17.0,"event_type":"bridge_state","payload":{"hp":2,"hp_max":99,"hp_ratio":0.02,"recent_pvp":True,"world_x":112,"world_y":100}},
        {"time":18.0,"event_type":"player_death","payload":{"local_player":True,"actor_type":"player"}},
    ]
    assert not any(x["event_type"]=="pvp_escape" for x in build_story_events(events))


def test_smite_is_promoted_only_when_exact_pk_and_local_transcript_agree():
    s=Settings(max_candidates=10)
    candidates=[{"start":90.0,"end":120.0,"score":80.0,"base_score":80.0,"reason":"pvp","transcript":"",
                 "event_type":"pvp","features":{}}]
    events=[
        {"time":100.0,"event_type":"big_hit","payload":{"name":"Target","amount":64}},
        {"time":104.0,"event_type":"pvp_kill","payload":{"name":"Target"},"confidence":1.25},
        {"time":106.0,"event_type":"player_loot","payload":{"source":"Target","total_value":42_000_000}},
    ]
    transcript={"segments":[
        {"start":96.0,"end":101.0,"text":"he is out of prayer"},
        {"start":102.0,"end":108.0,"text":"no way I smited him for the plus one"},
    ]}
    out=apply_story_intelligence(candidates,events,transcript,180.0,s)
    best=out[0]
    assert best["event_type"]=="pvp_kill"
    assert best["story_archetype"]=="pvp_smite"
    assert best["event_context"]["smite_signal_source"]=="local_transcript"
    assert best["features"]["smite_signal"]==1.0
    assert "SMITED" in generate_hook(best)
    title,_,tags=make_metadata(best)
    assert "Smited" in title
    assert "#PKing" in tags


def test_pet_message_is_high_priority_reward_story():
    events=[
        {"time":40.0,"event_type":"loot","payload":{"source":"Vorkath","total_value":120_000}},
        {"time":41.0,"event_type":"pet_drop","confidence":1.35,"payload":{"message":"You have a funny feeling like you're being followed"}},
    ]
    stories=build_story_events(events)
    assert len(stories)==1
    assert stories[0]["event_type"]=="pet_drop"
    assert stories[0]["payload"]["moment_archetype"]=="pet_reveal"
    assert event_strength(stories[0]) > 50


def test_99_milestone_and_combat_achievement_rank_above_generic_events():
    level={"event_type":"skill_milestone","payload":{"message":"You've just advanced your Strength level! You are now level 99."}}
    task={"event_type":"combat_achievement","payload":{"message":"Combat Task Completed: Perfect Verzik (Master)"}}
    generic={"event_type":"runelite_event","payload":{"message":"ordinary game message"}}
    assert normalize_event_type("skill_milestone",level["payload"])=="skill_milestone"
    assert event_strength(level) > event_strength(generic)
    assert event_strength(task) > event_strength(generic)
