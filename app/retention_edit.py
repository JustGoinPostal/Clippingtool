from __future__ import annotations

import math
import statistics
from typing import Any

IMPORTANT_EVENT_HINTS = (
    "big_hit", "pvp_kill", "boss_kill", "player_death", "rare_drop", "pet_drop",
    "collection_log", "raid_complete", "personal_best", "combat_achievement",
    "skill_milestone", "quest_complete", "loot", "drop", "death", "kill", "reward",
)


def _finite(value: Any) -> float | None:
    try:
        out=float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _event_priority(event: dict) -> float:
    typ=str(event.get("event_type") or "").lower()
    if typ.startswith("bridge_"):
        return -1.0
    if not any(hint in typ for hint in IMPORTANT_EVENT_HINTS):
        return -1.0
    strength=_finite(event.get("strength")) or 0.0
    payload=event.get("payload") or {}
    amount=_finite(payload.get("amount")) or 0.0
    bonus=0.0
    if any(x in typ for x in ("pvp_kill","boss_kill","pet_drop","rare_drop")):
        bonus=40.0
    elif any(x in typ for x in ("big_hit","player_death","raid_complete")):
        bonus=28.0
    elif any(x in typ for x in ("loot","drop","reward","personal_best","combat_achievement")):
        bonus=18.0
    return bonus + min(60.0, max(0.0, strength)) + min(25.0, max(0.0, amount) * 0.35)


def event_punch_times(game_events: list[dict] | None, start: float, end: float, max_events: int = 6) -> list[float]:
    """Return clip-relative moments worth a brief gameplay punch-in."""
    if not game_events or end <= start:
        return []
    candidates=[]
    for event in game_events:
        t=_finite(event.get("time"))
        if t is None or t < start or t > end:
            continue
        priority=_event_priority(event)
        if priority < 0:
            continue
        candidates.append((priority, max(0.0, min(end-start, t-start))))
    candidates.sort(key=lambda row: row[0], reverse=True)
    chosen=[]
    for _, t in candidates:
        if any(abs(t-existing) < 1.15 for existing in chosen):
            continue
        chosen.append(t)
        if len(chosen) >= max(1, int(max_events)):
            break
    return sorted(chosen)


def reaction_windows(
    energy_samples: list | None,
    start: float,
    end: float,
    *,
    z_threshold: float = 1.35,
    hold_seconds: float = 1.45,
    max_events: int = 5,
) -> list[tuple[float,float]]:
    """Detect clip-relative loud reaction windows from cached stream audio energy."""
    if not energy_samples or end <= start:
        return []
    parsed=[]
    for row in energy_samples:
        try:
            ts, value=row[0], row[1]
        except Exception:
            continue
        t=_finite(ts); v=_finite(value)
        if t is None or v is None or v <= -120:
            continue
        parsed.append((t,v))
    if len(parsed) < 3:
        return []
    levels=[v for _,v in parsed]
    mean=statistics.mean(levels)
    std=max(statistics.pstdev(levels), 3.0)
    peaks=[]
    for t,v in parsed:
        if t < start or t > end:
            continue
        z=(v-mean)/std
        if z >= float(z_threshold):
            peaks.append((z,t))
    peaks.sort(reverse=True)
    chosen=[]
    for z,t in peaks:
        if any(abs(t-existing[1]) < 1.20 for existing in chosen):
            continue
        chosen.append((z,t))
        if len(chosen) >= max(1, int(max_events)):
            break
    duration=end-start
    windows=[]
    for _,t in sorted(chosen,key=lambda row: row[1]):
        rel=t-start
        a=max(0.0, rel-0.22)
        b=min(duration, rel+max(0.55,float(hold_seconds)))
        if b-a >= 0.35:
            windows.append((a,b))
    merged=[]
    for a,b in windows:
        if merged and a <= merged[-1][1] + 0.12:
            merged[-1]=(merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a,b))
    return merged


def enable_expression(windows: list[tuple[float,float]], time_var: str = "t") -> str:
    if not windows:
        return "0"
    tv=str(time_var or "t")
    return "+".join(f"between({tv},{a:.3f},{b:.3f})" for a,b in windows)
