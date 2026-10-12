from __future__ import annotations

import re
import time
from datetime import datetime, timedelta
from typing import Any

from . import db
from .config import load_settings
from .covers import select_cover_ms
from .learning import platform_fit_score
from .platform_insights import choose_platform_variant

VALID_PLATFORMS={"youtube","tiktok","instagram"}


def _tokens(text: str) -> set[str]:
    return {x for x in re.findall(r"[a-z0-9']+",(text or "").lower()) if len(x)>2}


def similarity(a: str,b: str) -> float:
    aa,bb=_tokens(a),_tokens(b)
    if not aa or not bb: return 0.0
    return len(aa&bb)/max(1,len(aa|bb))


def _clip_text(row: dict[str,Any]) -> str:
    return " ".join(str(row.get(k) or "") for k in ("title","hook_text","transcript"))[:1800]


def _candidate_rows() -> list[dict[str,Any]]:
    return db.q("""SELECT c.*,r.id AS render_id,r.variant,r.quality_score,r.render_start,r.render_end,r.output_path
                   FROM clips c JOIN renders r ON r.clip_id=c.id
                   WHERE c.status IN ('approved','favorite')
                     AND r.id=(SELECT rr.id FROM renders rr WHERE rr.clip_id=c.id
                               ORDER BY rr.is_best DESC,rr.quality_score DESC,rr.id LIMIT 1)
                   ORDER BY CASE WHEN c.status='favorite' THEN 0 ELSE 1 END,
                            r.quality_score DESC,c.score DESC,c.id DESC""")


def _recent_rows(platform: str,days: int) -> list[dict[str,Any]]:
    cutoff=time.time()-max(1,int(days))*86400
    return db.q("""SELECT q.clip_id,q.platform,q.status,c.title,c.hook_text,c.transcript,c.event_type
                   FROM publish_queue q JOIN clips c ON c.id=q.clip_id
                   WHERE q.platform=? AND q.status IN ('queued','publishing','submitted','published')
                     AND (q.scheduled_for>=? OR q.published_at>=?)""",(platform,cutoff,cutoff))


def _local_slots(start_epoch: float,days:int,slots:list[str]) -> list[float]:
    base=datetime.fromtimestamp(float(start_epoch)).astimezone(); tz=base.tzinfo
    out=[]
    for d in range(max(1,int(days))):
        date=(base+timedelta(days=d)).date()
        for raw in slots:
            try:
                hh,mm=(int(x) for x in raw.split(":",1))
                ts=datetime(date.year,date.month,date.day,hh,mm,tzinfo=tz).timestamp()
                if ts>=start_epoch-1: out.append(ts)
            except Exception:
                continue
    return sorted(out)


def _privacy(platform:str,s) -> str:
    if platform=="youtube": return s.youtube_default_privacy
    if platform=="tiktok": return s.tiktok_default_privacy
    return s.instagram_default_privacy


def _scheduled_time(base_time:float,offset_minutes:float,sync_same_date:bool) -> float:
    proposed=base_time+60*float(offset_minutes)
    if not sync_same_date:
        return proposed
    base_dt=datetime.fromtimestamp(base_time).astimezone()
    proposed_dt=datetime.fromtimestamp(proposed).astimezone()
    return proposed if proposed_dt.date()==base_dt.date() else base_time


def _render_for_platform(clip_id:int,platform:str,fallback:dict[str,Any]) -> dict[str,Any]:
    try:
        renders=db.clip_renders(clip_id)
    except Exception:
        renders=[]
    if not renders:
        return fallback
    available=[str(r.get("variant") or "") for r in renders]
    preferred=choose_platform_variant(platform,available,str(fallback.get("variant") or ""))
    return next((r for r in renders if str(r.get("variant") or "")==preferred),fallback)


def build_week_plan(platforms:list[str],start_epoch:float|None=None,days:int=7,max_clips:int=5,
                    slots:list[str]|None=None) -> dict[str,Any]:
    s=load_settings(); start_epoch=float(start_epoch or time.time())
    platforms=[p.lower() for p in platforms if p.lower() in VALID_PLATFORMS]
    if not platforms: platforms=["youtube","tiktok","instagram"]
    slots=slots or list(s.distribution_slots)
    times=_local_slots(start_epoch,days,slots)
    if not times: times=[start_epoch+i*86400 for i in range(max(1,int(max_clips)))]

    candidates=_candidate_rows(); selected=[]; skipped=[]; last_event=""
    recent={p:_recent_rows(p,s.duplicate_window_days) for p in platforms}

    while candidates and len(selected)<max(1,int(max_clips)):
        best_index=None; best_platforms=[]
        for i,row in enumerate(candidates):
            text=_clip_text(row)
            if any(similarity(text,_clip_text(x))>=float(s.duplicate_similarity_threshold) for x in selected):
                skipped.append({"clip_id":row["id"],"reason":"too similar to another clip in this plan"}); continue
            eligible=[]
            for p in platforms:
                old_rows=recent[p]
                if any(int(x.get("clip_id") or 0)==int(row["id"]) for x in old_rows):
                    skipped.append({"clip_id":row["id"],"platform":p,"reason":"already queued/published recently"}); continue
                if any(similarity(text,_clip_text(old))>=float(s.duplicate_similarity_threshold) for old in old_rows):
                    skipped.append({"clip_id":row["id"],"platform":p,"reason":"too similar to recent content"}); continue
                eligible.append(p)
            if not eligible: continue
            if last_event and str(row.get("event_type") or "")==last_event:
                if any(str(x.get("event_type") or "")!=last_event for x in candidates[i+1:]):
                    continue
            best_index=i; best_platforms=eligible; break
        if best_index is None: break
        row=candidates.pop(best_index); row["_eligible_platforms"]=best_platforms
        selected.append(row); last_event=str(row.get("event_type") or "")

    plan=[]; offsets=s.platform_offsets_minutes
    for idx,row in enumerate(selected):
        base_time=times[min(idx,len(times)-1)]
        fallback_render={
            "id":row.get("render_id"),"variant":row.get("variant"),"quality_score":row.get("quality_score"),
            "render_start":row.get("render_start",0),"render_end":row.get("render_end",0),"output_path":row.get("output_path","")
        }
        for platform in row.get("_eligible_platforms",platforms):
            chosen=_render_for_platform(int(row["id"]),platform,fallback_render)
            cover_ms=select_cover_ms(row,chosen)
            fit=(platform_fit_score(row.get("features_json") or "{}",float(row.get("score") or 0),platform)
                 if s.platform_fit_enabled else float(row.get("score") or 0))
            plan.append({
                "clip_id":int(row["id"]),"render_id":int(chosen.get("id") or row["render_id"]),"platform":platform,
                "scheduled_for":_scheduled_time(base_time,float(offsets.get(platform,0)),bool(s.synchronized_crosspost_enabled)),
                "shared_calendar_slot":base_time,
                "title":row.get("title") or "","caption":row.get("description") or "","hashtags":row.get("hashtags") or "",
                "privacy":_privacy(platform,s),"variant":chosen.get("variant") or row.get("variant") or "",
                "quality_score":float(chosen.get("quality_score") or 0),"platform_fit_score":fit,
                "event_type":row.get("event_type") or "","hook_text":row.get("hook_text") or "",
                "options":{"cover_ms":cover_ms,"thumb_offset":cover_ms}
            })
    return {"plan":plan,"selected_clips":[int(x["id"]) for x in selected],"skipped":skipped,
            "platforms":platforms,"days":int(days),"slots":slots,
            "calendar_mode":"synchronized" if s.synchronized_crosspost_enabled else "independent",
            "same_clip_same_date":bool(s.synchronized_crosspost_enabled)}


def queue_week_plan(plan:list[dict[str,Any]]) -> list[int]:
    ids=[]
    for item in plan:
        ids.append(db.add_publish_job(int(item["clip_id"]),int(item["render_id"]),str(item["platform"]),
            float(item["scheduled_for"]),str(item.get("title") or ""),str(item.get("caption") or ""),
            str(item.get("hashtags") or ""),str(item.get("privacy") or "private"),
            item.get("options") if isinstance(item.get("options"),dict) else {}))
    return ids
