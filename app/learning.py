from __future__ import annotations
import json, time
from . import db
from .config import load_settings

FEATURE_KEYS = (
    "keyword", "audio", "speech_density", "visual_change",
    "chat_change", "ui_change", "center_change", "purple", "gold", "red", "punctuation", "runelite_event"
)


def _features(row: dict) -> dict[str, float]:
    try:
        raw = row.get("features_json") or "{}"
        data = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except Exception:
        return {}
    out = {}
    for k in FEATURE_KEYS:
        try: out[k] = float(data.get(k, 0.0))
        except Exception: out[k] = 0.0
    return out


def _explicit_profile() -> dict[str, float]:
    rows = db.q("SELECT status, features_json FROM feedback WHERE status IN ('approved','favorite','rejected')")
    approved = [_features(r) for r in rows if r["status"] in {"approved","favorite"}]
    approved += [_features(r) for r in rows if r["status"] == "favorite"]
    rejected = [_features(r) for r in rows if r["status"] == "rejected"]
    if len(approved) < 3 or len(rejected) < 3:
        return {k: 0.0 for k in FEATURE_KEYS}
    profile = {}
    for k in FEATURE_KEYS:
        a = sum(x.get(k, 0.0) for x in approved) / max(1, len(approved))
        r = sum(x.get(k, 0.0) for x in rejected) / max(1, len(rejected))
        profile[k] = max(-8.0, min(8.0, (a - r) * 12.0))
    return profile


def audience_profile() -> dict[str, float]:
    s = load_settings()
    zero = {k: 0.0 for k in FEATURE_KEYS}
    if not s.analytics_learning_enabled:
        return zero
    cutoff = time.time() - float(s.analytics_learning_min_age_hours) * 3600.0
    try:
        rows = db.q("""
            SELECT c.features_json,a.performance_score,a.views
            FROM analytics_snapshots a
            JOIN publish_queue q ON q.id=a.publish_job_id
            JOIN clips c ON c.id=a.clip_id
            WHERE q.published_at>0 AND q.published_at<=?
              AND a.views>=? AND a.error=''
              AND a.id=(SELECT aa.id FROM analytics_snapshots aa
                        WHERE aa.publish_job_id=a.publish_job_id
                        ORDER BY aa.captured_at DESC,aa.id DESC LIMIT 1)
        """, (cutoff, int(s.analytics_learning_min_views)))
    except Exception:
        return zero
    if len(rows) < 3:
        return zero
    numer = {k: 0.0 for k in FEATURE_KEYS}
    denom = {k: 0.0 for k in FEATURE_KEYS}
    for row in rows:
        f = _features(row)
        signal = max(-1.0, min(1.0, (float(row.get("performance_score") or 50.0) - 50.0) / 50.0))
        view_weight = min(1.0, max(0.25, (float(row.get("views") or 0) / 10000.0) ** 0.25))
        for k in FEATURE_KEYS:
            activation = max(0.0, min(1.0, float(f.get(k, 0.0))))
            if activation <= 0:
                continue
            numer[k] += signal * activation * view_weight
            denom[k] += activation * view_weight
    out = {}
    for k in FEATURE_KEYS:
        mean = numer[k] / denom[k] if denom[k] else 0.0
        out[k] = max(-4.0, min(4.0, mean * 4.0))
    return out


def learned_profile() -> dict[str, float]:
    explicit = _explicit_profile()
    audience = audience_profile()
    weight = max(0.0, min(1.0, float(load_settings().analytics_learning_weight)))
    return {
        k: max(-8.0, min(8.0, float(explicit.get(k, 0.0)) + float(audience.get(k, 0.0)) * weight))
        for k in FEATURE_KEYS
    }


def preference_bonus(features: dict[str, float], profile: dict[str, float]) -> float:
    return sum(float(features.get(k, 0.0)) * float(profile.get(k, 0.0)) for k in FEATURE_KEYS)
