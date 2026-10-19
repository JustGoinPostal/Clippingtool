from __future__ import annotations
import threading, time
from pathlib import Path
from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from .config import ROOT, load_settings, save_settings
from . import db
from .watcher import scan_once, start_watcher
from .pipeline import process_job, render_clip_id, render_all_variants, rerun_render_qa
from .learning import learned_profile, audience_profile
from .hooks import generate_hook
from .covers import ensure_cover
from .distribution import build_week_plan, queue_week_plan
from .publishing import (
    platform_status, connect_youtube, tiktok_creator_info, queue_post,
    process_due_posts, start_publish_worker,
)
from .analytics import build_summary, collect_all, connect_youtube_analytics, youtube_analytics_status
from .account_server import start_account_server
from .debug_log import build_debug_report, debug_filename
from .file_picker import pick_recording

app=FastAPI(title="Postal AutoClip",version="0.9.0")
app.mount("/static",StaticFiles(directory=ROOT/"app"/"static"),name="static")

@app.on_event("startup")
def startup():
    db.init_db(); s=load_settings(); start_watcher(); start_account_server()
    if s.publishing_enabled: start_publish_worker()

@app.get("/",response_class=HTMLResponse)
def home(): return (ROOT/"app"/"static"/"index.html").read_text(encoding="utf-8")

@app.get("/api/status")
def status():
    s=load_settings()
    return {"ok":True,"version":"0.9.0","watch_folder":str(s.watch_path),"output_folder":str(s.output_path),
            "render_variants":s.render_variants,"primary_variant":s.primary_variant,"layout":s.layout,
            "auto_hook_enabled":s.auto_hook_enabled,"dynamic_zoom_enabled":s.dynamic_zoom_enabled,
            "quality_scoring_enabled":s.quality_scoring_enabled,"best_variant_auto_select":s.best_variant_auto_select,
            "publishing_enabled":s.publishing_enabled,"auto_cover_enabled":s.auto_cover_enabled,
            "distribution_slots":s.distribution_slots,"analytics_enabled":s.analytics_enabled,
            "analytics_refresh_hours":s.analytics_refresh_hours}

@app.get("/api/jobs")
def jobs(): return db.q("SELECT * FROM jobs ORDER BY id DESC LIMIT 100")

@app.get("/api/debug/log")
def debug_log(job_id:int|None=None):
    if job_id is not None and not db.q("SELECT id FROM jobs WHERE id=?",(job_id,),one=True):
        raise HTTPException(404,"Job not found")
    text=build_debug_report(job_id)
    headers={"Content-Disposition":f'attachment; filename="{debug_filename(job_id)}"'}
    return PlainTextResponse(text,headers=headers,media_type="text/plain; charset=utf-8")

@app.post("/api/browse-recording")
def browse_recording(payload:dict=Body(default={})):
    try:
        path=pick_recording(str(payload.get("initial_dir") or ""))
        return {"path":path,"cancelled":not bool(path)}
    except Exception as e:
        raise HTTPException(500,f"{type(e).__name__}: {e}")

@app.get("/api/clips")
def clips(job_id:int|None=None):
    base="""SELECT clips.*,jobs.source_path,jobs.duration AS job_duration,
      (SELECT group_concat(variant, ',') FROM renders WHERE renders.clip_id=clips.id) AS rendered_variants
      FROM clips JOIN jobs ON jobs.id=clips.job_id"""
    if job_id is None: return db.q(base+" WHERE clips.status!='archived' ORDER BY score DESC LIMIT 250")
    return db.q(base+" WHERE clips.job_id=? AND clips.status!='archived' ORDER BY score DESC",(job_id,))

@app.post("/api/clips/archive-all")
def archive_all_clips():
    row=db.q("SELECT COUNT(*) AS n FROM clips WHERE status!='archived'",one=True) or {"n":0}
    db.exec_sql("UPDATE clips SET status='archived' WHERE status!='archived'")
    return {"ok":True,"archived":int(row.get("n") or 0)}

@app.get("/api/clips/{clip_id}")
def clip_detail(clip_id:int):
    row=db.q("""SELECT clips.*,jobs.source_path,jobs.duration AS job_duration
                FROM clips JOIN jobs ON jobs.id=clips.job_id WHERE clips.id=?""",(clip_id,),one=True)
    if not row: raise HTTPException(404,"Clip not found")
    row["renders"]=db.clip_renders(clip_id); return row

@app.post("/api/clips/{clip_id}/archive")
def archive_clip(clip_id:int):
    row=db.q("SELECT id,status FROM clips WHERE id=?",(clip_id,),one=True)
    if not row: raise HTTPException(404,"Clip not found")
    db.exec_sql("UPDATE clips SET status='archived' WHERE id=?",(clip_id,))
    return {"ok":True,"clip_id":clip_id,"previous_status":row.get("status") or "candidate"}

@app.patch("/api/clips/{clip_id}")
def edit_clip(clip_id:int,payload:dict=Body(...)):
    row=db.q("""SELECT clips.*,jobs.duration AS job_duration FROM clips
                JOIN jobs ON jobs.id=clips.job_id WHERE clips.id=?""",(clip_id,),one=True)
    if not row: raise HTTPException(404,"Clip not found")
    start=float(payload.get("start",row["start"])); end=float(payload.get("end",row["end"]))
    total=max(0.0,float(row.get("job_duration") or 0)); start=max(0.0,start); end=min(total,end) if total else end
    if end-start < 0.75: raise HTTPException(400,"Clip must be at least 0.75 seconds")
    if start>=end: raise HTTPException(400,"Start must be before end")
    hook_text=str(payload.get("hook_text",row.get("hook_text") or "")).strip()[:72]
    changed=(abs(start-float(row["start"]))>0.001 or abs(end-float(row["end"]))>0.001 or hook_text!=str(row.get("hook_text") or ""))
    if changed:
        db.exec_sql("UPDATE clips SET start=?,end=?,hook_text=?,status='candidate',output_path='',best_variant='' WHERE id=?",
                    (start,end,hook_text,clip_id))
        db.exec_sql("DELETE FROM publish_queue WHERE clip_id=? AND status IN ('queued','failed')",(clip_id,))
        db.exec_sql("DELETE FROM renders WHERE clip_id=?",(clip_id,))
    return {"ok":True,"clip_id":clip_id,"start":start,"end":end,"hook_text":hook_text,"renders_invalidated":changed}

@app.post("/api/clips/{clip_id}/hook/regenerate")
def regenerate_hook(clip_id:int):
    row=db.q("SELECT * FROM clips WHERE id=?",(clip_id,),one=True)
    if not row: raise HTTPException(404,"Clip not found")
    hook=generate_hook(row)
    db.exec_sql("UPDATE clips SET hook_text=?,status='candidate',output_path='',best_variant='' WHERE id=?",(hook,clip_id))
    db.exec_sql("DELETE FROM publish_queue WHERE clip_id=? AND status IN ('queued','failed')",(clip_id,))
    db.exec_sql("DELETE FROM renders WHERE clip_id=?",(clip_id,))
    return {"ok":True,"hook_text":hook}

@app.post("/api/ingest")
def ingest(payload:dict=Body(...)):
    p=Path(payload.get("path","")).expanduser()
    if not p.exists() or not p.is_file(): raise HTTPException(400,"File does not exist")
    job_id=db.add_job(str(p.resolve()))
    if payload.get("process",True): threading.Thread(target=process_job,args=(job_id,),daemon=True).start()
    return {"job_id":job_id}

@app.post("/api/scan")
def scan(): return {"job_ids":scan_once(auto=True)}

@app.post("/api/jobs/{job_id}/process")
def process(job_id:int):
    threading.Thread(target=process_job,args=(job_id,),daemon=True).start(); return {"started":True}

@app.post("/api/clips/{clip_id}/render")
def render(clip_id:int,payload:dict=Body(default={})):
    s=load_settings(); variant=str(payload.get("variant") or s.primary_variant)
    if variant not in s.render_variants: raise HTTPException(400,"Unknown render variant")
    threading.Thread(target=render_clip_id,args=(clip_id,variant),daemon=True).start(); return {"started":True,"variant":variant}

@app.post("/api/clips/{clip_id}/render-all")
def render_all(clip_id:int):
    threading.Thread(target=render_all_variants,args=(clip_id,),daemon=True).start()
    return {"started":True,"variants":list(load_settings().render_variants)}

@app.get("/api/clips/{clip_id}/renders")
def renders(clip_id:int): return db.clip_renders(clip_id)

@app.post("/api/renders/{render_id}/qa")
def render_qa_recheck(render_id:int):
    try:
        result=rerun_render_qa(render_id)
        return {"ok":True,**result}
    except KeyError:
        raise HTTPException(404,"Render not found")
    except Exception as e:
        raise HTTPException(500,f"Render QA failed: {type(e).__name__}: {e}")

@app.post("/api/clips/{clip_id}/decision")
def decision(clip_id:int,payload:dict=Body(...)):
    val=payload.get("status")
    if val not in {"approved","favorite","rejected","candidate"}: raise HTTPException(400,"Bad status")
    clip=db.q("SELECT id,features_json,event_type FROM clips WHERE id=?",(clip_id,),one=True)
    if not clip: raise HTTPException(404,"Clip not found")
    db.exec_sql("UPDATE clips SET status=? WHERE id=?",(val,clip_id))
    if val in {"approved","favorite","rejected"}:
        db.exec_sql("""INSERT INTO feedback(clip_id,status,features_json,event_type,updated_at) VALUES(?,?,?,?,CURRENT_TIMESTAMP)
          ON CONFLICT(clip_id) DO UPDATE SET status=excluded.status,features_json=excluded.features_json,
          event_type=excluded.event_type,updated_at=CURRENT_TIMESTAMP""",
          (clip_id,val,clip.get("features_json") or "{}",clip.get("event_type") or "speech"))
    else: db.exec_sql("DELETE FROM feedback WHERE clip_id=?",(clip_id,))
    return {"ok":True,"profile":learned_profile()}

@app.get("/api/profile")
def profile():
    counts=db.q("SELECT status,COUNT(*) n FROM feedback GROUP BY status")
    return {"weights":learned_profile(),"audience_weights":audience_profile(),
            "feedback":{x["status"]:x["n"] for x in counts}}

@app.post("/api/game-events")
def game_event(payload:dict=Body(...)):
    s=load_settings()
    if not s.runelite_bridge_enabled: raise HTTPException(403,"RuneLite bridge disabled")
    if s.runelite_bridge_token and str(payload.get("token",""))!=s.runelite_bridge_token: raise HTTPException(401,"Bad bridge token")
    event_id=db.add_game_event(float(payload.get("event_time") or time.time()),
        str(payload.get("event_type") or payload.get("type") or "runelite_event"),float(payload.get("confidence",1.0) or 1.0),
        payload.get("payload") if isinstance(payload.get("payload"),dict) else {},"runelite")
    return {"ok":True,"event_id":event_id}

@app.post("/api/game-events/batch")
def game_event_batch(payload:dict=Body(...)):
    s=load_settings()
    if not s.runelite_bridge_enabled: raise HTTPException(403,"RuneLite bridge disabled")
    if s.runelite_bridge_token and str(payload.get("token",""))!=s.runelite_bridge_token: raise HTTPException(401,"Bad bridge token")
    ids=[]
    for event in (payload.get("events") or [])[:250]:
        if not isinstance(event,dict): continue
        ids.append(db.add_game_event(float(event.get("event_time") or time.time()),
            str(event.get("event_type") or event.get("type") or "runelite_event"),float(event.get("confidence",1.0) or 1.0),
            event.get("payload") if isinstance(event.get("payload"),dict) else {},"runelite"))
    return {"ok":True,"count":len(ids)}

@app.get("/api/game-events/recent")
def game_events_recent(limit:int=25):
    return db.q("SELECT id,event_time,event_type,confidence,payload_json,source,created_at FROM game_events ORDER BY id DESC LIMIT ?",
                (max(1,min(250,limit)),))

def _default_privacy(platform:str) -> str:
    s=load_settings()
    if platform=="youtube": return s.youtube_default_privacy
    if platform=="tiktok": return s.tiktok_default_privacy
    return s.instagram_default_privacy

@app.get("/api/publishing/status")
def publishing_status(): return {"platforms":platform_status(),"queue":db.publish_jobs(100)}

@app.post("/api/publishing/youtube/connect")
def publishing_youtube_connect():
    def task():
        try: connect_youtube()
        except Exception as e: print(f"YouTube OAuth failed: {e}")
    threading.Thread(target=task,daemon=True,name="youtube-oauth").start()
    return {"started":True,"message":"OAuth browser flow started on this PC."}

@app.get("/api/publishing/tiktok/creator")
def publishing_tiktok_creator():
    try: return tiktok_creator_info()
    except Exception as e: raise HTTPException(400,f"{type(e).__name__}: {e}")

@app.post("/api/publishing/queue")
def publishing_queue(payload:dict=Body(...)):
    platform=str(payload.get("platform") or "").lower()
    if platform not in {"youtube","tiktok","instagram"}: raise HTTPException(400,"Unknown platform")
    render_id=int(payload.get("render_id") or 0)
    if not render_id: raise HTTPException(400,"render_id is required")
    scheduled=float(payload.get("scheduled_for") or time.time())
    try:
        job_id=queue_post(render_id,platform,scheduled,title=str(payload.get("title") or "")[:220],
            caption=str(payload.get("caption") or "")[:4000],hashtags=str(payload.get("hashtags") or "")[:1000],
            privacy=str(payload.get("privacy") or _default_privacy(platform)),
            options=payload.get("options") if isinstance(payload.get("options"),dict) else {})
    except KeyError: raise HTTPException(404,"Render not found")
    return {"ok":True,"publish_job_id":job_id,"scheduled_for":scheduled}

@app.post("/api/clips/{clip_id}/queue-best")
def publishing_queue_best(clip_id:int,payload:dict=Body(...)):
    clip=db.q("SELECT * FROM clips WHERE id=?",(clip_id,),one=True)
    if not clip: raise HTTPException(404,"Clip not found")
    render=db.q("SELECT * FROM renders WHERE clip_id=? ORDER BY is_best DESC,quality_score DESC,id LIMIT 1",(clip_id,),one=True)
    if not render: raise HTTPException(400,"Render this clip first")
    platform=str(payload.get("platform") or "youtube").lower()
    if platform not in {"youtube","tiktok","instagram"}: raise HTTPException(400,"Unknown platform")
    job_id=queue_post(int(render["id"]),platform,float(payload.get("scheduled_for") or time.time()),
        title=str(payload.get("title") or clip.get("title") or "")[:220],caption=str(payload.get("caption") or clip.get("description") or "")[:4000],
        hashtags=str(payload.get("hashtags") or clip.get("hashtags") or "")[:1000],privacy=str(payload.get("privacy") or _default_privacy(platform)),
        options=payload.get("options") if isinstance(payload.get("options"),dict) else {})
    return {"ok":True,"publish_job_id":job_id,"render_id":render["id"],"variant":render["variant"]}

@app.get("/api/publishing/queue")
def publishing_queue_list(limit:int=100): return db.publish_jobs(limit)

@app.delete("/api/publishing/queue/{job_id}")
def publishing_queue_delete(job_id:int):
    row=db.q("SELECT * FROM publish_queue WHERE id=?",(job_id,),one=True)
    if not row: raise HTTPException(404,"Publish job not found")
    if row["status"] in {"publishing","submitted","published"}: raise HTTPException(400,"Active/published jobs cannot be deleted here")
    db.exec_sql("DELETE FROM publish_queue WHERE id=?",(job_id,)); return {"ok":True}

@app.post("/api/publishing/queue/{job_id}/retry")
def publishing_queue_retry(job_id:int,payload:dict=Body(default={})):
    row=db.q("SELECT * FROM publish_queue WHERE id=?",(job_id,),one=True)
    if not row: raise HTTPException(404,"Publish job not found")
    if row["status"] in {"publishing","submitted","published"}:
        raise HTTPException(400,"Active/published jobs cannot be retried")
    if row["status"]=="needs_review" and not bool(payload.get("confirm_duplicate_risk",False)):
        raise HTTPException(409,"This upload ended in an uncertain state. Confirm duplicate risk before retrying.")
    db.update_publish_job(job_id,status="queued",scheduled_for=time.time(),next_attempt_at=0,error="")
    threading.Thread(target=process_due_posts,daemon=True).start(); return {"ok":True}

@app.post("/api/publishing/run-due")
def publishing_run_due():
    threading.Thread(target=process_due_posts,daemon=True).start(); return {"started":True}

@app.post("/api/distribution/plan")
def distribution_plan(payload:dict=Body(default={})):
    try:
        return build_week_plan(platforms=payload.get("platforms") or ["youtube","tiktok","instagram"],
            start_epoch=float(payload.get("start_epoch") or time.time()),days=int(payload.get("days") or 7),
            max_clips=int(payload.get("max_clips") or 5),slots=payload.get("slots") if isinstance(payload.get("slots"),list) else None)
    except Exception as e: raise HTTPException(400,f"{type(e).__name__}: {e}")

@app.post("/api/distribution/queue")
def distribution_queue(payload:dict=Body(default={})):
    try:
        result=build_week_plan(platforms=payload.get("platforms") or ["youtube","tiktok","instagram"],
            start_epoch=float(payload.get("start_epoch") or time.time()),days=int(payload.get("days") or 7),
            max_clips=int(payload.get("max_clips") or 5),slots=payload.get("slots") if isinstance(payload.get("slots"),list) else None)
        ids=queue_week_plan(result["plan"]); result["publish_job_ids"]=ids; result["queued_count"]=len(ids); return result
    except Exception as e: raise HTTPException(400,f"{type(e).__name__}: {e}")

@app.get("/api/analytics")
def analytics_summary():
    try: return build_summary()
    except Exception as e: raise HTTPException(500,f"{type(e).__name__}: {e}")

@app.post("/api/analytics/refresh")
def analytics_refresh():
    def task():
        try: collect_all(force=True)
        except Exception as e: print(f"Analytics refresh failed: {e}")
    threading.Thread(target=task,daemon=True,name="analytics-refresh").start()
    return {"started":True}

@app.get("/api/analytics/youtube/status")
def analytics_youtube_status(): return youtube_analytics_status()

@app.post("/api/analytics/youtube/connect")
def analytics_youtube_connect():
    def task():
        try: connect_youtube_analytics()
        except Exception as e: print(f"YouTube analytics OAuth failed: {e}")
    threading.Thread(target=task,daemon=True,name="youtube-analytics-oauth").start()
    return {"started":True,"message":"YouTube analytics OAuth browser flow started on this PC."}

@app.get("/api/settings")
def settings(): return load_settings().model_dump()

@app.put("/api/settings")
def settings_put(payload:dict=Body(...)): return save_settings(payload).model_dump()

@app.get("/source/{job_id}")
def source_media(job_id:int):
    row=db.q("SELECT source_path FROM jobs WHERE id=?",(job_id,),one=True)
    if not row: raise HTTPException(404,"Job not found")
    p=Path(row["source_path"])
    if not p.exists(): raise HTTPException(404,"Source file missing")
    return FileResponse(p,filename=p.name)

@app.get("/media/{clip_id}")
def media(clip_id:int):
    row=db.q("SELECT output_path FROM clips WHERE id=?",(clip_id,),one=True)
    if not row or not row["output_path"]: raise HTTPException(404)
    p=Path(row["output_path"])
    if not p.exists(): raise HTTPException(404)
    return FileResponse(p,media_type="video/mp4",filename=p.name)

@app.get("/media/render/{render_id}")
def render_media(render_id:int):
    row=db.q("SELECT output_path FROM renders WHERE id=?",(render_id,),one=True)
    if not row: raise HTTPException(404)
    p=Path(row["output_path"])
    if not p.exists(): raise HTTPException(404)
    return FileResponse(p,media_type="video/mp4",filename=p.name)

@app.get("/media/cover/{render_id}")
def render_cover(render_id:int):
    render=db.q("SELECT * FROM renders WHERE id=?",(render_id,),one=True)
    if not render: raise HTTPException(404,"Render not found")
    clip=db.q("SELECT * FROM clips WHERE id=?",(render["clip_id"],),one=True) or {}
    try: path,_=ensure_cover(render,clip)
    except Exception as e: raise HTTPException(500,f"Cover generation failed: {e}")
    return FileResponse(path,media_type="image/jpeg",filename=path.name)

def run():
    import uvicorn
    uvicorn.run("app.api:app",host="127.0.0.1",port=8787,reload=False)