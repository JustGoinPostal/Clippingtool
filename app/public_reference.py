from __future__ import annotations

import json
import re
import statistics
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .config import ROOT

CATALOG_PATH = ROOT / "data" / "public_reference_catalog.json"

SOURCE_MODES = {"metadata_only", "creative_commons", "permission"}
CATEGORIES = {
    "pvp", "raid", "pvm", "rng", "achievement", "reaction", "personality", "guide", "other"
}
STRUCTURAL_MODES = {"creative_commons", "permission"}


def parse_youtube_video_id(value: str) -> str:
    raw = str(value or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", raw):
        return raw
    try:
        u = urlparse(raw)
    except Exception as exc:
        raise ValueError("invalid YouTube URL") from exc
    host = (u.hostname or "").lower().removeprefix("www.")
    video_id = ""
    if host == "youtu.be":
        video_id = u.path.strip("/").split("/", 1)[0]
    elif host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
        parts = [p for p in u.path.split("/") if p]
        if u.path == "/watch":
            video_id = (parse_qs(u.query).get("v") or [""])[0]
        elif len(parts) >= 2 and parts[0] in {"shorts", "embed", "live"}:
            video_id = parts[1]
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id or ""):
        raise ValueError("could not extract an 11-character YouTube video id")
    return video_id


def canonical_youtube_url(video_id: str) -> str:
    vid = parse_youtube_video_id(video_id)
    return f"https://www.youtube.com/watch?v={vid}"


def _nonnegative_int(value: Any, field: str) -> int | None:
    if value in (None, ""):
        return None
    out = int(value)
    if out < 0:
        raise ValueError(f"{field} cannot be negative")
    return out


def _nonnegative_float(value: Any, field: str) -> float | None:
    if value in (None, ""):
        return None
    out = float(value)
    if out < 0:
        raise ValueError(f"{field} cannot be negative")
    return round(out, 3)


def _short(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def normalize_reference(row: dict[str, Any]) -> dict[str, Any]:
    video_id = parse_youtube_video_id(str(row.get("video_id") or row.get("url") or ""))
    source_mode = str(row.get("source_mode") or "metadata_only").strip().lower()
    if source_mode not in SOURCE_MODES:
        raise ValueError(f"source_mode must be one of {sorted(SOURCE_MODES)}")
    category = str(row.get("category") or "other").strip().lower()
    if category not in CATEGORIES:
        raise ValueError(f"category must be one of {sorted(CATEGORIES)}")

    license_value = str(row.get("license") or "unknown").strip()
    rights_basis = _short(row.get("rights_basis"), 240)
    permission_confirmed = bool(row.get("permission_confirmed", False))
    if source_mode == "creative_commons" and license_value != "creativeCommon":
        raise ValueError("creative_commons structural analysis requires license='creativeCommon'")
    if source_mode == "permission" and not permission_confirmed:
        raise ValueError("permission structural analysis requires permission_confirmed=true")

    structural = dict(row.get("structural") or {})
    if source_mode not in STRUCTURAL_MODES and structural:
        raise ValueError("timing/edit annotations are only allowed for Creative Commons or permissioned references")

    clean_structural: dict[str, Any] = {}
    if structural:
        for key in ("hook_time", "setup_time", "payoff_time", "reaction_end"):
            value = _nonnegative_float(structural.get(key), key)
            if value is not None:
                clean_structural[key] = value
        for key in ("has_facecam", "has_burned_captions", "uses_zoom", "uses_hard_cuts"):
            if key in structural:
                clean_structural[key] = bool(structural.get(key))
        hook_style = _short(structural.get("hook_style"), 80)
        payoff_type = _short(structural.get("payoff_type"), 80)
        if hook_style:
            clean_structural["hook_style"] = hook_style
        if payoff_type:
            clean_structural["payoff_type"] = payoff_type

    duration_seconds = _nonnegative_float(row.get("duration_seconds"), "duration_seconds")
    if clean_structural and duration_seconds:
        for key in ("hook_time", "setup_time", "payoff_time", "reaction_end"):
            if clean_structural.get(key, 0) > duration_seconds + 0.001:
                raise ValueError(f"{key} cannot exceed duration_seconds")

    return {
        "video_id": video_id,
        "url": canonical_youtube_url(video_id),
        "source_mode": source_mode,
        "license": license_value,
        "rights_basis": rights_basis,
        "permission_confirmed": permission_confirmed,
        "creator": _short(row.get("creator"), 120),
        "title": _short(row.get("title"), 240),
        "published_at": _short(row.get("published_at"), 40),
        "observed_at": _short(row.get("observed_at"), 40),
        "category": category,
        "duration_seconds": duration_seconds,
        "view_count": _nonnegative_int(row.get("view_count"), "view_count"),
        "like_count": _nonnegative_int(row.get("like_count"), "like_count"),
        "embeddable": None if row.get("embeddable") is None else bool(row.get("embeddable")),
        "structural": clean_structural,
    }


def load_catalog(path: Path = CATALOG_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("references") if isinstance(payload, dict) else payload
        return [normalize_reference(dict(x)) for x in (rows or []) if isinstance(x, dict)]
    except Exception as exc:
        raise RuntimeError(f"public reference catalog is invalid: {exc}") from exc


def save_catalog(rows: list[dict[str, Any]], path: Path = CATALOG_PATH) -> list[dict[str, Any]]:
    clean = [normalize_reference(dict(x)) for x in rows]
    seen: set[str] = set()
    for row in clean:
        if row["video_id"] in seen:
            raise ValueError(f"duplicate YouTube video id: {row['video_id']}")
        seen.add(row["video_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"schema_version": 1, "references": clean}, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return clean


def upsert_reference(row: dict[str, Any], path: Path = CATALOG_PATH) -> dict[str, Any]:
    clean = normalize_reference(row)
    rows = load_catalog(path)
    replaced = False
    for i, existing in enumerate(rows):
        if existing["video_id"] == clean["video_id"]:
            rows[i] = clean
            replaced = True
            break
    if not replaced:
        rows.append(clean)
    save_catalog(rows, path)
    return clean


def delete_reference(video_id: str, path: Path = CATALOG_PATH) -> bool:
    vid = parse_youtube_video_id(video_id)
    rows = load_catalog(path)
    kept = [x for x in rows if x["video_id"] != vid]
    if len(kept) == len(rows):
        return False
    save_catalog(kept, path)
    return True


def _median(values: list[float]) -> float | None:
    return round(float(statistics.median(values)), 3) if values else None


def summarize_references(rows: list[dict[str, Any]]) -> dict[str, Any]:
    refs = [normalize_reference(dict(x)) for x in rows]
    durations = [float(x["duration_seconds"]) for x in refs if x.get("duration_seconds") is not None]
    title_lengths = [len(str(x.get("title") or "")) for x in refs if x.get("title")]
    views = [float(x["view_count"]) for x in refs if x.get("view_count") is not None]
    engagement = [
        float(x["like_count"]) / float(x["view_count"])
        for x in refs
        if x.get("like_count") is not None and (x.get("view_count") or 0) > 0
    ]
    structural = [x for x in refs if x["source_mode"] in STRUCTURAL_MODES and x.get("structural")]
    hook_times = [float(x["structural"]["hook_time"]) for x in structural if "hook_time" in x["structural"]]
    payoff_ratios = [
        float(x["structural"]["payoff_time"]) / float(x["duration_seconds"])
        for x in structural
        if "payoff_time" in x["structural"] and (x.get("duration_seconds") or 0) > 0
    ]
    reaction_tails = [
        float(x["structural"]["reaction_end"]) - float(x["structural"]["payoff_time"])
        for x in structural
        if "reaction_end" in x["structural"] and "payoff_time" in x["structural"]
        and float(x["structural"]["reaction_end"]) >= float(x["structural"]["payoff_time"])
    ]
    category_counts: dict[str, int] = {}
    for row in refs:
        category_counts[row["category"]] = category_counts.get(row["category"], 0) + 1
    return {
        "reference_count": len(refs),
        "structural_reference_count": len(structural),
        "metadata_only_count": sum(1 for x in refs if x["source_mode"] == "metadata_only"),
        "category_counts": dict(sorted(category_counts.items())),
        "metadata": {
            "median_duration_seconds": _median(durations),
            "median_title_characters": _median([float(x) for x in title_lengths]),
            "median_observed_views": _median(views),
            "median_like_view_ratio": _median(engagement),
        },
        "structural": {
            "median_hook_seconds": _median(hook_times),
            "median_payoff_ratio": _median(payoff_ratios),
            "median_reaction_tail_seconds": _median(reaction_tails),
        },
        "guardrail": "Structural timing/edit statistics include only Creative Commons or explicitly permissioned references.",
    }
