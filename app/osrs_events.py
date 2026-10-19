from __future__ import annotations
import math, statistics, re
from typing import Any

EVENT_WEIGHTS: dict[str, float] = {
    "collection_log": 48,
    "pet_drop": 58,
    "raid_reward": 44,
    "rare_drop": 42,
    "player_loot": 38,
    "pvp_kill": 44,
    "pvp_escape": 42,
    "player_death": 34,
    "npc_loot": 18,
    "big_hit": 18,
    "big_hit_taken": 13,
    "loot": 20,
    "chat_reaction": 14,
    "boss_kill": 28,
    "raid_complete": 36,
    "raid_start": 6,
    "combat_achievement": 36,
    "skill_milestone": 22,
    "quest_complete": 28,
    "personal_best": 32,
}

DROP_WORDS = (
    "collection log", "new item added", "purple", "twisted bow", "tbow",
    "scythe", "tumeken", "shadow", "pet", "unique", "rare drop",
)
PVP_WORDS = ("pk", "pker", "smite", "smited", "loot key", "player loot")
DEATH_WORDS = ("you have died", "oh dear, you are dead", "death")
RAID_WORDS = ("chambers of xeric", "theatre of blood", "tombs of amascut", "raid")
PET_WORDS = (
    "funny feeling like you're being followed",
    "funny feeling you would have been followed",
    "weird sneaking into your backpack",
)


def _payload_text(payload: dict[str, Any]) -> str:
    return " ".join(str(payload.get(k, "")) for k in ("message", "name", "source", "item", "items", "raid_name", "achievement")).lower()


def normalize_event_type(event_type: str, payload: dict[str, Any] | None = None) -> str:
    payload = payload or {}
    raw = (event_type or "").strip().lower().replace("-", "_").replace(" ", "_")
    text = _payload_text(payload)
    if raw.startswith("bridge_"):
        return raw
    if "collection" in raw or "collection log" in text or "new item added" in text:
        return "collection_log"
    if any(w in text for w in PET_WORDS) or raw in {"pet", "pet_received", "pet_drop"}:
        return "pet_drop"
    if "combat task completed" in text or "combat achievement completed" in text or "combat_achievement" in raw:
        return "combat_achievement"
    if "new personal best" in text or raw in {"pb", "personal_best"}:
        return "personal_best"
    if "quest complete" in text or "quest completed" in text:
        return "quest_complete"
    if "just advanced" in text or "total level is now" in text or raw in {"level_up", "skill_level", "skill_milestone"}:
        return "skill_milestone"
    if raw in {"playerlootreceived", "player_loot_received", "pk_loot"} or "player loot" in text:
        return "player_loot"
    if raw in {"npclootreceived", "npc_loot_received", "server_npc_loot"}:
        return "npc_loot"
    # Generic loot must remain context-sensitive: RuneLite's LootReceived can use
    # the same event label for raid chests/reward interfaces and ordinary loot.
    if "loot" in raw:
        if any(w in text for w in RAID_WORDS):
            return "raid_reward"
        if payload.get("unique") or payload.get("rare"):
            return "rare_drop"
        return "loot"
    if raw in {"actordeath", "actor_death"}:
        actor_type = str(payload.get("actor_type", "")).lower()
        if actor_type == "player" and payload.get("local_player"):
            return "player_death"
        if actor_type == "player" and payload.get("attributed_to_local"):
            return "pvp_kill"
        if actor_type == "npc" and payload.get("attributed_to_local"):
            return "boss_kill"
        return "runelite_event"
    if raw in {"hitsplatapplied", "hitsplat_applied", "hitsplat"}:
        if payload.get("target_local"):
            return "big_hit_taken"
        if payload.get("attributed_to_local"):
            return "big_hit"
        return "runelite_event"
    if "raid" in raw and ("complete" in raw or "finish" in raw):
        return "raid_complete"
    if raw in EVENT_WEIGHTS:
        return raw
    if any(w in text for w in DROP_WORDS):
        return "rare_drop"
    if any(w in text for w in PVP_WORDS):
        return "pvp_kill"
    if any(w in text for w in DEATH_WORDS):
        return "player_death"
    return raw or "runelite_event"


def _extract_level(text: str) -> int:
    vals=[]
    for m in re.finditer(r"\b(?:level(?: is now)?|to)\s*[: ]?\s*(\d{1,3})\b", text, re.I):
        try: vals.append(int(m.group(1)))
        except Exception: pass
    return max(vals or [0])


def event_strength(event: dict[str, Any]) -> float:
    typ = normalize_event_type(event.get("event_type", ""), event.get("payload") or {})
    base = EVENT_WEIGHTS.get(typ, 12.0)
    payload = event.get("payload") or {}
    confidence = float(event.get("confidence", 1.0) or 1.0)
    confidence = max(0.25, min(1.5, confidence))
    if typ in {"big_hit", "big_hit_taken"}:
        amount = float(payload.get("amount", 0) or 0)
        multiplier = 0.7 if typ == "big_hit" else 0.45
        base += min(22.0, max(0.0, amount - 25.0) * multiplier)
    items = payload.get("items")
    if isinstance(items, list):
        base += min(10.0, len(items) * 1.5)
        if any(bool(x.get("unique")) for x in items if isinstance(x, dict)):
            base += 20.0
    if payload.get("unique"):
        base += 20.0
    if payload.get("rare"):
        base += 14.0
    if typ == "skill_milestone":
        level = int(payload.get("level", 0) or 0) or _extract_level(str(payload.get("message") or ""))
        if level >= 99:
            base += 30.0
        elif level >= 90:
            base += 14.0
        elif level and level % 10 == 0:
            base += 6.0
    if typ == "combat_achievement":
        text = _payload_text(payload)
        if "grandmaster" in text: base += 24.0
        elif "master" in text: base += 15.0
        elif "elite" in text: base += 10.0
    if typ == "pvp_escape":
        hp_ratio = float(payload.get("lowest_hp_ratio", payload.get("hp_ratio", 1.0)) or 1.0)
        moved = float(payload.get("tiles_moved", 0) or 0)
        base += min(20.0, max(0.0, (0.45 - hp_ratio) * 50.0)) + min(8.0, moved * 0.5)
    try:
        total_value=float(payload.get("total_value", payload.get("loot_value",0)) or 0)
        if total_value > 0:
            base += min(24.0, max(0.0, math.log10(max(1.0,total_value))-4.5) * 10.0)
    except Exception:
        pass
    return base * confidence


def summarize_event(event: dict[str, Any]) -> str:
    typ = normalize_event_type(event.get("event_type", ""), event.get("payload") or {})
    p = event.get("payload") or {}
    bits: list[str] = []
    if p.get("name"):
        bits.append(str(p["name"]))
    if p.get("opponent_name"):
        bits.append(f"vs {p['opponent_name']}")
    if p.get("source"):
        bits.append(f"from {p['source']}")
    if p.get("raid_name"):
        bits.append(str(p["raid_name"]))
    if isinstance(p.get("items"), list):
        names=[]
        for item in p["items"][:4]:
            if isinstance(item, dict):
                n=item.get("name") or item.get("id")
                q=item.get("quantity",1)
                if n is not None: names.append(f"{q}x {n}" if q not in (None,1) else str(n))
            else:
                names.append(str(item))
        if names: bits.append(", ".join(names))
    if p.get("message"):
        bits.append(re.sub(r"<[^>]+>", "", str(p["message"]))[:120])
    if typ in {"big_hit", "big_hit_taken"} and p.get("amount") is not None:
        direction = "dealt" if typ == "big_hit" else "taken"
        bits.append(f"{p['amount']} damage {direction}")
    if typ == "pvp_kill" and p.get("last_confirmed_damage") is not None:
        bits.append(f"last hit {p['last_confirmed_damage']}")
    if typ == "pvp_escape":
        if p.get("lowest_hp") is not None: bits.append(f"escaped on {p['lowest_hp']} HP")
        if p.get("tiles_moved") is not None: bits.append(f"{p['tiles_moved']} tiles moved")
    return f"RuneLite {typ.replace('_',' ')}" + (": " + " · ".join(bits) if bits else "")


def map_events_to_recording(events: list[dict[str, Any]], start_epoch: float, duration: float) -> list[dict[str, Any]]:
    out=[]
    for e in events:
        wall=float(e.get("event_time",0) or 0)
        t=wall-start_epoch
        if -4 <= t <= duration+4:
            x=dict(e)
            x["time"]=round(max(0.0,min(duration,t)),3)
            x["event_type"]=normalize_event_type(x.get("event_type",""),x.get("payload") or {})
            x["strength"]=round(event_strength(x),2)
            x["summary"]=summarize_event(x)
            out.append(x)
    return sorted(out,key=lambda x:x["time"])
