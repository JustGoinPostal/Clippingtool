from pathlib import Path
from types import SimpleNamespace

import pytest

from app import db
import app.publishing as publishing


def _publishing_settings(max_attempts: int = 3):
    return SimpleNamespace(
        publish_max_attempts=max_attempts,
        publish_retry_base_seconds=10,
        publish_retry_max_seconds=60,
        publish_stale_seconds=60,
        auto_cover_enabled=False,
        publish_poll_seconds=20,
    )


def _qa_settings():
    return SimpleNamespace(render_qa_enabled=True, render_qa_block_publish=True)


def _seed(tmp_path: Path, *, qa_status: str = "pass", scheduled_for: float = 1.0, platform: str = "youtube", direct_queue: bool = False) -> int:
    job_id=db.exec_sql("INSERT INTO jobs(source_path,status) VALUES(?,?)",(str(tmp_path/f"{platform}_{qa_status}.mkv"),"ready"))
    clip_id=db.exec_sql("INSERT INTO clips(job_id,start,end,score,title) VALUES(?,?,?,?,?)",(job_id,0.0,22.0,90.0,"contract test"))
    render_id=db.exec_sql("INSERT INTO renders(clip_id,variant,output_path,quality_score,qa_status,is_best) VALUES(?,?,?,?,?,?)",
                          (clip_id,"short",str(tmp_path/f"{platform}_{qa_status}.mp4"),90.0,qa_status,1 if qa_status=="pass" else 0))
    if direct_queue:
        return db.exec_sql("INSERT INTO publish_queue(clip_id,render_id,platform,scheduled_for) VALUES(?,?,?,?)",
                           (clip_id,render_id,platform,scheduled_for))
    return db.add_publish_job(clip_id,render_id,platform,scheduled_for)


def _with_db(tmp_path: Path):
    original=db.DB_PATH
    db.DB_PATH=tmp_path/"contract.db"
    db.init_db()
    return original


def test_transient_failure_requeues_with_backoff(tmp_path: Path, monkeypatch):
    original=_with_db(tmp_path)
    try:
        monkeypatch.setattr(db,"load_settings",_qa_settings)
        monkeypatch.setattr(publishing,"load_settings",lambda:_publishing_settings(3))
        job_id=_seed(tmp_path)
        monkeypatch.setattr(publishing,"_publish_one",lambda row: (_ for _ in ()).throw(RuntimeError("503 upstream")))
        publishing.process_due_posts()
        row=db.q("SELECT * FROM publish_queue WHERE id=?",(job_id,),one=True)
        assert row["status"]=="queued"
        assert row["attempts"]==1
        assert row["next_attempt_at"]>0
        assert "retry scheduled" in row["error"]
    finally:
        db.DB_PATH=original


def test_exhausted_failure_becomes_failed(tmp_path: Path, monkeypatch):
    original=_with_db(tmp_path)
    try:
        monkeypatch.setattr(db,"load_settings",_qa_settings)
        monkeypatch.setattr(publishing,"load_settings",lambda:_publishing_settings(1))
        job_id=_seed(tmp_path)
        monkeypatch.setattr(publishing,"_publish_one",lambda row: (_ for _ in ()).throw(RuntimeError("429 exhausted")))
        publishing.process_due_posts()
        row=db.q("SELECT * FROM publish_queue WHERE id=?",(job_id,),one=True)
        assert row["status"]=="failed"
        assert row["attempts"]==1
        assert row["next_attempt_at"]==0
        assert "429 exhausted" in row["error"]
    finally:
        db.DB_PATH=original


def test_ambiguous_submission_without_checkpoint_requires_review(tmp_path: Path, monkeypatch):
    original=_with_db(tmp_path)
    try:
        monkeypatch.setattr(db,"load_settings",_qa_settings)
        monkeypatch.setattr(publishing,"load_settings",lambda:_publishing_settings())
        job_id=_seed(tmp_path)
        monkeypatch.setattr(publishing,"_publish_one",lambda row: (_ for _ in ()).throw(publishing.SubmissionUncertain("timeout after submit")))
        publishing.process_due_posts()
        row=db.q("SELECT * FROM publish_queue WHERE id=?",(job_id,),one=True)
        assert row["status"]=="needs_review"
        assert row["next_attempt_at"]==0
        assert "timeout after submit" in row["error"]
    finally:
        db.DB_PATH=original


def test_checkpointed_partial_upload_is_never_blindly_replayed(tmp_path: Path, monkeypatch):
    original=_with_db(tmp_path)
    try:
        monkeypatch.setattr(db,"load_settings",_qa_settings)
        monkeypatch.setattr(publishing,"load_settings",lambda:_publishing_settings())
        job_id=_seed(tmp_path,platform="tiktok")
        def partial(row):
            db.update_publish_job(int(row["id"]),status="submitted",platform_post_id="publish_checkpoint_123")
            raise RuntimeError("socket reset after checkpoint")
        monkeypatch.setattr(publishing,"_publish_one",partial)
        publishing.process_due_posts()
        row=db.q("SELECT * FROM publish_queue WHERE id=?",(job_id,),one=True)
        assert row["status"]=="submitted"
        assert row["platform_post_id"]=="publish_checkpoint_123"
        assert "after platform checkpoint" in row["error"]
    finally:
        db.DB_PATH=original


def test_unsafe_legacy_job_does_not_block_a_safe_due_job(tmp_path: Path, monkeypatch):
    original=_with_db(tmp_path)
    try:
        monkeypatch.setattr(db,"load_settings",_qa_settings)
        monkeypatch.setattr(publishing,"load_settings",lambda:_publishing_settings())
        unsafe=_seed(tmp_path,qa_status="unknown",scheduled_for=1.0,direct_queue=True)
        safe=_seed(tmp_path,qa_status="pass",scheduled_for=2.0)
        monkeypatch.setattr(publishing,"_publish_one",lambda row:{"platform_post_id":f"remote_{row['id']}","url":"https://example.invalid/post","raw":{},"async":False})
        publishing.process_due_posts(limit=5)
        bad=db.q("SELECT * FROM publish_queue WHERE id=?",(unsafe,),one=True)
        good=db.q("SELECT * FROM publish_queue WHERE id=?",(safe,),one=True)
        assert bad["status"]=="needs_review"
        assert "Render QA" in bad["error"]
        assert good["status"]=="published"
        assert good["platform_post_id"]==f"remote_{safe}"
    finally:
        db.DB_PATH=original


def test_tiktok_processing_failure_becomes_failed(tmp_path: Path, monkeypatch):
    original=_with_db(tmp_path)
    try:
        monkeypatch.setattr(db,"load_settings",_qa_settings)
        job_id=_seed(tmp_path,platform="tiktok")
        db.update_publish_job(job_id,status="submitted",platform_post_id="publish_1")
        monkeypatch.setattr(publishing,"tiktok_publish_status",lambda _: {"status":"FAILED","fail_reason":"platform processing rejected media"})
        publishing.poll_submitted_tiktok()
        row=db.q("SELECT * FROM publish_queue WHERE id=?",(job_id,),one=True)
        assert row["status"]=="failed"
        assert "rejected media" in row["error"]
    finally:
        db.DB_PATH=original


def test_instagram_processing_error_becomes_failed(tmp_path: Path, monkeypatch):
    original=_with_db(tmp_path)
    try:
        monkeypatch.setattr(db,"load_settings",_qa_settings)
        job_id=_seed(tmp_path,platform="instagram")
        db.update_publish_job(job_id,status="submitted",platform_post_id="container_1")
        monkeypatch.setattr(publishing,"instagram_container_status",lambda _: {"status_code":"ERROR","status":"Transcode failed"})
        publishing.poll_submitted_instagram()
        row=db.q("SELECT * FROM publish_queue WHERE id=?",(job_id,),one=True)
        assert row["status"]=="failed"
        assert "Transcode failed" in row["error"]
    finally:
        db.DB_PATH=original
