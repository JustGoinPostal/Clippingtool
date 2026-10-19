from app.framing import build_focus_keyframes, crop_x_expression, focus_ratio_expression


def test_focus_keyframes_keep_bridge_motion_and_exact_anchor():
    events=[
        {"time":101.0,"event_type":"bridge_focus","payload":{"focus_x_ratio":0.31,"focus_y_ratio":0.52}},
        {"time":103.0,"event_type":"bridge_focus","payload":{"focus_x_ratio":0.36,"focus_y_ratio":0.51}},
        {"time":105.0,"event_type":"big_hit","payload":{"focus_x_ratio":0.73,"focus_y_ratio":0.47}},
    ]
    rows=build_focus_keyframes(events,100.0,110.0)
    assert len(rows)==3
    assert rows[0]["time"]==1.0
    assert rows[-1]["time"]==5.0
    assert rows[-1]["x"]==0.73
    assert rows[-1]["exact"]==1.0


def test_exact_event_wins_when_periodic_sample_is_same_moment():
    events=[
        {"time":105.0,"event_type":"bridge_focus","payload":{"focus_x_ratio":0.20}},
        {"time":105.05,"event_type":"pvp_kill","payload":{"focus_x_ratio":0.80}},
    ]
    rows=build_focus_keyframes(events,100.0,110.0)
    assert len(rows)==1
    assert rows[0]["x"]==0.80
    assert rows[0]["exact"]==1.0


def test_missing_focus_data_is_ignored():
    rows=build_focus_keyframes([
        {"time":4.0,"event_type":"bridge_heartbeat","payload":{}},
        {"time":5.0,"event_type":"big_hit","payload":{"amount":70}},
    ],0.0,10.0)
    assert rows==[]
    assert focus_ratio_expression(rows)=="0.5"
    assert crop_x_expression(rows)=="max(0,min(iw-ow,iw*(0.5)-ow/2))"


def test_crop_expression_interpolates_and_clamps():
    rows=[
        {"time":1.0,"x":0.25,"y":0.5,"exact":0.0},
        {"time":5.0,"x":0.75,"y":0.5,"exact":1.0},
    ]
    expr=crop_x_expression(rows)
    assert "0.250000" in expr
    assert "0.500000" in expr
    assert "0.750000" in expr
    assert "max(0,min(iw-ow" in expr
