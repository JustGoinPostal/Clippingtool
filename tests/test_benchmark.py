from app.benchmark import evaluate_predictions


def test_benchmark_rewards_detection_but_scores_boundaries_separately():
    labels = [
        {"id": "purple", "start": 100.0, "end": 106.0, "event_type": "drop", "weight": 2},
        {"id": "reaction", "start": 210.0, "end": 218.0, "event_type": "reaction"},
    ]
    predictions = [
        {"start": 92.0, "end": 128.0, "score": 95, "event_type": "drop"},
        {"start": 208.0, "end": 220.0, "score": 88, "event_type": "reaction"},
        {"start": 99.0, "end": 126.0, "score": 80, "event_type": "drop"},
        {"start": 400.0, "end": 430.0, "score": 70, "event_type": "speech"},
    ]

    result = evaluate_predictions(labels, predictions, top_k=2)

    assert result["recall"] == 1.0
    assert result["weighted_recall"] == 1.0
    assert result["top_k_label_recall"] == 1.0
    assert result["event_type_accuracy"] == 1.0
    assert result["duplicate_prediction_rate"] == 0.25
    assert result["false_positive_rate"] == 0.25
    assert 0 < result["mean_boundary_iou"] < 1
    assert result["missed_label_ids"] == []


def test_benchmark_exposes_missed_high_value_moment():
    labels = [
        {"id": "smite", "time": 50.0, "tolerance_seconds": 2.0, "event_type": "pvp", "weight": 3},
        {"id": "chat", "time": 150.0, "tolerance_seconds": 3.0, "event_type": "reaction", "weight": 1},
    ]
    predictions = [
        {"start": 145.0, "end": 160.0, "score": 80, "event_type": "reaction"},
    ]

    result = evaluate_predictions(labels, predictions)

    assert result["recall"] == 0.5
    assert result["weighted_recall"] == 0.25
    assert result["missed_label_ids"] == ["smite"]
