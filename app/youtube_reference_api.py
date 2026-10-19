from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from .public_reference import canonical_youtube_url, normalize_reference, parse_youtube_video_id

API_BASE = "https://www.googleapis.com/youtube/v3"


def _api_key(explicit: str | None = None) -> str:
    key = str(explicit or os.environ.get("YOUTUBE_DATA_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("Set YOUTUBE_DATA_API_KEY to use official YouTube public-metadata discovery.")
    return key


def parse_iso8601_duration(value: str) -> float:
    # YouTube contentDetails.duration uses ISO 8601 durations such as PT1M2S or PT1H3M5S.
    m = re.fullmatch(r"P(?:(?P<days>\d+)D)?T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?", str(value or ""))
    if not m:
        return 0.0
    days = float(m.group("days") or 0)
    hours = float(m.group("hours") or 0)
    minutes = float(m.group("minutes") or 0)
    seconds = float(m.group("seconds") or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _selected_video_metadata(item: dict[str, Any], *, category: str = "other", source_mode: str = "metadata_only") -> dict[str, Any]:
    snippet = dict(item.get("snippet") or {})
    stats = dict(item.get("statistics") or {})
    details = dict(item.get("contentDetails") or {})
    status = dict(item.get("status") or {})
    video_id = parse_youtube_video_id(str(item.get("id") or ""))
    license_value = str(status.get("license") or "unknown")
    if source_mode == "creative_commons" and license_value != "creativeCommon":
        source_mode = "metadata_only"
    return normalize_reference({
        "video_id": video_id,
        "url": canonical_youtube_url(video_id),
        "source_mode": source_mode,
        "license": license_value,
        "rights_basis": "YouTube Data API status.license" if license_value == "creativeCommon" else "",
        "creator": snippet.get("channelTitle") or "",
        "title": snippet.get("title") or "",
        "published_at": snippet.get("publishedAt") or "",
        "observed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "category": category,
        "duration_seconds": parse_iso8601_duration(str(details.get("duration") or "")),
        "view_count": stats.get("viewCount"),
        "like_count": stats.get("likeCount"),
        "embeddable": status.get("embeddable"),
        "structural": {},
    })


def fetch_video_metadata(video_ids: list[str], *, api_key: str | None = None, category: str = "other") -> list[dict[str, Any]]:
    ids = [parse_youtube_video_id(x) for x in video_ids]
    if not ids:
        return []
    params = {
        "part": "snippet,contentDetails,statistics,status",
        "id": ",".join(ids[:50]),
        "key": _api_key(api_key),
    }
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        response = client.get(f"{API_BASE}/videos", params=params)
        response.raise_for_status()
        payload = response.json()
    return [_selected_video_metadata(dict(item), category=category) for item in payload.get("items") or []]


def search_creative_commons_osrs(query: str = "Old School RuneScape", *, api_key: str | None = None,
                                 max_results: int = 10, category: str = "other") -> list[dict[str, Any]]:
    limit = max(1, min(50, int(max_results)))
    params = {
        "part": "snippet",
        "q": str(query or "Old School RuneScape")[:200],
        "type": "video",
        "order": "viewCount",
        "videoLicense": "creativeCommon",
        "maxResults": limit,
        "key": _api_key(api_key),
    }
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        response = client.get(f"{API_BASE}/search", params=params)
        response.raise_for_status()
        items = response.json().get("items") or []
    ids = [str((item.get("id") or {}).get("videoId") or "") for item in items]
    ids = [x for x in ids if x]
    if not ids:
        return []
    rows = fetch_video_metadata(ids, api_key=api_key, category=category)
    out: list[dict[str, Any]] = []
    for row in rows:
        if row.get("license") != "creativeCommon":
            continue
        upgraded = dict(row)
        upgraded["source_mode"] = "creative_commons"
        upgraded["rights_basis"] = "YouTube Data API reports status.license=creativeCommon"
        out.append(normalize_reference(upgraded))
    return out
