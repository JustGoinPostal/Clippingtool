from app.retention_edit import enable_expression, event_punch_times, reaction_windows


def test_event_punches_only_use_real_high_value_events():
    events=[
        {"time":2.0,"event_type":"bridge_state","strength":99},
        {"time":4.0,"event_type":"big_hit","strength":20,"payload":{"amount":62}},
        {"time":4.4,"event_type":"big_hit","strength":18,"payload":{"amount":55}},
        {"time":8.0,"event_type":"pvp_kill","strength":35},
        {"time":12.0,"event_type":"bridge_focus","strength":99},
    ]
    times=event_punch_times(events,0.0,10.0,max_events=6)
    assert 4.0 in times
    assert 8.0 in times
    assert 2.0 not in times
    assert 4.4 not in times
    assert 12.0 not in times


def test_reaction_windows_find_audio_spikes_and_merge_close_peaks():
    energy=[
        [0.0,-34.0],[2.0,-35.0],[4.0,-36.0],[6.0,-12.0],
        [8.0,-34.0],[10.0,-35.0],[12.0,-11.0],[14.0,-36.0],
    ]
    windows=reaction_windows(energy,0.0,15.0,z_threshold=1.1,hold_seconds=1.2,max_events=3)
    assert len(windows)>=1
    assert all(0.0 <= a < b <= 15.0 for a,b in windows)
    expr=enable_expression(windows)
    assert "between(t," in expr


def test_no_reaction_windows_for_flat_audio():
    energy=[[float(i),-30.0] for i in range(10)]
    assert reaction_windows(energy,0.0,9.0,z_threshold=1.2)==[]
    assert enable_expression([])=="0"
