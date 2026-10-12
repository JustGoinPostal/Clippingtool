from __future__ import annotations

from typing import Any

from . import db
from .config import load_settings
from .learning import platform_audience_profiles

PLATFORMS=("youtube","tiktok","instagram")


def _latest_rows(platform: str) -> list[dict[str,Any]]:
    try:
        return db.q("""
            SELECT a.platform,a.performance_score,a.views,a.error,r.variant,c.event_type
            FROM analytics_snapshots a
            JOIN publish_queue q ON q.id=a.publish_job_id
            JOIN renders r ON r.id=q.render_id
            JOIN clips c ON c.id=a.clip_id
            WHERE a.platform=? AND a.error=''
              AND a.id=(SELECT aa.id FROM analytics_snapshots aa
                        WHERE aa.publish_job_id=a.publish_job_id
                        ORDER BY aa.captured_at DESC,aa.id DESC LIMIT 1)
        """,(platform,))
    except Exception:
        return []


def variant_stats(platform: str) -> dict[str,dict[str,float]]:
    groups: dict[str,list[dict[str,Any]]]={}
    for row in _latest_rows(platform):
        groups.setdefault(str(row.get("variant") or ""),[]).append(row)
    out={}
    for variant,rows in groups.items():
        if not variant: continue
        out[variant]={
            "posts":len(rows),
            "avg_score":round(sum(float(x.get("performance_score") or 0) for x in rows)/len(rows),1),
            "views":sum(int(x.get("views") or 0) for x in rows),
        }
    return out


def event_stats(platform: str) -> dict[str,dict[str,float]]:
    groups: dict[str,list[dict[str,Any]]]={}
    for row in _latest_rows(platform):
        groups.setdefault(str(row.get("event_type") or "speech"),[]).append(row)
    out={}
    for event_type,rows in groups.items():
        out[event_type]={
            "posts":len(rows),
            "avg_score":round(sum(float(x.get("performance_score") or 0) for x in rows)/len(rows),1),
            "views":sum(int(x.get("views") or 0) for x in rows),
        }
    return out


def choose_platform_variant(platform: str, available: list[str], fallback: str) -> str:
    """Choose a render length only after enough platform-specific evidence exists."""
    stats=variant_stats(platform)
    min_samples=max(2,int(getattr(load_settings(),"platform_variant_min_samples",3)))
    candidates=[
        (name,data) for name,data in stats.items()
        if name in available and int(data.get("posts") or 0)>=min_samples
    ]
    if not candidates: return fallback
    candidates.sort(key=lambda x:(float(x[1].get("avg_score") or 0),int(x[1].get("views") or 0)),reverse=True)
    return candidates[0][0]


def platform_models() -> dict[str,dict[str,Any]]:
    profiles=platform_audience_profiles()
    out={}
    for platform in PLATFORMS:
        out[platform]={
            "audience":profiles.get(platform,{"samples":0,"weights":{}}),
            "variants":variant_stats(platform),
            "event_types":event_stats(platform),
        }
    return out
