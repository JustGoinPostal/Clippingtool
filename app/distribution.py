from __future__ import annotations

import re
import time
from datetime import datetime, timedelta
from typing import Any

from . import db
from .config import load_settings
from .covers import select_cover_ms

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


def _local_slots(start_epoch: float,days: int,slots: list[str]) -> list[float]:
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


def _privacy(platform: str,s) -> str:
    if platform=="youtube": return s.youtube_default_privacy
    if platform=="tiktok": return s.tiktok_default_privacy
    return s.instagram_default_privacy


def build_week_plan(platforms:list[str],start_epoch:float|None=None,days:int=7,max_clips:int=5,
                    slots:list[str]|None=None) -> dict[str,Any]:
    s=load_settings(); start_epoch=float(start_epoch or time.time())
    platforms=[p.lower() for p in platforms if p.lower() in VALID_PLATFORMS]
    if not platforms: platforms=["youtube"]
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
        render={"render_start":row.get("render_start",0),"render_end":row.get("render_end",0)}
        cover_ms=select_cover_ms(row,render)
        for platform in row.get("_eligible_platforms",platforms):
            plan.append({
                "clip_id":int(row["id"]),"render_id":int(row["render_id"]),"platform":platform,
                "scheduled_for":base_time+60*float(offsets.get(platform,0)),
                "title":row.get("title") or "","caption":row.get("description") or "","hashtags":row.get("hashtags") or "",
                "privacy":_privacy(platform,s),"variant":row.get("variant") or "",
                "quality_score":float(row.get("quality_score") or 0),"event_type":row.get("event_type") or "",
                "hook_text":row.get("hook_text") or "","options":{"cover_ms":cover_ms,"thumb_offset":cover_ms}
            })
    return {"plan":plan,"selected_clips":[int(x["id"]) for x in selected],"skipped":skipped,
            "platforms":platforms,"days":int(days),"slots":slots}


def queue_week_plan(plan:list[dict[str,Any]]) -> list[int]:
    ids=[]
    for item in plan:
        ids.append(db.add_publish_job(int(item["clip_id"]),int(item["render_id"]),str(item["platform"]),
            float(item["scheduled_for"]),str(item.get("title") or ""),str(item.get("caption") or ""),
            str(item.get("hashtags") or ""),str(item.get("privacy") or "private"),
            item.get("options") if isinstance(item.get("options"),dict) else {}))
    return ids
