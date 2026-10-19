import json
from pathlib import Path

from app import db
from app.hooks import generate_hook


def test_osrs_story_context_survives_database_round_trip(tmp_path: Path):
    original = db.DB_PATH
    db.DB_PATH = tmp_path / "postal_test.db"
    try:
        db.init_db()
        job_id = db.exec_sql(
            "INSERT INTO jobs(source_path,status) VALUES(?,?)",
            (str(tmp_path / "vod.mp4"), "ready"),
        )
        db.replace_clips(job_id, [{
            "start": 10.0,
            "end": 38.0,
            "score": 96.0,
            "reason": "exact RuneLite OSRS story moment",
            "transcript": "sit no way bro",
            "title": "52M PK on TargetName",
            "description": "desc",
            "hashtags": "#OSRS #OSRSPvP",
            "event_type": "pvp_kill",
            "features": {"osrs_story": 1.0, "high_value": 1.0},
            "base_score": 96.0,
            "personal_score": 0.0,
            "hook_text": "52M ON THE FLOOR",
            "story_archetype": "high_value_pk",
            "event_context": {
                "moment_archetype": "high_value_pk",
                "name": "TargetName",
                "loot_value": 52_000_000,
                "biggest_setup_hit": 72,
            },
        }])

        saved = db.q("SELECT * FROM clips WHERE job_id=?", (job_id,), one=True)
        assert saved["story_archetype"] == "high_value_pk"
        ctx = json.loads(saved["event_context_json"])
        assert ctx["name"] == "TargetName"
        assert ctx["loot_value"] == 52_000_000
        assert ctx["biggest_setup_hit"] == 72
        assert generate_hook(saved) == "52M ON THE FLOOR"
    finally:
        db.DB_PATH = original


def test_existing_database_gets_story_context_columns(tmp_path: Path):
    original = db.DB_PATH
    db.DB_PATH = tmp_path / "postal_test.db"
    try:
        # init_db is intentionally called twice to exercise idempotent migrations.
        db.init_db()
        db.init_db()
        columns = {row["name"] for row in db.q("PRAGMA table_info(clips)")}
        assert "story_archetype" in columns
        assert "event_context_json" in columns
    finally:
        db.DB_PATH = original
