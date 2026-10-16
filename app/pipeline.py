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
from .hooks import generate_hook
from .quality import evaluate_render
from .debug_log import start_job_log, append_job_log, append_job_exception

def _key(path: Path):
    st=path.stat()
    raw=f"{path.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode()
    return hashlib.sha1(raw).hexdigest()[:16]

def process_job(job_id: int):
    s=load_settings(); job=db.q("SELECT * FROM jobs WHERE id=?",(job_id,),one=True)
    if not job: return
    path=Path(job["source_path"])
    start_job_log(job_id,str(path))
    def msg(text,prog=None,level="INFO"):
        fields={"message":text}
        if prog is not None: fields["progress"]=prog
        db.update_job(job_id,**fields)
        append_job_log(job_id,text,level=level)
    try:
        db.update_job(job_id,status="processing",progress=0.02,message="Probing video")
        append_job_log(job_id,"Probing video")
        if not path.exists(): raise FileNotFoundError(path)
        key=_key(path); cache=s.cache_path/key; cache.mkdir(parents=True,exist_ok=True)
        append_job_log(job_id,f"Cache key: {key}")
        d=duration(path); db.update_job(job_id,duration=d)
        append_job_log(job_id,f"Video duration: {d:.3f} seconds")
        msg("Analyzing audio energy",0.07)
        energy_file=cache/"energy.txt"; energy_json=cache/"energy.json"
        if energy_json.exists():
            append_job_log(job_id,f"Using cached audio energy: {energy_json}")
            energy=json.loads(energy_json.read_text())
        else:
            energy=audio_energy(path,energy_file); energy_json.write_text(json.dumps(energy))
            append_job_log(job_id,f"Audio energy samples: {len(energy)}")
        msg("Scanning OSRS/game visuals",0.14)
        video_json=cache/"video_events.json"
        if video_json.exists():
            append_job_log(job_id,f"Using cached visual analysis: {video_json}")
            video=json.loads(video_json.read_text())
        else:
            video=analyze_video(path,d,s); video_json.write_text(json.dumps(video))
            append_job_log(job_id,f"Visual samples: {len(video)}")
        msg("Transcribing stream",0.22)
        tx=transcribe(path,s,cache/"transcript.json",lambda x:msg(x,0.42))
        append_job_log(job_id,f"Transcript segments: {len(tx.get('segments',[]))}; words: {len(tx.get('words',[]))}")
        msg("Mapping exact RuneLite events",0.64)
        game_events=[]
        if s.runelite_bridge_enabled:
            start_epoch,start_source=recording_start_epoch(path,d)
            append_job_log(job_id,f"Recording start epoch: {start_epoch} ({start_source})")
            raw_events=db.game_events_between(start_epoch-8,start_epoch+d+8)
            game_events=map_events_to_recording(raw_events,start_epoch,d)
            append_job_log(job_id,f"RuneLite events in recording window: raw={len(raw_events)} mapped={len(game_events)}")
            (cache/"runelite_events.json").write_text(
                json.dumps({"recording_start_epoch":start_epoch,"source":start_source,"events":game_events},indent=2),
                encoding="utf-8"
            )
        else:
            append_job_log(job_id,"RuneLite bridge disabled; skipping exact event mapping")
        msg("Learning your clip preferences",0.70)
        profile=learned_profile()
        msg("Scoring OSRS moments and de-duplicating",0.78)
        candidates=make_candidates(tx,energy,d,s,video=video,learned=profile,game_events=game_events)
        append_job_log(job_id,f"Candidate clips after scoring/de-duplication: {len(candidates)}")
        msg("Running optional local AI second pass",0.88)
        candidates=local_ai_second_pass(candidates,s)
        append_job_log(job_id,f"Candidate clips after local AI second pass: {len(candidates)}")
        for c in candidates:
            c["title"],c["description"],c["hashtags"]=make_metadata(c)
            if c.get("ai_title"): c["title"]=c["ai_title"]
            c["hook_text"]=generate_hook(c) if s.auto_hook_enabled else ""
        db.replace_clips(job_id,candidates)
        done=f"Found {len(candidates)} diverse candidate clips"
        db.update_job(job_id,status="ready",progress=1.0,message=done)
        append_job_log(job_id,done)
        append_job_log(job_id,"Analysis completed successfully")
    except Exception as e:
        tb=traceback.format_exc()
        db.update_job(job_id,status="error",message=f"{type(e).__name__}: {e}")
        append_job_log(job_id,f"{type(e).__name__}: {e}",level="ERROR")
        append_job_exception(job_id,tb)
        error_path=s.cache_path/f"job_{job_id}_error.txt"
        error_path.parent.mkdir(parents=True,exist_ok=True)
        error_path.write_text(tb,encoding="utf-8")

def render_clip_id(clip_id: int, variant: str|None=None):
    s=load_settings()
    variant=variant or s.primary_variant
    if variant not in s.render_variants:
        raise ValueError(f"Unknown render variant: {variant}")
    clip=db.q("SELECT * FROM clips WHERE id=?",(clip_id,),one=True)
    if not clip: raise KeyError(clip_id)
    job=db.q("SELECT * FROM jobs WHERE id=?",(clip["job_id"],),one=True)
    source=Path(job["source_path"])
    key=_key(source)
    tx=json.loads((s.cache_path/key/"transcript.json").read_text(encoding="utf-8"))
    safe="".join(c if c.isalnum() or c in "-_" else "_" for c in clip["title"][:45]).strip("_") or f"clip_{clip_id}"
    out=s.output_path/f"{clip_id:04d}_{variant}_{safe}.mp4"
    db.exec_sql("UPDATE clips SET status='rendering' WHERE id=?",(clip_id,))
    try:
        result=render_clip(source,clip,tx.get("words",[]),out,s,variant=variant)
        quality=(evaluate_render(clip,tx.get("words",[]),result,str(clip.get("hook_text") or ""))
                 if s.quality_scoring_enabled else {"score":0.0})
        db.upsert_render(clip_id,variant,str(out),result["start"],result["end"],result["focus"],
                         quality_score=float(quality.get("score",0) or 0),quality=quality)
        best=None
        if s.best_variant_auto_select and s.quality_scoring_enabled:
            best=db.choose_best_render(clip_id)
        elif variant==s.primary_variant or not clip.get("output_path"):
            db.exec_sql("UPDATE clips SET output_path=?,best_variant=? WHERE id=?",(str(out),variant,clip_id))
        db.exec_sql("UPDATE clips SET status='rendered' WHERE id=?",(clip_id,))
        result["quality"]=quality
        result["best_variant"]=(best or {}).get("variant") if best else variant
        return result
    except Exception:
        db.exec_sql("UPDATE clips SET status='error' WHERE id=?",(clip_id,))
        raise

def render_all_variants(clip_id: int):
    s=load_settings()
    results=[]
    for variant in s.render_variants:
        results.append(render_clip_id(clip_id,variant))
    if s.best_variant_auto_select and s.quality_scoring_enabled:
        db.choose_best_render(clip_id)
    return results
