from pathlib import Path
from types import SimpleNamespace

import pytest

from app import db


def _settings(enabled=True, block=True):
    return SimpleNamespace(render_qa_enabled=enabled, render_qa_block_publish=block)


def _seed(tmp_path: Path, qa_status: str) -> tuple[int,int,int]:
    job_id=db.exec_sql("INSERT INTO jobs(source_path,status) VALUES(?,?)",(str(tmp_path/"vod.mkv"),"ready"))
    clip_id=db.exec_sql("INSERT INTO clips(job_id,start,end,score,title) VALUES(?,?,?,?,?)",(job_id,0.0,22.0,90.0,"test clip"))
    render_id=db.exec_sql("INSERT INTO renders(clip_id,variant,output_path,quality_score,qa_status) VALUES(?,?,?,?,?)",
                          (clip_id,"short",str(tmp_path/"clip.mp4"),91.0,qa_status))
    return job_id,clip_id,render_id


def test_new_publish_job_requires_qa_pass(tmp_path: Path, monkeypatch):
    original=db.DB_PATH; db.DB_PATH=tmp_path/"test.db"
    try:
        db.init_db(); monkeypatch.setattr(db,"load_settings",lambda:_settings())
        _,clip_id,render_id=_seed(tmp_path,"review")
        with pytest.raises(RuntimeError) as exc:
            db.add_publish_job(clip_id,render_id,"youtube",1.0)
        assert "Render QA is REVIEW" in str(exc.value)
        assert db.q("SELECT * FROM publish_queue")==[]
    finally:
        db.DB_PATH=original


def test_qa_pass_render_can_be_queued(tmp_path: Path, monkeypatch):
    original=db.DB_PATH; db.DB_PATH=tmp_path/"test.db"
    try:
        db.init_db(); monkeypatch.setattr(db,"load_settings",lambda:_settings())
        _,clip_id,render_id=_seed(tmp_path,"pass")
        publish_id=db.add_publish_job(clip_id,render_id,"youtube",1.0)
        assert publish_id > 0
        assert db.q("SELECT status FROM publish_queue WHERE id=?",(publish_id,),one=True)["status"]=="queued"
    finally:
        db.DB_PATH=original


def test_legacy_queued_unknown_render_is_quarantined_before_network_stage(tmp_path: Path, monkeypatch):
    original=db.DB_PATH; db.DB_PATH=tmp_path/"test.db"
    try:
        db.init_db(); monkeypatch.setattr(db,"load_settings",lambda:_settings())
        _,clip_id,render_id=_seed(tmp_path,"unknown")
        publish_id=db.exec_sql("INSERT INTO publish_queue(clip_id,render_id,platform,scheduled_for) VALUES(?,?,?,?)",
                               (clip_id,render_id,"youtube",1.0))
        with pytest.raises(RuntimeError):
            db.update_publish_job(publish_id,status="publishing",attempts=1)
        saved=db.q("SELECT * FROM publish_queue WHERE id=?",(publish_id,),one=True)
        assert saved["status"]=="needs_review"
        assert "re-run QA" in saved["error"]
    finally:
        db.DB_PATH=original


def test_qa_guard_can_be_explicitly_disabled(tmp_path: Path, monkeypatch):
    original=db.DB_PATH; db.DB_PATH=tmp_path/"test.db"
    try:
        db.init_db(); monkeypatch.setattr(db,"load_settings",lambda:_settings(enabled=False,block=True))
        _,clip_id,render_id=_seed(tmp_path,"unknown")
        publish_id=db.add_publish_job(clip_id,render_id,"youtube",1.0)
        assert publish_id > 0
    finally:
        db.DB_PATH=original
