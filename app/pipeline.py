from __future__ import annotations
import hashlib, json, traceback
from pathlib import Path
from .config import load_settings
from . import db
from .media import duration, audio_energy
from .transcribe import transcribe
from .scoring import make_candidates
from .metadata import make_metadata
from .render import render_clip
from .video_events import analyze_video
from .learning import learned_profile
from .ranker import local_ai_second_pass
from .media_time import recording_start_epoch
from .osrs_events import map_events_to_recording


def _key(path: Path):
    st=path.stat(); raw=f"{path.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode(); return hashlib.sha1(raw).hexdigest()[:16]


def process_job(job_id: int):
    s=load_settings(); job=db.q("SELECT * FROM jobs WHERE id=?",(job_id,),one=True)
    if not job: return
    path=Path(job["source_path"])
    def msg(text,prog=None):
        fields={"message":text}
        if prog is not None: fields["progress"]=prog
        db.update_job(job_id,**fields)
    try:
        db.update_job(job_id,status="processing",progress=0.02,message="Probing video")
        if not path.exists(): raise FileNotFoundError(path)
        key=_key(path); cache=s.cache_path/key; cache.mkdir(parents=True,exist_ok=True)
        d=duration(path); db.update_job(job_id,duration=d)
        msg("Analyzing audio energy",0.07)
        energy_file=cache/"energy.txt"; energy_json=cache/"energy.json"
        if energy_json.exists(): energy=json.loads(energy_json.read_text())
        else:
            energy=audio_energy(path,energy_file); energy_json.write_text(json.dumps(energy))
        msg("Scanning OSRS/game visuals",0.14)
        video_json=cache/"video_events.json"
        if video_json.exists(): video=json.loads(video_json.read_text())
        else:
            video=analyze_video(path,d,s); video_json.write_text(json.dumps(video))
        msg("Transcribing stream",0.22)
        tx=transcribe(path,s,cache/"transcript.json",lambda x:msg(x,0.42))
        msg("Mapping exact RuneLite events",0.64)
        game_events=[]
        if s.runelite_bridge_enabled:
            start_epoch,start_source=recording_start_epoch(path,d)
            raw_events=db.game_events_between(start_epoch-8,start_epoch+d+8)
            game_events=map_events_to_recording(raw_events,start_epoch,d)
            (cache/"runelite_events.json").write_text(json.dumps({"recording_start_epoch":start_epoch,"source":start_source,"events":game_events},indent=2),encoding="utf-8")
        msg("Learning your clip preferences",0.70)
        profile=learned_profile()
        msg("Scoring OSRS moments and de-duplicating",0.78)
        candidates=make_candidates(tx,energy,d,s,video=video,learned=profile,game_events=game_events)
        msg("Running optional local AI second pass",0.88)
        candidates=local_ai_second_pass(candidates,s)
        for c in candidates:
            c["title"],c["description"],c["hashtags"]=make_metadata(c)
            if c.get("ai_title"): c["title"]=c["ai_title"]
        db.replace_clips(job_id,candidates)
        db.update_job(job_id,status="ready",progress=1.0,message=f"Found {len(candidates)} diverse candidate clips")
    except Exception as e:
        db.update_job(job_id,status="error",message=f"{type(e).__name__}: {e}")
        (s.cache_path/f"job_{job_id}_error.txt").write_text(traceback.format_exc(),encoding="utf-8")


def render_clip_id(clip_id: int):
    s=load_settings(); clip=db.q("SELECT * FROM clips WHERE id=?",(clip_id,),one=True)
    if not clip: raise KeyError(clip_id)
    job=db.q("SELECT * FROM jobs WHERE id=?",(clip["job_id"],),one=True); source=Path(job["source_path"])
    key=_key(source); tx=json.loads((s.cache_path/key/"transcript.json").read_text(encoding="utf-8"))
    safe="".join(c if c.isalnum() or c in "-_" else "_" for c in clip["title"][:45]).strip("_") or f"clip_{clip_id}"
    out=s.output_path/f"{clip_id:04d}_{safe}.mp4"
    db.exec_sql("UPDATE clips SET status='rendering' WHERE id=?",(clip_id,))
    try:
        render_clip(source,clip,tx.get("words",[]),out,s)
        db.exec_sql("UPDATE clips SET status='rendered', output_path=? WHERE id=?",(str(out),clip_id))
    except Exception:
        db.exec_sql("UPDATE clips SET status='error' WHERE id=?",(clip_id,)); raise
