from app.config import Settings
from app.interest_windows import build_interest_windows, window_coverage_seconds


def _contains(windows, t, source=None):
    for row in windows:
        if float(row["start"]) <= t <= float(row["end"]):
            if source is None or source in row.get("sources",[]):
                return True
    return False


def test_interest_windows_prioritize_runelite_and_keep_human_reactions():
    s=Settings(
        keywords={"no way":22.0},
        targeted_video_pre_seconds=10.0,
        targeted_video_post_seconds=16.0,
        targeted_video_audio_z=1.2,
        targeted_video_merge_gap_seconds=2.0,
        targeted_video_max_windows=20,
    )
    transcript={"segments":[
        {"start":295.0,"end":298.0,"text":"no way bro"},
        {"start":410.0,"end":412.0,"text":"normal sentence"},
    ]}
    energy=[(0.0,-52.0),(40.0,-51.0),(80.0,-50.0),(120.0,-53.0),(200.0,-12.0),(400.0,-52.0)]
    events=[
        {"time":100.0,"event_type":"pvp_kill","strength":44.0,"payload":{}},
        {"time":150.0,"event_type":"bridge_heartbeat","strength":0.0,"payload":{}},
    ]

    windows=build_interest_windows(transcript,energy,events,500.0,s)

    assert _contains(windows,100.0,"runelite")
    assert _contains(windows,200.0,"audio_reaction")
    assert _contains(windows,296.0,"speech_keyword")
    assert not any("bridge_heartbeat" in row.get("sources",[]) for row in windows)
    assert window_coverage_seconds(windows) < 500.0


def test_nearby_runelite_events_merge_into_one_dense_window():
    s=Settings(
        targeted_video_pre_seconds=12.0,
        targeted_video_post_seconds=20.0,
        targeted_video_merge_gap_seconds=4.0,
        targeted_video_max_windows=20,
    )
    events=[
        {"time":100.0,"event_type":"big_hit","strength":28.0,"payload":{"amount":50}},
        {"time":108.0,"event_type":"pvp_kill","strength":44.0,"payload":{}},
    ]

    windows=build_interest_windows({"segments":[]},[],events,600.0,s)

    assert len(windows)==1
    assert windows[0]["start"] <= 92.0
    assert windows[0]["end"] >= 128.0
    assert "big_hit" in windows[0]["sources"]
    assert "pvp_kill" in windows[0]["sources"]


def test_dense_combat_cannot_turn_into_one_unbounded_scan():
    s=Settings(
        targeted_video_pre_seconds=16.0,
        targeted_video_post_seconds=28.0,
        targeted_video_merge_gap_seconds=6.0,
        targeted_video_max_window_seconds=60.0,
        targeted_video_max_windows=20,
    )
    events=[
        {"time":float(t),"event_type":"pvp_kill","strength":44.0,"payload":{}}
        for t in range(100,221,20)
    ]

    windows=build_interest_windows({"segments":[]},[],events,600.0,s)

    assert windows
    assert all(float(row["end"])-float(row["start"]) <= 60.001 for row in windows)
    assert _contains(windows,100.0,"runelite")
    assert _contains(windows,220.0,"runelite")
