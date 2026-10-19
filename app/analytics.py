from __future__ import annotations

import argparse
import json
import math
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from . import db
from .config import ROOT, load_settings
from .publishing import (
    YOUTUBE_CLIENT,
    SECRETS,
    TIKTOK_TOKEN,
    INSTAGRAM_TOKEN,
    _graph_url,
    _instagram_credentials,
    _json_load,
    _tiktok_access_token,
)
from .secure_store import SecureStoreError, read_secure_json, write_secure_json

YOUTUBE_ANALYTICS_TOKEN = SECRETS / "youtube_analytics_token.json"
YOUTUBE_ANALYTICS_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
SNAPSHOT_PATH = ROOT / "app" / "static" / "analytics_snapshot.json"
_refresh_lock = threading.Lock()
_refresh_running = False
_last_attempt = 0.0


def ensure_schema() -> None:
    db.exec_sql("""
    CREATE TABLE IF NOT EXISTS analytics_snapshots (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      publish_job_id INTEGER NOT NULL,
      clip_id INTEGER NOT NULL,
      platform TEXT NOT NULL,
      platform_post_id TEXT NOT NULL DEFAULT '',
      captured_at REAL NOT NULL,
      views INTEGER NOT NULL DEFAULT 0,
      likes INTEGER NOT NULL DEFAULT 0,
      comments INTEGER NOT NULL DEFAULT 0,
      shares INTEGER NOT NULL DEFAULT 0,
      saves INTEGER NOT NULL DEFAULT 0,
      reach INTEGER NOT NULL DEFAULT 0,
      avg_view_duration REAL NOT NULL DEFAULT 0,
      avg_view_percentage REAL NOT NULL DEFAULT 0,
      followers_gained INTEGER NOT NULL DEFAULT 0,
      raw_score REAL NOT NULL DEFAULT 0,
      performance_score REAL NOT NULL DEFAULT 0,
      confidence REAL NOT NULL DEFAULT 0,
      metrics_json TEXT NOT NULL DEFAULT '{}',
      error TEXT NOT NULL DEFAULT '',
      FOREIGN KEY(publish_job_id) REFERENCES publish_queue(id),
      FOREIGN KEY(clip_id) REFERENCES clips(id)
    )
    """)
    db.exec_sql("CREATE INDEX IF NOT EXISTS idx_analytics_job_time ON analytics_snapshots(publish_job_id,captured_at)")
    db.exec_sql("CREATE INDEX IF NOT EXISTS idx_analytics_clip ON analytics_snapshots(clip_id,platform,captured_at)")


def _youtube_analytics_credentials():
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except Exception as e:
        raise RuntimeError("Google OAuth libraries are not installed. Reinstall Postal AutoClip.") from e
    try:
        token = read_secure_json(YOUTUBE_ANALYTICS_TOKEN)
    except SecureStoreError as e:
        raise RuntimeError(f"YouTube analytics credential could not be opened: {e}") from e
    if not token:
        raise RuntimeError("YouTube analytics is not connected. Use Accounts to connect YouTube.")
    creds = Credentials.from_authorized_user_info(token, YOUTUBE_ANALYTICS_SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        write_secure_json(YOUTUBE_ANALYTICS_TOKEN, json.loads(creds.to_json()))
    if not creds.valid:
        raise RuntimeError("YouTube analytics authorization is invalid. Reconnect YouTube in Accounts.")
    return creds


def connect_youtube_analytics() -> dict[str, Any]:
    SECRETS.mkdir(parents=True, exist_ok=True)
    try:
        client = read_secure_json(YOUTUBE_CLIENT)
    except SecureStoreError as e:
        raise RuntimeError(f"Google OAuth client could not be opened: {e}") from e
    if not client:
        raise RuntimeError("Set up YouTube publishing OAuth in Accounts first.")
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except Exception as e:
        raise RuntimeError("Google OAuth libraries are not installed. Reinstall Postal AutoClip.") from e
    flow = InstalledAppFlow.from_client_config(client, YOUTUBE_ANALYTICS_SCOPES)
    creds = flow.run_local_server(port=8766, prompt="consent", access_type="offline", open_browser=True)
    write_secure_json(YOUTUBE_ANALYTICS_TOKEN, json.loads(creds.to_json()))
    return {"ok": True, "token_path": str(YOUTUBE_ANALYTICS_TOKEN)}


def youtube_analytics_status() -> dict[str, Any]:
    return {
        "ready": YOUTUBE_CLIENT.exists() and YOUTUBE_ANALYTICS_TOKEN.exists(),
        "client_secret_present": YOUTUBE_CLIENT.exists(),
        "analytics_token_present": YOUTUBE_ANALYTICS_TOKEN.exists(),
        "token_path": str(YOUTUBE_ANALYTICS_TOKEN),
    }


def _date_range(published_at: float) -> tuple[str, str]:
    start = datetime.fromtimestamp(max(1.0, published_at - 86400), tz=timezone.utc).date().isoformat()
    end = datetime.now(timezone.utc).date().isoformat()
    return start, end


def collect_youtube(row: dict[str, Any]) -> dict[str, Any]:
    try:
        from googleapiclient.discovery import build
    except Exception as e:
        raise RuntimeError("Google API client is not installed. Reinstall Postal AutoClip.") from e
    video_id = str(row.get("platform_post_id") or "").strip()
    if not video_id:
        raise RuntimeError("YouTube video id is missing")
    creds = _youtube_analytics_credentials()
    service = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    start, end = _date_range(float(row.get("published_at") or row.get("scheduled_for") or time.time()))
    metrics = "views,engagedViews,likes,comments,shares,averageViewDuration,averageViewPercentage,subscribersGained"
    try:
        report = service.reports().query(ids="channel==MINE", startDate=start, endDate=end, metrics=metrics, filters=f"video=={video_id}").execute()
    except Exception:
        metrics = "views,likes,comments,shares,averageViewDuration,averageViewPercentage,subscribersGained"
        report = service.reports().query(ids="channel==MINE", startDate=start, endDate=end, metrics=metrics, filters=f"video=={video_id}").execute()
    headers = [x.get("name") for x in report.get("columnHeaders", [])]
    values = (report.get("rows") or [[0] * len(headers)])[0]
    data = dict(zip(headers, values))
    return {
        "views": int(data.get("views") or 0), "engaged_views": int(data.get("engagedViews") or 0),
        "likes": int(data.get("likes") or 0), "comments": int(data.get("comments") or 0),
        "shares": int(data.get("shares") or 0), "saves": 0, "reach": 0,
        "avg_view_duration": float(data.get("averageViewDuration") or 0),
        "avg_view_percentage": float(data.get("averageViewPercentage") or 0),
        "followers_gained": int(data.get("subscribersGained") or 0), "raw": report,
    }


def _extract_tiktok_post_id(row: dict[str, Any]) -> str:
    direct = str(row.get("platform_post_id") or "").strip()
    if direct.isdigit(): return direct
    try: raw = json.loads(row.get("result_json") or "{}")
    except Exception: raw = {}
    stack = [raw]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k == "publicaly_available_post_id" and isinstance(v, list) and v: return str(v[0])
                stack.append(v)
        elif isinstance(cur, list): stack.extend(cur)
    return ""


def collect_tiktok(row: dict[str, Any]) -> dict[str, Any]:
    token = _tiktok_access_token()
    if not token: raise RuntimeError("TikTok token missing")
    video_id = _extract_tiktok_post_id(row)
    if not video_id: raise RuntimeError("TikTok public post id is not available yet; public analytics cannot be matched safely")
    fields = "id,title,view_count,like_count,comment_count,share_count"
    with httpx.Client(timeout=30) as client:
        r = client.post(f"https://open.tiktokapis.com/v2/video/query/?fields={fields}", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, json={"filters": {"video_ids": [video_id]}})
        r.raise_for_status(); payload = r.json()
    err = payload.get("error") or {}
    if err.get("code") not in {None, "ok", 0}: raise RuntimeError(f"TikTok analytics error: {err.get('code')}: {err.get('message')}")
    videos = (payload.get("data") or {}).get("videos") or []
    if not videos: raise RuntimeError("TikTok returned no video analytics. Ensure the token includes video.list.")
    v = videos[0]
    return {"views": int(v.get("view_count") or 0), "likes": int(v.get("like_count") or 0), "comments": int(v.get("comment_count") or 0), "shares": int(v.get("share_count") or 0), "saves": 0, "reach": 0, "avg_view_duration": 0.0, "avg_view_percentage": 0.0, "followers_gained": 0, "raw": payload}


def _insight_value(item: dict[str, Any]) -> float:
    vals = item.get("values") or []
    if vals and isinstance(vals[0], dict): return float(vals[0].get("value") or 0)
    return float(item.get("value") or 0)


def collect_instagram(row: dict[str, Any]) -> dict[str, Any]:
    token, _ = _instagram_credentials()
    if not token: raise RuntimeError("Instagram token missing")
    media_id = str(row.get("platform_post_id") or "").strip()
    if not media_id: raise RuntimeError("Instagram media id is missing")
    metrics: dict[str, float] = {}
    wanted = ["views", "reach", "likes", "comments", "shares", "saved", "total_interactions", "ig_reels_avg_watch_time"]
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=30) as client:
        for name in wanted:
            try:
                r = client.get(_graph_url(f"{media_id}/insights"), headers=headers, params={"metric": name})
                if not r.is_success: continue
                for item in (r.json() or {}).get("data", []): metrics[str(item.get("name") or name)] = _insight_value(item)
            except Exception: continue
        try:
            meta = client.get(_graph_url(media_id), headers=headers, params={"fields": "like_count,comments_count,permalink"})
            if meta.is_success:
                md = meta.json() or {}; metrics.setdefault("likes", float(md.get("like_count") or 0)); metrics.setdefault("comments", float(md.get("comments_count") or 0))
        except Exception: pass
    if not metrics: raise RuntimeError("Instagram returned no Reel insights for this media/account")
    avg_watch_ms = float(metrics.get("ig_reels_avg_watch_time") or 0)
    return {"views": int(metrics.get("views") or 0), "likes": int(metrics.get("likes") or 0), "comments": int(metrics.get("comments") or 0), "shares": int(metrics.get("shares") or 0), "saves": int(metrics.get("saved") or 0), "reach": int(metrics.get("reach") or 0), "avg_view_duration": avg_watch_ms / 1000.0 if avg_watch_ms > 0 else 0.0, "avg_view_percentage": 0.0, "followers_gained": 0, "raw": metrics}


def _raw_score(m: dict[str, Any]) -> tuple[float, float]:
    views = max(0, int(m.get("views") or 0)); likes = max(0, int(m.get("likes") or 0)); comments = max(0, int(m.get("comments") or 0)); shares = max(0, int(m.get("shares") or 0)); saves = max(0, int(m.get("saves") or 0)); avg_pct = max(0.0, float(m.get("avg_view_percentage") or 0))
    view_norm = min(1.0, math.log10(views + 1) / 5.0); engagement_rate = (likes + 2 * comments + 3 * shares + 2 * saves) / max(views, 1); engage_norm = min(1.0, engagement_rate / 0.08)
    if avg_pct > 0:
        retain_norm = min(1.0, avg_pct / 100.0); score = 100.0 * (0.50 * view_norm + 0.30 * engage_norm + 0.20 * retain_norm); confidence = 1.0
    else:
        score = 100.0 * (0.625 * view_norm + 0.375 * engage_norm); confidence = 0.78
    return round(score, 2), confidence


def _latest_rows(platform: str | None = None) -> list[dict[str, Any]]:
    where = " AND a.platform=?" if platform else ""; args: tuple[Any, ...] = (platform,) if platform else ()
    return db.q(f"""SELECT a.*,q.title AS post_title,c.title AS clip_title,c.event_type,c.features_json,q.published_at,q.platform_url FROM analytics_snapshots a JOIN publish_queue q ON q.id=a.publish_job_id JOIN clips c ON c.id=a.clip_id WHERE a.id=(SELECT aa.id FROM analytics_snapshots aa WHERE aa.publish_job_id=a.publish_job_id ORDER BY aa.captured_at DESC,aa.id DESC LIMIT 1) {where} ORDER BY a.captured_at DESC""", args)


def _recompute_relative_scores() -> None:
    for platform in ("youtube", "tiktok", "instagram"):
        rows = _latest_rows(platform); usable = [float(r.get("raw_score") or 0) for r in rows if not r.get("error")]
        if not usable: continue
        ordered = sorted(usable)
        for r in rows:
            if r.get("error"): continue
            raw = float(r.get("raw_score") or 0)
            score = 0.45 * raw + 0.55 * (sum(1 for x in ordered if x <= raw) / len(ordered)) * 100.0 if len(ordered) >= 5 else raw
            db.exec_sql("UPDATE analytics_snapshots SET performance_score=? WHERE id=?", (round(score, 2), int(r["id"])))


def _store_snapshot(row: dict[str, Any], metrics: dict[str, Any] | None, error: str = "") -> None:
    metrics = metrics or {}; raw_score, confidence = _raw_score(metrics) if not error else (0.0, 0.0)
    db.exec_sql("""INSERT INTO analytics_snapshots(publish_job_id,clip_id,platform,platform_post_id,captured_at,views,likes,comments,shares,saves,reach,avg_view_duration,avg_view_percentage,followers_gained,raw_score,performance_score,confidence,metrics_json,error) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
        int(row["id"]), int(row["clip_id"]), str(row["platform"]), str(row.get("platform_post_id") or ""), time.time(), int(metrics.get("views") or 0), int(metrics.get("likes") or 0), int(metrics.get("comments") or 0), int(metrics.get("shares") or 0), int(metrics.get("saves") or 0), int(metrics.get("reach") or 0), float(metrics.get("avg_view_duration") or 0), float(metrics.get("avg_view_percentage") or 0), int(metrics.get("followers_gained") or 0), raw_score, raw_score, confidence, json.dumps(metrics.get("raw") or metrics, default=str)[:30000], error[:2000]))


def collect_all(force: bool = False) -> dict[str, Any]:
    ensure_schema(); s = load_settings(); cutoff = time.time() - max(1, int(s.analytics_history_days)) * 86400
    rows = db.q("SELECT * FROM publish_queue WHERE status='published' AND published_at>=? ORDER BY published_at DESC,id DESC", (cutoff,))
    collected = 0; errors = []
    for row in rows:
        age_hours = (time.time() - float(row.get("published_at") or 0)) / 3600.0
        if not force and age_hours < float(s.analytics_collection_min_age_hours): continue
        try:
            if row["platform"] == "youtube": metrics = collect_youtube(row)
            elif row["platform"] == "tiktok": metrics = collect_tiktok(row)
            elif row["platform"] == "instagram": metrics = collect_instagram(row)
            else: continue
            _store_snapshot(row, metrics); collected += 1
        except Exception as e:
            msg = f"{row['platform']} job {row['id']}: {type(e).__name__}: {e}"; errors.append(msg); _store_snapshot(row, None, msg)
    _recompute_relative_scores(); snapshot = build_summary(errors=errors); SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    return {"collected": collected, "errors": errors, "summary": snapshot}


def build_summary(errors: list[str] | None = None) -> dict[str, Any]:
    ensure_schema(); rows = _latest_rows(); posts = []; by_platform: dict[str, list[dict[str, Any]]] = {}; by_event: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        if r.get("error"): continue
        posts.append({"publish_job_id": r["publish_job_id"], "clip_id": r["clip_id"], "platform": r["platform"], "title": r.get("post_title") or r.get("clip_title") or "", "event_type": r.get("event_type") or "speech", "views": r["views"], "likes": r["likes"], "comments": r["comments"], "shares": r["shares"], "saves": r["saves"], "reach": r["reach"], "avg_view_duration": r["avg_view_duration"], "avg_view_percentage": r["avg_view_percentage"], "performance_score": r["performance_score"], "confidence": r["confidence"], "url": r.get("platform_url") or "", "captured_at": r["captured_at"]})
        by_platform.setdefault(r["platform"], []).append(r); by_event.setdefault(r.get("event_type") or "speech", []).append(r)
    platforms = {p: {"posts": len(xs), "views": sum(int(x.get("views") or 0) for x in xs), "avg_score": round(sum(float(x.get("performance_score") or 0) for x in xs) / len(xs), 1), "shares": sum(int(x.get("shares") or 0) for x in xs)} for p, xs in by_platform.items()}
    events = [{"event_type": event_type, "posts": len(xs), "avg_score": round(sum(float(x.get("performance_score") or 0) for x in xs) / len(xs), 1), "views": sum(int(x.get("views") or 0) for x in xs)} for event_type, xs in by_event.items()]; events.sort(key=lambda x: (x["avg_score"], x["views"]), reverse=True)
    recommendations = []
    if events: recommendations.append(f"Audience signal currently favors {events[0]['event_type']} clips (avg score {events[0]['avg_score']}).")
    for p, stats in sorted(platforms.items(), key=lambda kv: kv[1]["avg_score"], reverse=True): recommendations.append(f"{p.title()}: {stats['posts']} measured posts, {stats['views']:,} total views, avg performance {stats['avg_score']}.")
    if not posts: recommendations.append("No mature published posts have analytics yet. Keep cross-posting strong clips and let AutoClip build a baseline.")
    return {"version": "0.9.0", "generated_at": time.time(), "youtube_analytics": youtube_analytics_status(), "platforms": platforms, "event_types": events, "posts": posts[:100], "recommendations": recommendations, "errors": (errors or [])[:30]}


def _background_refresh(force: bool) -> None:
    global _refresh_running, _last_attempt
    try: _last_attempt = time.time(); collect_all(force=force)
    finally:
        with _refresh_lock: _refresh_running = False


def maybe_refresh_analytics(force: bool = False) -> bool:
    global _refresh_running
    s = load_settings()
    if not s.analytics_enabled: return False
    interval = max(0.25, float(s.analytics_refresh_hours)) * 3600.0
    if not force and time.time() - _last_attempt < interval: return False
    with _refresh_lock:
        if _refresh_running: return False
        _refresh_running = True
    threading.Thread(target=_background_refresh, args=(force,), daemon=True, name="PostalAnalytics").start(); return True


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Postal AutoClip analytics helper"); parser.add_argument("--connect-youtube", action="store_true"); parser.add_argument("--refresh", action="store_true"); parser.add_argument("--summary", action="store_true"); args = parser.parse_args()
    if args.connect_youtube: print(json.dumps(connect_youtube_analytics(), indent=2)); return 0
    if args.refresh: print(json.dumps(collect_all(force=True), indent=2, default=str)); return 0
    if args.summary: print(json.dumps(build_summary(), indent=2, default=str)); return 0
    parser.print_help(); return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
