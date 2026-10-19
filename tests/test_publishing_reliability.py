from pathlib import Path
from types import SimpleNamespace

from app import db
import app.publishing as publishing


def _seed_publish_job(tmp_path: Path, platform: str) -> int:
    job_id = db.exec_sql(
        "INSERT INTO jobs(source_path,status) VALUES(?,?)",
        (str(tmp_path / f"{platform}.mp4"), "ready"),
    )
    clip_id = db.exec_sql(
        "INSERT INTO clips(job_id,start,end,score,title,description,hashtags) VALUES(?,?,?,?,?,?,?)",
        (job_id, 1.0, 20.0, 90.0, f"{platform} clip", "caption", "#osrs"),
    )
    render_id = db.exec_sql(
        "INSERT INTO renders(clip_id,variant,output_path,quality_score,is_best) VALUES(?,?,?,?,?)",
        (clip_id, "short", str(tmp_path / f"{platform}_short.mp4"), 90.0, 1),
    )
    return db.add_publish_job(clip_id, render_id, platform, 1.0, "title", "caption", "#osrs", "private", {})


def test_retry_delay_is_exponential_and_capped(monkeypatch):
    monkeypatch.setattr(
        publishing,
        "load_settings",
        lambda: SimpleNamespace(publish_retry_base_seconds=10, publish_retry_max_seconds=40),
    )
    assert publishing._retry_delay(1) == 10
    assert publishing._retry_delay(2) == 20
    assert publishing._retry_delay(3) == 40
    assert publishing._retry_delay(4) == 40


def test_recover_interrupted_posts_fails_closed(tmp_path: Path, monkeypatch):
    original = db.DB_PATH
    db.DB_PATH = tmp_path / "postal_test.db"
    try:
        db.init_db()
        checkpointed = _seed_publish_job(tmp_path, "tiktok")
        ambiguous = _seed_publish_job(tmp_path, "youtube")
        db.update_publish_job(
            checkpointed,
            status="publishing",
            last_attempt_at=1.0,
            platform_post_id="publish_123",
        )
        db.update_publish_job(ambiguous, status="publishing", last_attempt_at=1.0)
        monkeypatch.setattr(
            publishing,
            "load_settings",
            lambda: SimpleNamespace(publish_stale_seconds=60),
        )

        changed = publishing.recover_interrupted_posts()
        assert changed == 2

        saved_checkpointed = db.q("SELECT * FROM publish_queue WHERE id=?", (checkpointed,), one=True)
        saved_ambiguous = db.q("SELECT * FROM publish_queue WHERE id=?", (ambiguous,), one=True)
        assert saved_checkpointed["status"] == "submitted"
        assert saved_checkpointed["platform_post_id"] == "publish_123"
        assert saved_ambiguous["status"] == "needs_review"
        assert "avoid a duplicate" in saved_ambiguous["error"]
    finally:
        db.DB_PATH = original
