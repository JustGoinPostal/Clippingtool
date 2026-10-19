from __future__ import annotations

import math
from typing import Any

from .config import Settings
from .osrs_events import event_strength, normalize_event_type

# These edit envelopes are intentionally OSRS-specific. They are based on the
# shape of successful public OSRS clips: fast reward reveals, ~30 second PK
# finishes, and longer chase/escape/raid stories when setup is part of payoff.
EVENT_PROFILES: dict[str, dict[str, float]] = {
    "pvp_kill": {"pre": 12.0, "post": 9.0, "min": 18.0, "max": 34.0},
    "player_loot": {"pre": 8.0, "post": 9.0, "min": 15.0, "max": 30.0},
    "big_hit": {"pre": 7.0, "post": 8.0, "min": 13.0, "max": 24.0},
    "big_hit_taken": {"pre": 8.0, "post": 9.0, "min": 15.0, "max": 28.0},
    "player_death": {"pre": 12.0, "post": 11.0, "min": 19.0, "max": 38.0},
    "rare_drop": {"pre": 8.0, "post": 13.0, "min": 16.0, "max": 34.0},
    "collection_log": {"pre": 8.0, "post": 13.0, "min": 16.0, "max": 34.0},
    "raid_reward": {"pre": 12.0, "post": 18.0, "min": 24.0, "max": 48.0},
    "raid_complete": {"pre": 15.0, "post": 18.0, "min": 26.0, "max": 52.0},
    "boss_kill": {"pre": 10.0, "post": 12.0, "min": 18.0, "max": 38.0},
    "npc_loot": {"pre": 7.0, "post": 10.0, "min": 15.0, "max": 30.0},
    "loot": {"pre": 7.0, "post": 10.0, "min": 15.0, "max": 30.0},
}

REWARD_TYPES = {"rare_drop", "collection_log", "raid_reward", "raid_complete", "npc_loot", "loot"}
REWARD_PRIORITY = {
    "collection_log": 6,
    "raid_reward": 5,
    "rare_drop": 4,
    "raid_complete": 3,
    "npc_loot": 2,
    "loot": 1,
}


def _t(event: dict[str, Any]) -> float:
    return float(event.get("time", 0.0) or 0.0)


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("payload")
    return dict(raw) if isinstance(raw, dict) else {}


def _name(event: dict[str, Any]) -> str:
    p = _payload(event)
    return str(p.get("name") or p.get("source") or p.get("target_name") or "").strip().lower()


def _same_actor(a: dict[str, Any], b: dict[str, Any]) -> bool:
    aa, bb = _name(a), _name(b)
    return not aa or not bb or aa == bb


def _loot_value(event: dict[str, Any]) -> float:
    p = _payload(event)
    try:
        return max(0.0, float(p.get("total_value", 0) or 0))
    except Exception:
        return 0.0


def _max_hit(event: dict[str, Any]) -> float:
    p = _payload(event)
    try:
        return max(0.0, float(p.get("amount", p.get("last_confirmed_damage", 0)) or 0))
    except Exception:
        return 0.0


def _value_bonus(value: float) -> float:
    if value <= 0:
        return 0.0
    # Starts becoming meaningful around 1m and saturates so a 1b PK does not
    # permanently dominate every other creator signal.
    return min(22.0, max(0.0, math.log10(max(value, 1.0)) - 6.0) * 8.0)


def _copy_event(event: dict[str, Any]) -> dict[str, Any]:
    out = dict(event)
    out["payload"] = _payload(event)
    out["event_type"] = normalize_event_type(out.get("event_type", ""), out["payload"])
    out["strength"] = float(out.get("strength", event_strength(out)) or 0.0)
    return out


def _reward_cluster(events: list[dict[str, Any]], index: int, used: set[int]) -> tuple[dict[str, Any], set[int]]:
    seed = events[index]
    group = {index}
    seed_t = _t(seed)
    for j, event in enumerate(events):
        if j in used or j == index:
            continue
        typ = normalize_event_type(event.get("event_type", ""), _payload(event))
        if typ not in REWARD_TYPES:
            continue
        if abs(_t(event) - seed_t) <= 8.0:
            group.add(j)

    rows = [_copy_event(events[j]) for j in sorted(group)]
    canonical = max(
        rows,
        key=lambda e: (
            REWARD_PRIORITY.get(str(e.get("event_type") or ""), 0),
            event_strength(e),
            _loot_value(e),
        ),
    )
    p = _payload(canonical)
    total_value = max([_loot_value(x) for x in rows] or [0.0])
    items: list[Any] = []
    messages: list[str] = []
    for row in rows:
        rp = _payload(row)
        if isinstance(rp.get("items"), list):
            items.extend(rp["items"])
        if rp.get("message"):
            messages.append(str(rp["message"]))
    if items and not p.get("items"):
        p["items"] = items[:12]
    if total_value:
        p["total_value"] = total_value
    p["moment_archetype"] = "reward_reveal"
    p["source_event_types"] = [str(x.get("event_type") or "") for x in rows]
    p["story_start"] = max(0.0, min(_t(x) for x in rows) - 8.0)
    p["story_end"] = max(_t(x) for x in rows) + 12.0
    if messages:
        p["story_messages"] = messages[:4]
    canonical["payload"] = p
    canonical["strength"] = min(100.0, max(event_strength(x) for x in rows) + _value_bonus(total_value) + min(10.0, 2.0 * (len(rows) - 1)))
    return canonical, group


def build_story_events(game_events: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Collapse exact RuneLite telemetry into clip-worthy OSRS story moments.

    bridge_* events are framing telemetry and intentionally excluded here; the raw
    event stream still goes to the renderer. This function is only for ranking and
    clip boundary decisions.
    """
    raw = sorted([e for e in (game_events or []) if not str(e.get("event_type") or "").startswith("bridge_")], key=_t)
    out: list[dict[str, Any]] = []
    used: set[int] = set()

    # Reward events commonly arrive as loot + chat + collection-log/raid events.
    # Treat that as one reveal instead of three competing clips.
    for i, event in enumerate(raw):
        if i in used:
            continue
        typ = normalize_event_type(event.get("event_type", ""), _payload(event))
        if typ in REWARD_TYPES:
            canonical, group = _reward_cluster(raw, i, used)
            used.update(group)
            out.append(canonical)

    # PK finishes are story arcs: setup/spec -> death -> loot/reaction.
    for i, event in enumerate(raw):
        if i in used:
            continue
        typ = normalize_event_type(event.get("event_type", ""), _payload(event))
        if typ != "pvp_kill":
            continue
        kill = _copy_event(event)
        t = _t(kill)
        pre_hits = [
            _copy_event(x) for x in raw
            if normalize_event_type(x.get("event_type", ""), _payload(x)) == "big_hit"
            and 0.0 <= t - _t(x) <= 12.0 and _same_actor(kill, x)
        ]
        loot_rows = [
            _copy_event(x) for x in raw
            if normalize_event_type(x.get("event_type", ""), _payload(x)) == "player_loot"
            and 0.0 <= _t(x) - t <= 12.0 and _same_actor(kill, x)
        ]
        biggest = max([_max_hit(x) for x in pre_hits] or [_max_hit(kill)])
        loot_value = max([_loot_value(x) for x in loot_rows] or [0.0])
        p = _payload(kill)
        p["moment_archetype"] = "high_value_pk" if loot_value >= 20_000_000 else "pvp_finish"
        p["biggest_setup_hit"] = biggest
        p["loot_value"] = loot_value
        p["story_start"] = max(0.0, min([_t(x) for x in pre_hits] or [t - 10.0]) - 2.0)
        p["story_end"] = max([_t(x) for x in loot_rows] or [t + 6.0]) + 4.0
        p["source_event_types"] = ["big_hit"] * len(pre_hits) + ["pvp_kill"] + ["player_loot"] * len(loot_rows)
        kill["payload"] = p
        kill["strength"] = min(100.0, event_strength(kill) + min(18.0, biggest / 4.0) + _value_bonus(loot_value))
        out.append(kill)
        used.add(i)
        for j, x in enumerate(raw):
            if j in used:
                continue
            xt = normalize_event_type(x.get("event_type", ""), _payload(x))
            if xt == "big_hit" and 0 <= t - _t(x) <= 12.0 and _same_actor(kill, x):
                used.add(j)
            elif xt == "player_loot" and 0 <= _t(x) - t <= 12.0 and _same_actor(kill, x):
                used.add(j)

    # Deaths should include the damage that caused the collapse plus the immediate
    # streamer reaction instead of beginning at the death message itself.
    for i, event in enumerate(raw):
        if i in used:
            continue
        typ = normalize_event_type(event.get("event_type", ""), _payload(event))
        if typ != "player_death":
            continue
        death = _copy_event(event)
        t = _t(death)
        incoming = [
            _copy_event(x) for x in raw
            if normalize_event_type(x.get("event_type", ""), _payload(x)) == "big_hit_taken"
            and 0.0 <= t - _t(x) <= 10.0
        ]
        p = _payload(death)
        p["moment_archetype"] = "death_collapse"
        p["biggest_hit_taken"] = max([_max_hit(x) for x in incoming] or [0.0])
        p["story_start"] = max(0.0, min([_t(x) for x in incoming] or [t - 10.0]) - 2.0)
        p["story_end"] = t + 10.0
        death["payload"] = p
        death["strength"] = min(100.0, event_strength(death) + min(14.0, p["biggest_hit_taken"] / 5.0))
        out.append(death)
        used.add(i)
        for j, x in enumerate(raw):
            if j not in used and normalize_event_type(x.get("event_type", ""), _payload(x)) == "big_hit_taken" and 0 <= t - _t(x) <= 10.0:
                used.add(j)

    # Anything not absorbed into a richer story remains eligible on its own.
    for i, event in enumerate(raw):
        if i in used:
            continue
        out.append(_copy_event(event))

    return sorted(out, key=lambda e: (-float(e.get("strength", 0.0) or 0.0), _t(e)))


def _snap_to_speech(segments: list[dict[str, Any]], start: float, end: float) -> tuple[float, float]:
    if not segments:
        return start, end
    before = [s for s in segments if float(s.get("start", 0)) <= start <= float(s.get("end", 0)) + 4.0]
    after = [s for s in segments if float(s.get("start", 0)) - 5.0 <= end <= float(s.get("end", 0))]
    if before:
        start = min(start, float(before[-1].get("start", start)))
    if after:
        end = max(end, float(after[0].get("end", end)))
    return start, end


def story_window(segments: list[dict[str, Any]], event: dict[str, Any], total: float, s: Settings) -> tuple[float, float]:
    typ = normalize_event_type(event.get("event_type", ""), _payload(event))
    profile = EVENT_PROFILES.get(typ)
    if not profile:
        t = _t(event)
        return max(0.0, t - float(s.pre_roll_seconds)), min(total, t + float(s.post_roll_seconds))

    t = _t(event)
    p = _payload(event)
    start = max(0.0, float(p.get("story_start", t - profile["pre"]) or 0.0))
    end = min(total, float(p.get("story_end", t + profile["post"]) or total))
    start, end = _snap_to_speech(segments, start, end)

    # Preserve enough setup and enough reaction. If the story becomes too long,
    # the payoff remains in-frame instead of blindly trimming only the end.
    minimum = profile["min"]
    maximum = profile["max"]
    if end - start < minimum:
        need = minimum - (end - start)
        start = max(0.0, start - need * 0.55)
        end = min(total, end + need * 0.45)
        if end - start < minimum:
            start = max(0.0, end - minimum)
    if end - start > maximum:
        preferred_start = max(0.0, t - profile["pre"])
        start = max(start, preferred_start)
        end = min(total, start + maximum)
        if end < t + min(profile["post"], maximum * 0.30):
            end = min(total, t + min(profile["post"], maximum * 0.30))
            start = max(0.0, end - maximum)

    return max(0.0, start), min(total, max(start + 0.5, end))
