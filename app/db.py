from __future__ import annotations
import sqlite3, json, threading
from pathlib import Path
from typing import Any
from .config import ROOT

DB_PATH = ROOT / "data" / "postal_autoclip.db"
_lock = threading.Lock()

def _con():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

def _ensure_column(c, table: str, col: str, ddl: str):
    names={r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
    if col not in names:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")

def init_db():
    with _lock, _con() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source_path TEXT UNIQUE NOT NULL,
          status TEXT NOT NULL DEFAULT 'queued',
          progress REAL NOT NULL DEFAULT 0,
          message TEXT NOT NULL DEFAULT '',
          duration REAL NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS clips (
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
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(job_id) REFERENCES jobs(id)
        );
        CREATE INDEX IF NOT EXISTS idx_clips_job ON clips(job_id);
        CREATE TABLE IF NOT EXISTS feedback (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          clip_id INTEGER UNIQUE NOT NULL,
          status TEXT NOT NULL,
          features_json TEXT NOT NULL DEFAULT '{}',
          event_type TEXT NOT NULL DEFAULT 'speech',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS game_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          event_time REAL NOT NULL,
          event_type TEXT NOT NULL,
          confidence REAL NOT NULL DEFAULT 1.0,
          payload_json TEXT NOT NULL DEFAULT '{}',
          source TEXT NOT NULL DEFAULT 'runelite',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_game_events_time ON game_events(event_time);
        CREATE TABLE IF NOT EXISTS renders (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          clip_id INTEGER NOT NULL,
          variant TEXT NOT NULL,
          output_path TEXT NOT NULL,
          render_start REAL NOT NULL DEFAULT 0,
          render_end REAL NOT NULL DEFAULT 0,
          focus_mode TEXT NOT NULL DEFAULT 'center',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(clip_id,variant),
          FOREIGN KEY(clip_id) REFERENCES clips(id)
        );
        CREATE INDEX IF NOT EXISTS idx_renders_clip ON renders(clip_id);
        """)
        _ensure_column(c,"clips","event_type","TEXT NOT NULL DEFAULT 'speech'")
        _ensure_column(c,"clips","features_json","TEXT NOT NULL DEFAULT '{}'")
        _ensure_column(c,"clips","base_score","REAL NOT NULL DEFAULT 0")
        _ensure_column(c,"clips","personal_score","REAL NOT NULL DEFAULT 0")
        _ensure_column(c,"clips","hook_text","TEXT NOT NULL DEFAULT ''")
        _ensure_column(c,"clips","best_variant","TEXT NOT NULL DEFAULT ''")
        _ensure_column(c,"renders","quality_score","REAL NOT NULL DEFAULT 0")
        _ensure_column(c,"renders","quality_json","TEXT NOT NULL DEFAULT '{}'")
        _ensure_column(c,"renders","is_best","INTEGER NOT NULL DEFAULT 0")
        c.commit()

def q(sql: str, args=(), one=False):
    with _lock, _con() as c:
        rows = c.execute(sql, args).fetchall()
    vals=[dict(r) for r in rows]
    return vals[0] if one and vals else (None if one else vals)

def exec_sql(sql: str, args=()):
    with _lock, _con() as c:
        cur=c.execute(sql,args); c.commit(); return cur.lastrowid

def add_job(path: str) -> int:
    try:
        return exec_sql("INSERT INTO jobs(source_path) VALUES(?)",(path,))
    except sqlite3.IntegrityError:
        row=q("SELECT id FROM jobs WHERE source_path=?",(path,),one=True)
        return int(row["id"])

def update_job(job_id: int, **fields):
    if not fields: return
    fields["updated_at"]="CURRENT_TIMESTAMP"
    sets=[]; vals=[]
    for k,v in fields.items():
        if k=="updated_at": sets.append("updated_at=CURRENT_TIMESTAMP")
        else: sets.append(f"{k}=?"); vals.append(v)
    vals.append(job_id)
    exec_sql(f"UPDATE jobs SET {', '.join(sets)} WHERE id=?",vals)

def replace_clips(job_id: int, clips: list[dict[str, Any]]):
    with _lock, _con() as c:
        old_ids=[r[0] for r in c.execute("SELECT id FROM clips WHERE job_id=?",(job_id,)).fetchall()]
        if old_ids:
            c.executemany("DELETE FROM renders WHERE clip_id=?",[(x,) for x in old_ids])
        c.execute("DELETE FROM clips WHERE job_id=?",(job_id,))
        for x in clips:
            c.execute("""INSERT INTO clips(job_id,start,end,score,reason,transcript,title,description,hashtags,
              event_type,features_json,base_score,personal_score,hook_text,best_variant)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(
              job_id,x["start"],x["end"],x["score"],x.get("reason",""),x.get("transcript",""),
              x.get("title",""),x.get("description",""),x.get("hashtags",""),x.get("event_type","speech"),
              json.dumps(x.get("features",{}),separators=(",",":")),
              x.get("base_score",x["score"]),x.get("personal_score",0),x.get("hook_text",""),""))
        c.commit()

def add_game_event(event_time: float, event_type: str, confidence: float=1.0,
                   payload: dict|None=None, source: str="runelite") -> int:
    return exec_sql(
        "INSERT INTO game_events(event_time,event_type,confidence,payload_json,source) VALUES(?,?,?,?,?)",
        (float(event_time),str(event_type),float(confidence),
         json.dumps(payload or {},separators=(",",":")),str(source))
    )

def game_events_between(start_epoch: float, end_epoch: float) -> list[dict[str, Any]]:
    rows=q("SELECT * FROM game_events WHERE event_time BETWEEN ? AND ? ORDER BY event_time",
           (float(start_epoch),float(end_epoch)))
    for r in rows:
        try: r["payload"]=json.loads(r.pop("payload_json") or "{}")
        except Exception: r["payload"]={}
    return rows

def upsert_render(clip_id: int, variant: str, output_path: str,
                  render_start: float, render_end: float, focus_mode: str,
                  quality_score: float=0.0, quality: dict|None=None):
    exec_sql("""INSERT INTO renders(clip_id,variant,output_path,render_start,render_end,focus_mode,
                quality_score,quality_json,is_best,updated_at)
                VALUES(?,?,?,?,?,?,?,?,0,CURRENT_TIMESTAMP)
                ON CONFLICT(clip_id,variant) DO UPDATE SET
                output_path=excluded.output_path,render_start=excluded.render_start,
                render_end=excluded.render_end,focus_mode=excluded.focus_mode,
                quality_score=excluded.quality_score,quality_json=excluded.quality_json,
                is_best=0,updated_at=CURRENT_TIMESTAMP""",
             (clip_id,variant,output_path,float(render_start),float(render_end),focus_mode,
              float(quality_score),json.dumps(quality or {},separators=(",",":"))))

def choose_best_render(clip_id: int):
    rows=q("SELECT * FROM renders WHERE clip_id=? ORDER BY quality_score DESC,id ASC",(clip_id,))
    if not rows:
        exec_sql("UPDATE clips SET best_variant='' WHERE id=?",(clip_id,))
        return None
    best=rows[0]
    with _lock, _con() as c:
        c.execute("UPDATE renders SET is_best=0 WHERE clip_id=?",(clip_id,))
        c.execute("UPDATE renders SET is_best=1 WHERE id=?",(best["id"],))
        c.execute("UPDATE clips SET best_variant=?,output_path=? WHERE id=?",
                  (best["variant"],best["output_path"],clip_id))
        c.commit()
    best["is_best"]=1
    return best

def clip_renders(clip_id: int):
    return q("SELECT * FROM renders WHERE clip_id=? ORDER BY is_best DESC,quality_score DESC,id",(clip_id,))
