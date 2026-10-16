from app.config import Settings
from app.scoring import make_candidates


def test_multi_signal_burst_becomes_candidate():
    s = Settings(max_candidates=8, smart_boundaries=False)
    transcript = {"segments": [
        {"start": 5.0, "end": 8.0, "text": "normal gameplay"},
        {"start": 65.0, "end": 68.0, "text": "still playing"},
    ]}
    energy = [(0.0, -48.0), (20.0, -47.0), (40.0, -8.0), (60.0, -49.0), (79.0, -48.0)]
    base = {"visual_change": 0.01, "chat_change": 0.01, "ui_change": 0.01,
            "center_change": 0.01, "purple_ratio": 0.001, "gold_ratio": 0.001, "red_ratio": 0.001}
    video = [
        {"time": 0.0, **base},
        {"time": 20.0, **base},
        {"time": 40.0, "visual_change": 0.40, "chat_change": 0.20, "ui_change": 0.18,
         "center_change": 0.42, "purple_ratio": 0.06, "gold_ratio": 0.05, "red_ratio": 0.08},
        {"time": 60.0, **base},
        {"time": 79.0, **base},
    ]
    rows = make_candidates(transcript, energy, 80.0, s, video=video)
    assert rows
    assert any("multi-signal dynamic moment" in row["reason"] or
               "excitement signals aligned" in row["reason"] for row in rows)
