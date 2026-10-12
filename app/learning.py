from __future__ import annotations
import json
from . import db

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


def learned_profile() -> dict[str, float]:
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


def preference_bonus(features: dict[str, float], profile: dict[str, float]) -> float:
    return sum(float(features.get(k, 0.0)) * float(profile.get(k, 0.0)) for k in FEATURE_KEYS)
