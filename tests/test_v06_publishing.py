from pathlib import Path

from app.config import Settings
from app.publishing import _tiktok_chunk_plan
from app import db


def test_v06_publish_defaults():
    s = Settings()
    assert s.publishing_enabled is True
    assert s.publish_poll_seconds >= 5
    assert s.youtube_default_privacy == "private"
    assert s.tiktok_default_privacy == "SELF_ONLY"


def test_tiktok_chunk_plan_is_bounded():
    chunk, count = _tiktok_chunk_plan(25 * 1024 * 1024)
    assert chunk == 10 * 1024 * 1024
    assert count == 3
    small_chunk, small_count = _tiktok_chunk_plan(2 * 1024 * 1024)
    assert small_chunk == 2 * 1024 * 1024
    assert small_count == 1


def test_publish_queue_round_trip(tmp_path: Path):
    original = db.DB_PATH
    db.DB_PATH = tmp_path / "postal_test.db"
    try:
        db.init_db()
        job_id = db.exec_sql("INSERT INTO jobs(source_path,status) VALUES(?,?)", (str(tmp_path / "vod.mp4"), "ready"))
        clip_id = db.exec_sql(
            "INSERT INTO clips(job_id,start,end,score,title,description,hashtags) VALUES(?,?,?,?,?,?,?)",
            (job_id, 10.0, 35.0, 90.0, "Test clip", "caption", "#osrs #shorts"),
        )
        render_id = db.exec_sql(
            "INSERT INTO renders(clip_id,variant,output_path,quality_score,is_best) VALUES(?,?,?,?,?)",
            (clip_id, "short", str(tmp_path / "short.mp4"), 92.0, 1),
        )
        publish_id = db.add_publish_job(
            clip_id, render_id, "youtube", 1234.0,
            "Test clip", "caption", "#osrs #shorts", "private", {},
        )
        rows = db.publish_jobs()
        row = next(x for x in rows if x["id"] == publish_id)
        assert row["platform"] == "youtube"
        assert row["status"] == "queued"
        assert row["variant"] == "short"
        db.update_publish_job(publish_id, status="published", platform_post_id="abc123")
        saved = db.q("SELECT * FROM publish_queue WHERE id=?", (publish_id,), one=True)
        assert saved["status"] == "published"
        assert saved["platform_post_id"] == "abc123"
    finally:
        db.DB_PATH = original
