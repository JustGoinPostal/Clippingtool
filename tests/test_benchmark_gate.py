from app.benchmark_gate import compare_metrics


def _metrics(**overrides):
    base={
        "label_count":20,
        "prediction_count":18,
        "recall":0.85,
        "weighted_recall":0.88,
        "precision":0.78,
        "top_k_label_recall":0.65,
        "duplicate_prediction_rate":0.08,
        "false_positive_rate":0.12,
        "mean_boundary_iou":0.48,
        "event_type_accuracy":0.90,
    }
    base.update(overrides)
    return base


def test_gate_passes_small_expected_noise():
    baseline=_metrics()
    current=_metrics(recall=0.84,weighted_recall=0.87,precision=0.76,duplicate_prediction_rate=0.09)
    report=compare_metrics(current,baseline)
    assert report["passed"] is True
    assert report["failures"]==[]


def test_gate_fails_meaningful_recall_regression():
    report=compare_metrics(_metrics(recall=0.79),_metrics(recall=0.85))
    assert report["passed"] is False
    assert any(x["metric"]=="recall" and "regressed" in x["rule"] for x in report["failures"])


def test_gate_fails_duplicate_explosion():
    report=compare_metrics(_metrics(duplicate_prediction_rate=0.18),_metrics(duplicate_prediction_rate=0.08))
    assert report["passed"] is False
    assert any(x["metric"]=="duplicate_prediction_rate" for x in report["failures"])


def test_gate_has_bootstrap_floors_without_baseline():
    report=compare_metrics(_metrics(weighted_recall=0.60,precision=0.40,top_k_label_recall=0.30),{})
    assert report["passed"] is False
    metrics={x["metric"] for x in report["failures"]}
    assert {"weighted_recall","precision","top_k_label_recall"}.issubset(metrics)


def test_empty_label_set_cannot_fake_a_pass():
    report=compare_metrics(_metrics(label_count=0,prediction_count=0),{})
    assert report["passed"] is False
    assert any(x["metric"]=="label_count" for x in report["failures"])
