import json
from pathlib import Path

import pytest

from app import benchmark_labeler


def test_label_validation_normalizes_and_bounds_fields():
    row=benchmark_labeler._clean_label({
        "id":"My PK #1","start":10,"end":15.1256,"event_type":"pvp_kill","weight":2.5,
        "note":"important payoff",
    },0)
    assert row["id"]=="My_PK_1"
    assert row["start"]==10.0
    assert row["end"]==15.126
    assert row["event_type"]=="pvp_kill"
    assert row["weight"]==2.5
    with pytest.raises(ValueError):
        benchmark_labeler._clean_label({"start":5,"end":4,"event_type":"pvp_kill"},0)
    with pytest.raises(ValueError):
        benchmark_labeler._clean_label({"start":1,"end":2,"event_type":"made_up"},0)


def test_save_load_labels_is_local_and_atomic(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(benchmark_labeler,"LABEL_DIR",tmp_path/"labels")
    monkeypatch.setattr(benchmark_labeler,"_job",lambda job_id:{"id":job_id,"source_path":"vod.mp4"})
    saved=benchmark_labeler.save_labels(7,[
        {"id":"kill_1","start":2,"end":8,"event_type":"pvp_kill","weight":1.5},
        {"id":"pet_1","start":20,"end":25,"event_type":"pet_drop","weight":3.0},
    ])
    assert len(saved)==2
    assert benchmark_labeler.load_labels(7)==saved
    payload=json.loads((tmp_path/"labels"/"job_7.labels.json").read_text(encoding="utf-8"))
    assert payload["job_id"]==7
    assert payload["labels"][1]["event_type"]=="pet_drop"
    assert not (tmp_path/"labels"/"job_7.labels.tmp").exists()


def test_heldout_export_refuses_assisted_labeling(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(benchmark_labeler,"_job",lambda job_id:{"id":job_id,"source_path":"owned.mp4"})
    monkeypatch.setattr(benchmark_labeler,"load_labels",lambda job_id:[{"id":"truth","start":1,"end":3,"event_type":"pvp_kill","weight":1.0}])
    monkeypatch.setattr(benchmark_labeler,"PRIVATE_DIR",tmp_path/"private")
    monkeypatch.setattr(benchmark_labeler,"MANIFEST_PATH",tmp_path/"private"/"corpus.json")
    with pytest.raises(ValueError,match="held-out sessions must be labeled blind"):
        benchmark_labeler.export_session(1,"held_001","heldout",blind_labeled=False)


def test_export_writes_private_case_and_manifest_without_media(monkeypatch, tmp_path: Path):
    private=tmp_path/"private"
    monkeypatch.setattr(benchmark_labeler,"PRIVATE_DIR",private)
    monkeypatch.setattr(benchmark_labeler,"MANIFEST_PATH",private/"corpus.json")
    monkeypatch.setattr(benchmark_labeler,"EXAMPLE_MANIFEST",tmp_path/"missing.example.json")
    monkeypatch.setattr(benchmark_labeler,"_job",lambda job_id:{"id":job_id,"source_path":"C:/private/owned_vod.mp4","status":"ready","duration":600})
    monkeypatch.setattr(benchmark_labeler,"load_labels",lambda job_id:[
        {"id":"purple","start":50,"end":65,"event_type":"raid_reward","weight":2.0}
    ])
    monkeypatch.setattr(benchmark_labeler,"export_job_case",lambda job_id,labels,top_k,max_predictions:{
        "schema_version":1,"job_id":job_id,"top_k":top_k,"labels":labels,
        "predictions":[{"clip_id":9,"start":49,"end":67,"score":95,"event_type":"raid_reward"}],
    })
    out=benchmark_labeler.export_session(4,"postal cox 001","heldout",blind_labeled=True)
    assert out["session_id"]=="postal_cox_001"
    assert out["split"]=="heldout"
    case=json.loads((private/"postal_cox_001.case.json").read_text(encoding="utf-8"))
    serialized=json.dumps(case)
    assert case["labeling_mode"]=="blind"
    assert "owned_vod.mp4" not in serialized
    assert "source_path" not in serialized
    manifest=json.loads((private/"corpus.json").read_text(encoding="utf-8"))
    assert manifest["sessions"]==[{
        "id":"postal_cox_001","split":"heldout","case":"postal_cox_001.case.json","labeling_mode":"blind"
    }]
