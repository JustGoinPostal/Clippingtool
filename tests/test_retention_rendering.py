from app.config import Settings
from app import render_fullscreen


def test_real_runelite_event_drives_punch_in():
    s=Settings(layout="osrs_focus",webcam_manual_enabled=False,webcam_region="auto")
    events=[
        {"time":4.0,"event_type":"bridge_state","payload":{"player_x_ratio":0.50}},
        {"time":7.0,"event_type":"big_hit","strength":25,"payload":{"player_x_ratio":0.52,"amount":55}},
    ]
    graph,region,mode,focus_points,webcam_box=render_fullscreen._full_game_filter(
        None,0.0,{"event_type":"big_hit","features_json":"{}"},"C\\:/tmp/captions.ass",
        s,12.0,game_events=events,reaction_windows_list=[]
    )
    assert "zoompan" in graph
    assert "abs(on-210)" in graph
    assert focus_points==2


def test_no_exact_event_means_no_random_gameplay_zoom():
    s=Settings(layout="osrs_focus",webcam_manual_enabled=False,webcam_region="auto")
    events=[
        {"time":2.0,"event_type":"bridge_state","payload":{"player_x_ratio":0.50}},
        {"time":5.0,"event_type":"bridge_focus","payload":{"player_x_ratio":0.51}},
    ]
    graph,_,_,_,_=render_fullscreen._full_game_filter(
        None,0.0,{"event_type":"speech","features_json":"{}"},"C\\:/tmp/captions.ass",
        s,10.0,game_events=events,reaction_windows_list=[]
    )
    assert "zoompan" not in graph


def test_audio_reaction_temporarily_enlarges_manual_webcam(monkeypatch):
    s=Settings(layout="osrs_focus",webcam_region="auto",webcam_manual_enabled=True)
    monkeypatch.setattr(render_fullscreen,"_source_size",lambda *args,**kwargs:(1280,720))
    graph,region,_,_,box=render_fullscreen._full_game_filter(
        None,0.0,{"event_type":"reaction","features_json":"{}"},"C\\:/tmp/captions.ass",
        s,12.0,game_events=[],reaction_windows_list=[(2.0,3.3)],punch_times=[]
    )
    assert region=="manual"
    assert box["w"]==390
    assert "split=3" in graph
    assert "enable='between(t,2.000,3.300)'" in graph
    assert "scale=499:" in graph
