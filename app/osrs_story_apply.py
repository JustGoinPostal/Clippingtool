from __future__ import annotations

import re
from typing import Any

from .config import Settings
from .osrs_context import enrich_encounter_context
from .osrs_events import normalize_event_type, summarize_event
from .osrs_story import build_story_events, story_window


def _clip_text(segments: list[dict[str, Any]], start: float, end: float) -> str:
    return " ".join(
        str(s.get("text") or "").strip()
        for s in segments
        if float(s.get("end", 0) or 0) >= start and float(s.get("start", 0) or 0) <= end
    ).strip()


def _iou(a: dict[str, Any], b: dict[str, Any]) -> float:
    a0, a1 = float(a.get("start", 0) or 0), float(a.get("end", 0) or 0)
    b0, b1 = float(b.get("start", 0) or 0), float(b.get("end", 0) or 0)
    inter = max(0.0, min(a1, b1) - max(a0, b0))
    union = max(a1, b1) - min(a0, b0)
    return inter / union if union > 0 else 0.0


def _compatible(candidate_type: str, story_type: str) -> bool:
    c = (candidate_type or "").lower()
    s = (story_type or "").lower()
    if c == s:
        return True
    if s in {"pvp_kill", "pvp_escape", "player_loot", "big_hit"} and c in {"pvp", "combat", "gameplay", "reaction"}:
        return True
    if s in {"pet_drop", "rare_drop", "collection_log", "raid_reward", "raid_complete", "loot", "npc_loot"} and c in {"drop", "gameplay", "reaction"}:
        return True
    if s == "player_death" and c in {"death", "reaction", "gameplay"}:
        return True
    if s in {"combat_achievement", "skill_milestone", "quest_complete", "personal_best", "boss_kill"} and c in {"reaction", "gameplay", "speech"}:
        return True
    return False


def _story_score(story: dict[str, Any], current: float = 0.0) -> float:
    strength = float(story.get("strength", 0.0) or 0.0)
    payload = story.get("payload") if isinstance(story.get("payload"), dict) else {}
    archetype = str(payload.get("moment_archetype") or "")
    bonus = 5.0 if archetype in {"pvp_finish", "reward_reveal", "pet_reveal", "death_collapse", "pvp_escape"} else 0.0
    if archetype == "high_value_pk":
        bonus = 10.0
    if archetype == "pvp_smite":
        bonus = 12.0
    return min(100.0, max(float(current or 0.0), 15.0 + strength + bonus))


def _smite_signal(text: str) -> bool:
    low = (text or "").lower()
    return bool(re.search(r"\bsmite(?:d|s|ing)?\b|\bno prayer\b|\bgot (?:his|their) \+?1\b", low))


def _decorate(candidate: dict[str, Any], story: dict[str, Any], segments: list[dict[str, Any]], total: float, s: Settings) -> dict[str, Any]:
    out = dict(candidate)
    start, end = story_window(segments, story, total, s)
    typ = normalize_event_type(story.get("event_type", ""), story.get("payload") or {})
    payload = dict(story.get("payload") or {})
    clip_text = _clip_text(segments, start, end) or str(out.get("transcript") or "")
    archetype = str(payload.get("moment_archetype") or typ)

    # RuneLite can prove the kill/loot, but it cannot reliably expose an opponent's
    # prayer points. Promote to a smite story only when the exact PK is also paired
    # with the local spoken reaction around that same moment.
    if typ == "pvp_kill" and _smite_signal(clip_text):
        payload["smite_signal"] = True
        payload["smite_signal_source"] = "local_transcript"
        payload["moment_archetype"] = "pvp_smite"
        archetype = "pvp_smite"

    score = _story_score({**story, "payload": payload}, float(out.get("score", 0) or 0))
    out.update({
        "start": round(start, 2),
        "end": round(end, 2),
        "score": round(score, 1),
        "base_score": round(max(float(out.get("base_score", 0) or 0), score), 1),
        "event_type": typ,
        "event_summary": summarize_event({**story, "payload": payload}),
        "event_context": payload,
        "story_archetype": archetype,
        "transcript": clip_text,
    })
    features = dict(out.get("features") or {})
    features["runelite_event"] = max(float(features.get("runelite_event", 0) or 0), min(1.0, float(story.get("strength", 0) or 0) / 55.0))
    features["osrs_story"] = 1.0
    if bool(payload.get("inferred")):
        features["inferred_story"] = 1.0
    if bool(payload.get("smite_signal")):
        features["smite_signal"] = 1.0
    if payload.get("activity_key"):
        features["encounter_context"] = 1.0
    if float(payload.get("loot_value", payload.get("total_value", 0)) or 0) >= 20_000_000:
        features["high_value"] = 1.0
    out["features"] = features
    reason = str(out.get("reason") or "").strip("; ")
    story_reason = f"OSRS story: {archetype.replace('_', ' ')}"
    if payload.get("encounter"):
        story_reason += f" at {payload['encounter']}"
    elif payload.get("activity"):
        story_reason += f" in {payload['activity']}"
    out["reason"] = f"{reason}; {story_reason}" if reason else story_reason
    return out


def apply_story_intelligence(
    candidates: list[dict[str, Any]],
    game_events: list[dict[str, Any]] | None,
    transcript: dict[str, Any],
    total_duration: float,
    s: Settings,
) -> list[dict[str, Any]]:
    """Promote exact/inferred OSRS story arcs without crushing personality-only clips."""
    enriched_events=enrich_encounter_context(game_events)
    stories = build_story_events(enriched_events)
    if not stories:
        return candidates
    segments = list(transcript.get("segments") or [])
    output = [dict(c) for c in candidates]
    matched_indexes: set[int] = set()

    always_keep_types = {
        "pvp_kill", "pvp_escape", "player_death", "collection_log", "pet_drop", "rare_drop", "raid_reward",
        "raid_complete", "combat_achievement", "quest_complete", "personal_best", "boss_kill",
    }

    for story in stories:
        typ = normalize_event_type(story.get("event_type", ""), story.get("payload") or {})
        t = float(story.get("time", 0) or 0)
        strength = float(story.get("strength", 0) or 0)
        options: list[tuple[float, int]] = []
        for i, candidate in enumerate(output):
            if i in matched_indexes:
                continue
            start = float(candidate.get("start", 0) or 0)
            end = float(candidate.get("end", 0) or 0)
            mid = (start + end) / 2.0
            contains = start - 2.0 <= t <= end + 2.0
            if not contains:
                continue
            penalty = 0.0 if _compatible(str(candidate.get("event_type") or ""), typ) else 8.0
            options.append((abs(mid - t) + penalty, i))

        if options:
            _, idx = min(options)
            output[idx] = _decorate(output[idx], story, segments, total_duration, s)
            matched_indexes.add(idx)
            continue

        if strength < 34.0 and typ not in always_keep_types:
            continue
        start, end = story_window(segments, story, total_duration, s)
        synthesized = {
            "start": start,
            "end": end,
            "score": _story_score(story),
            "base_score": _story_score(story),
            "personal_score": 0.0,
            "reason": "RuneLite OSRS story moment",
            "transcript": _clip_text(segments, start, end),
            "event_type": typ,
            "features": {"runelite_event": min(1.0, strength / 55.0), "osrs_story": 1.0},
            "event_summary": summarize_event(story),
        }
        output.append(_decorate(synthesized, story, segments, total_duration, s))

    output.sort(key=lambda c: float(c.get("score", 0) or 0), reverse=True)
    keep: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for candidate in output:
        duplicate = any(
            _iou(candidate, existing) >= 0.58
            and (
                str(candidate.get("story_archetype") or "")
                or str(existing.get("story_archetype") or "")
                or _compatible(str(candidate.get("event_type") or ""), str(existing.get("event_type") or ""))
            )
            for existing in keep
        )
        if duplicate:
            continue
        typ = str(candidate.get("event_type") or "speech")
        if counts.get(typ, 0) >= max(2, int(s.diversity_per_type)):
            continue
        counts[typ] = counts.get(typ, 0) + 1
        keep.append(candidate)
        if len(keep) >= int(s.max_candidates):
            break
    return keep
