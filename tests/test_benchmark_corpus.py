import json
from pathlib import Path

from app import benchmark_corpus, benchmark_export


def _write(path: Path, payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(payload),encoding="utf-8")


def test_corpus_aggregates_exact_counts_and_heldout_split(tmp_path: Path):
    tuning={
        "top_k":2,
        "labels":[
            {"id":"pk","start":10,"end":14,"event_type":"pvp_kill","weight":2},
            {"id":"pet","start":40,"end":44,"event_type":"pet_drop","weight":3},
        ],
        "predictions":[
            {"start":9,"end":16,"score":95,"event_type":"pvp_kill"},
            {"start":80,"end":90,"score":20,"event_type":"speech"},
        ],
    }
    heldout={
        "top_k":2,
        "labels":[{"id":"purple","start":100,"end":106,"event_type":"raid_reward","weight":2}],
        "predictions":[{"start":98,"end":110,"score":90,"event_type":"raid_reward"}],
    }
    _write(tmp_path/"tuning.json",tuning); _write(tmp_path/"heldout.json",heldout)
    manifest={
        "sessions":[
            {"id":"s1","split":"tuning","case":"tuning.json"},
            {"id":"s2","split":"heldout","case":"heldout.json"},
        ],
        "release_requirements":{
            "min_total_labels":3,"min_heldout_labels":1,"min_heldout_sessions":1,
            "required_event_types":["pvp_kill","pet_drop","raid_reward"],
        },
    }
    _write(tmp_path/"corpus.json",manifest)
    report=benchmark_corpus.evaluate_manifest(tmp_path/"corpus.json")
    assert report["session_count"]==2
    assert report["overall"]["label_count"]==3
    assert report["overall"]["prediction_count"]==3
    assert report["overall"]["matched_labels"]==2
    assert report["splits"]["heldout"]["metrics"]["recall"]==1.0
    assert report["event_type_counts"]["pet_drop"]==1
    assert report["coverage_failures"]==[]
    assert report["release_gate_passed"] is True


def test_corpus_fails_release_when_required_osrs_coverage_is_missing(tmp_path: Path):
    _write(tmp_path/"case.json",{
        "labels":[{"id":"one","start":1,"end":4,"event_type":"pvp_kill"}],
        "predictions":[{"start":0,"end":5,"score":90,"event_type":"pvp_kill"}],
    })
    _write(tmp_path/"corpus.json",{
        "sessions":[{"id":"only","split":"tuning","case":"case.json"}],
        "release_requirements":{
            "min_total_labels":5,"min_heldout_labels":2,"min_heldout_sessions":1,
            "required_event_types":["pvp_kill","raid_reward","pet_drop"],
        },
    })
    report=benchmark_corpus.evaluate_manifest(tmp_path/"corpus.json")
    text=" | ".join(report["coverage_failures"])
    assert report["release_gate_passed"] is False
    assert "held-out" in text
    assert "raid_reward" in text
    assert "pet_drop" in text


def test_corpus_uses_heldout_metrics_for_baseline_regression_gate(tmp_path: Path):
    _write(tmp_path/"case.json",{
        "labels":[
            {"id":"a","start":1,"end":4,"event_type":"pvp_kill"},
            {"id":"b","start":10,"end":14,"event_type":"raid_reward"},
        ],
        "predictions":[{"start":0,"end":5,"score":90,"event_type":"pvp_kill"}],
    })
    _write(tmp_path/"corpus.json",{
        "sessions":[{"id":"held","split":"heldout","case":"case.json"}],
        "release_requirements":{"min_total_labels":0,"min_heldout_labels":0,"min_heldout_sessions":0},
    })
    baseline={"splits":{"heldout":{"metrics":{
        "label_count":2,"prediction_count":2,"recall":1.0,"weighted_recall":1.0,"precision":1.0,
        "top_k_label_recall":1.0,"duplicate_prediction_rate":0.0,"false_positive_rate":0.0,
        "mean_boundary_iou":0.5,"event_type_accuracy":1.0,
    }}}}
    report=benchmark_corpus.evaluate_manifest(tmp_path/"corpus.json",baseline=baseline)
    assert report["regression_gate"]["passed"] is False
    assert report["release_gate_passed"] is False


def test_export_job_case_contains_only_prediction_metadata(monkeypatch):
    def fake_q(sql,args=(),one=False):
        if "FROM jobs" in sql:
            return {"id":7,"status":"ready","duration":600.0}
        return [{
            "id":11,"start":10.0,"end":38.0,"score":94.0,"event_type":"pvp_kill",
            "story_archetype":"high_value_pk","status":"candidate","title":"52M PK",
        }]
    monkeypatch.setattr(benchmark_export.db,"q",fake_q)
    payload=benchmark_export.export_job_case(7,[{"id":"truth","start":12,"end":16,"event_type":"pvp_kill"}])
    assert payload["job_id"]==7
    assert payload["predictions"][0]["clip_id"]==11
    serialized=json.dumps(payload)
    assert "source_path" not in serialized
    assert "transcript" not in serialized
