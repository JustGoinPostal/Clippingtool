from app.hooks import generate_hook
from app.metadata import make_metadata


def test_high_value_pk_hook_and_title_use_exact_context():
    clip = {
        "event_type": "pvp_kill",
        "story_archetype": "high_value_pk",
        "event_context": {
            "moment_archetype": "high_value_pk",
            "name": "TargetName",
            "loot_value": 52_000_000,
            "biggest_setup_hit": 72,
        },
        "transcript": "sit no way bro",
    }
    assert generate_hook(clip) == "52M ON THE FLOOR"
    title, _, tags = make_metadata(clip)
    assert title == "52M PK on TargetName"
    assert "#OSRSPvP" in tags


def test_reward_reveal_prefers_item_name():
    clip = {
        "event_type": "collection_log",
        "story_archetype": "reward_reveal",
        "event_context": {
            "moment_archetype": "reward_reveal",
            "source": "Chambers of Xeric",
            "items": [{"name": "Twisted bow", "quantity": 1}],
        },
        "transcript": "no way no way",
    }
    assert generate_hook(clip) == "TWISTED BOW. NO WAY."
    title, _, tags = make_metadata(clip)
    assert title == "Twisted bow From Chambers of Xeric"
    assert "#OSRSDrops" in tags
