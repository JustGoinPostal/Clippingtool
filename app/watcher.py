from __future__ import annotations
import threading, time
from pathlib import Path
from .config import load_settings
from .media import VIDEO_EXTS
from . import db
from .pipeline import process_job

_started=False

def scan_once(auto=True):
    s=load_settings(); found=[]
    for p in sorted(s.watch_path.glob("*")):
        if not p.is_file() or p.suffix.lower() not in VIDEO_EXTS: continue
        job_id=db.add_job(str(p.resolve())); found.append(job_id)
        row=db.q("SELECT status FROM jobs WHERE id=?",(job_id,),one=True)
        if auto and s.auto_process_new_files and row and row["status"]=="queued":
            threading.Thread(target=process_job,args=(job_id,),daemon=True).start()
    return found

def start_watcher():
    global _started
    if _started: return
    _started=True
    def loop():
        while True:
            try:
                s=load_settings(); scan_once(auto=True); time.sleep(max(10,s.poll_seconds))
            except Exception:
                time.sleep(30)
    threading.Thread(target=loop,daemon=True,name="PostalAutoClipWatcher").start()
