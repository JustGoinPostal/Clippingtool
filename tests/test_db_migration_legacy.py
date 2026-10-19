from __future__ import annotations

import sqlite3
from pathlib import Path

from app import db


def test_legacy_render_and_publish_tables_upgrade_before_new_indexes(tmp_path: Path, monkeypatch):
    path = tmp_path / "postal_autoclip.db"
    monkeypatch.setattr(db, "DB_PATH", path)

    with sqlite3.connect(path) as con:
        con.executescript("""
        CREATE TABLE clips (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          job_id INTEGER NOT NULL,
          start REAL NOT NULL,
          end REAL NOT NULL,
          score REAL NOT NULL,
          reason TEXT NOT NULL DEFAULT '',
          transcript TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'candidate',
          output_path TEXT NOT NULL DEFAULT '',
          title TEXT NOT NULL DEFAULT '',
          description TEXT NOT NULL DEFAULT '',
          hashtags TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE renders (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          clip_id INTEGER NOT NULL,
          variant TEXT NOT NULL,
          output_path TEXT NOT NULL,
          render_start REAL NOT NULL DEFAULT 0,
          render_end REAL NOT NULL DEFAULT 0,
          focus_mode TEXT NOT NULL DEFAULT 'center',
          quality_score REAL NOT NULL DEFAULT 0,
          quality_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(clip_id,variant)
        );

        CREATE TABLE publish_queue (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          clip_id INTEGER NOT NULL,
          render_id INTEGER NOT NULL,
          platform TEXT NOT NULL,
          scheduled_for REAL NOT NULL,
          status TEXT NOT NULL DEFAULT 'queued',
          title TEXT NOT NULL DEFAULT '',
          caption TEXT NOT NULL DEFAULT '',
          hashtags TEXT NOT NULL DEFAULT '',
          privacy TEXT NOT NULL DEFAULT 'private',
          options_json TEXT NOT NULL DEFAULT '{}',
          attempts INTEGER NOT NULL DEFAULT 0,
          error TEXT NOT NULL DEFAULT '',
          platform_post_id TEXT NOT NULL DEFAULT '',
          platform_url TEXT NOT NULL DEFAULT '',
          result_json TEXT NOT NULL DEFAULT '{}',
          published_at REAL NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        INSERT INTO clips(job_id,start,end,score,title) VALUES(1,10,20,7.5,'legacy clip');
        INSERT INTO renders(clip_id,variant,output_path,quality_score) VALUES(1,'22','legacy.mp4',88.0);
        INSERT INTO publish_queue(clip_id,render_id,platform,scheduled_for) VALUES(1,1,'youtube',123.0);
        """)
        con.commit()

    db.init_db()

    with sqlite3.connect(path) as con:
        render_columns = {row[1] for row in con.execute("PRAGMA table_info(renders)")}
        publish_columns = {row[1] for row in con.execute("PRAGMA table_info(publish_queue)")}
        indexes = {row[1] for row in con.execute("SELECT type,name,tbl_name,rootpage,sql FROM sqlite_master WHERE type='index'")}

        assert {"qa_status", "qa_json", "is_best"} <= render_columns
        assert {"next_attempt_at", "last_attempt_at"} <= publish_columns
        assert "idx_renders_qa" in indexes
        assert "idx_publish_retry" in indexes
        assert con.execute("SELECT output_path FROM renders WHERE id=1").fetchone()[0] == "legacy.mp4"
        assert con.execute("SELECT platform FROM publish_queue WHERE id=1").fetchone()[0] == "youtube"
