from app.osrs_events import normalize_event_type, event_strength, summarize_event


def test_legacy_nearby_player_death_is_not_assumed_pvp_kill():
    payload = {"actor_type": "player", "local_player": False, "name": "Nearby Player"}
    assert normalize_event_type("actor_death", payload) == "runelite_event"


def test_confirmed_player_death_can_normalize_to_pvp_kill():
    payload = {
        "actor_type": "player",
        "local_player": False,
        "attributed_to_local": True,
        "name": "Opponent",
    }
    assert normalize_event_type("actor_death", payload) == "pvp_kill"


def test_direct_pvp_kill_stays_pvp_kill():
    payload = {"attributed_to_local": True, "name": "Opponent", "last_confirmed_damage": 42}
    assert normalize_event_type("pvp_kill", payload) == "pvp_kill"
    assert "last hit 42" in summarize_event({"event_type": "pvp_kill", "payload": payload})


def test_incoming_big_hit_is_separate_from_outgoing_big_hit():
    incoming = {"amount": 55, "target_local": True, "attributed_to_local": False}
    outgoing = {"amount": 55, "target_local": False, "attributed_to_local": True}
    assert normalize_event_type("big_hit_taken", incoming) == "big_hit_taken"
    assert normalize_event_type("big_hit", outgoing) == "big_hit"
    assert event_strength({"event_type": "big_hit", "payload": outgoing, "confidence": 1.0}) > event_strength(
        {"event_type": "big_hit_taken", "payload": incoming, "confidence": 1.0}
    )
