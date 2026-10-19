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
    assert payload["assisted"] is False
    assert payload["labels"][1]["event_type"]=="pet_drop"
    assert not (tmp_path/"labels"/"job_7.labels.tmp").exists()


def test_legacy_label_draft_without_provenance_fails_closed(tmp_path: Path, monkeypatch):
    label_dir=tmp_path/"labels"; label_dir.mkdir()
    monkeypatch.setattr(benchmark_labeler,"LABEL_DIR",label_dir)
    legacy={"schema_version":1,"job_id":12,"labels":[
        {"id":"old","start":1,"end":3,"event_type":"pvp_kill","weight":1.0}
    ]}
    (label_dir/"job_12.labels.json").write_text(json.dumps(legacy),encoding="utf-8")
    state=benchmark_labeler.load_label_state(12)
    assert state["assisted"] is True
    assert state["labels"][0]["id"]=="old"

    # The pre-schema list format is also untrusted for held-out provenance.
    (label_dir/"job_13.labels.json").write_text(json.dumps(legacy["labels"]),encoding="utf-8")
    assert benchmark_labeler.load_label_state(13)["assisted"] is True


def test_corrupt_existing_provenance_stays_tuning_only_after_resave(tmp_path: Path, monkeypatch):
    label_dir=tmp_path/"labels"; label_dir.mkdir()
    monkeypatch.setattr(benchmark_labeler,"LABEL_DIR",label_dir)
    monkeypatch.setattr(benchmark_labeler,"_job",lambda job_id:{"id":job_id,"source_path":"vod.mp4"})
    (label_dir/"job_14.labels.json").write_text("{not json",encoding="utf-8")
    assert benchmark_labeler.load_label_state(14)["assisted"] is True
    benchmark_labeler.save_labels(14,[
        {"id":"rebuilt","start":4,"end":9,"event_type":"boss_kill","weight":1.0}
    ])
    assert benchmark_labeler.load_label_state(14)["assisted"] is True


def test_revealing_predictions_permanently_marks_label_draft_assisted(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(benchmark_labeler,"LABEL_DIR",tmp_path/"labels")
    monkeypatch.setattr(benchmark_labeler,"_job",lambda job_id:{"id":job_id,"source_path":"vod.mp4"})
    benchmark_labeler.save_labels(8,[
        {"id":"truth","start":1,"end":4,"event_type":"pvp_kill","weight":1.0},
    ])
    assert benchmark_labeler.load_label_state(8)["assisted"] is False
    marked=benchmark_labeler.mark_assisted(8)
    assert marked["assisted"] is True

    # Editing/saving labels after the reveal must never reset contamination.
    benchmark_labeler.save_labels(8,[
        {"id":"truth","start":1.2,"end":4.2,"event_type":"pvp_kill","weight":1.0},
    ])
    reloaded=benchmark_labeler.load_label_state(8)
    assert reloaded["assisted"] is True
    assert reloaded["labels"][0]["start"]==1.2


def test_heldout_export_refuses_server_marked_assisted_labeling(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(benchmark_labeler,"_job",lambda job_id:{"id":job_id,"source_path":"owned.mp4"})
    monkeypatch.setattr(benchmark_labeler,"load_label_state",lambda job_id:{
        "schema_version":1,"job_id":job_id,"assisted":True,
        "labels":[{"id":"truth","start":1,"end":3,"event_type":"pvp_kill","weight":1.0}],
    })
    monkeypatch.setattr(benchmark_labeler,"PRIVATE_DIR",tmp_path/"private")
    monkeypatch.setattr(benchmark_labeler,"MANIFEST_PATH",tmp_path/"private"/"corpus.json")
    with pytest.raises(ValueError,match="permanently marked assisted"):
        benchmark_labeler.export_session(1,"held_001","heldout")


def test_export_writes_private_case_and_manifest_without_media(monkeypatch, tmp_path: Path):
    private=tmp_path/"private"
    monkeypatch.setattr(benchmark_labeler,"PRIVATE_DIR",private)
    monkeypatch.setattr(benchmark_labeler,"MANIFEST_PATH",private/"corpus.json")
    monkeypatch.setattr(benchmark_labeler,"EXAMPLE_MANIFEST",tmp_path/"missing.example.json")
    monkeypatch.setattr(benchmark_labeler,"_job",lambda job_id:{"id":job_id,"source_path":"C:/private/owned_vod.mp4","status":"ready","duration":600})
    monkeypatch.setattr(benchmark_labeler,"load_label_state",lambda job_id:{
        "schema_version":1,"job_id":job_id,"assisted":False,
        "labels":[{"id":"purple","start":50,"end":65,"event_type":"raid_reward","weight":2.0}],
    })
    monkeypatch.setattr(benchmark_labeler,"export_job_case",lambda job_id,labels,top_k,max_predictions:{
        "schema_version":1,"job_id":job_id,"top_k":top_k,"labels":labels,
        "predictions":[{"clip_id":9,"start":49,"end":67,"score":95,"event_type":"raid_reward"}],
    })
    out=benchmark_labeler.export_session(4,"postal cox 001","heldout")
    assert out["session_id"]=="postal_cox_001"
    assert out["split"]=="heldout"
    assert out["labeling_mode"]=="blind"
    case=json.loads((private/"postal_cox_001.case.json").read_text(encoding="utf-8"))
    serialized=json.dumps(case)
    assert case["labeling_mode"]=="blind"
    assert "owned_vod.mp4" not in serialized
    assert "source_path" not in serialized
    manifest=json.loads((private/"corpus.json").read_text(encoding="utf-8"))
    assert manifest["sessions"]==[{
        "id":"postal_cox_001","split":"heldout","case":"postal_cox_001.case.json","labeling_mode":"blind"
    }]


def test_assisted_session_can_export_only_as_tuning(monkeypatch, tmp_path: Path):
    private=tmp_path/"private"
    monkeypatch.setattr(benchmark_labeler,"PRIVATE_DIR",private)
    monkeypatch.setattr(benchmark_labeler,"MANIFEST_PATH",private/"corpus.json")
    monkeypatch.setattr(benchmark_labeler,"EXAMPLE_MANIFEST",tmp_path/"missing.example.json")
    monkeypatch.setattr(benchmark_labeler,"_job",lambda job_id:{"id":job_id,"source_path":"owned.mp4","status":"ready","duration":100})
    monkeypatch.setattr(benchmark_labeler,"load_label_state",lambda job_id:{
        "schema_version":1,"job_id":job_id,"assisted":True,
        "labels":[{"id":"kill","start":10,"end":20,"event_type":"pvp_kill","weight":1.0}],
    })
    monkeypatch.setattr(benchmark_labeler,"export_job_case",lambda job_id,labels,top_k,max_predictions:{
        "schema_version":1,"job_id":job_id,"top_k":top_k,"labels":labels,"predictions":[],
    })
    out=benchmark_labeler.export_session(9,"assisted_pvp_001","tuning")
    assert out["labeling_mode"]=="assisted"
    assert out["blind_labeled"] is False
    manifest=json.loads((private/"corpus.json").read_text(encoding="utf-8"))
    assert manifest["sessions"][0]["labeling_mode"]=="assisted"
