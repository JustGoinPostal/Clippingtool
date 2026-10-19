from __future__ import annotations

import re

RARE_ITEMS = (
    "twisted bow", "tbow", "scythe", "tumeken's shadow", "tumekens shadow",
    "shadow", "torva", "ancestral", "kodai", "elder maul", "pet",
)


def _clean(text: str) -> str:
    text=re.sub(r"<[^>]+>"," ",text or "")
    text=re.sub(r"\s+"," ",text).strip()
    return text


def _item_name(text: str) -> str:
    low=text.lower()
    for item in RARE_ITEMS:
        if item in low:
            if item in {"tbow"}: return "TWISTED BOW"
            if item in {"tumeken's shadow","tumekens shadow","shadow"}: return "TUMEKEN'S SHADOW"
            return item.upper()
    return ""


def _context_item(ctx: dict) -> str:
    if ctx.get("name") and str(ctx.get("moment_archetype") or "") in {"reward_reveal","pet_reveal"}:
        return str(ctx["name"]).strip().upper()
    for row in ctx.get("items") or []:
        if isinstance(row,dict) and row.get("name"):
            return str(row["name"]).strip().upper()
    return ""


def _gp(value) -> str:
    try: n=float(value or 0)
    except Exception: return ""
    if n >= 1_000_000_000: return f"{n/1_000_000_000:.1f}B".replace(".0B","B")
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M".replace(".0M","M")
    if n >= 1_000: return f"{n/1_000:.0f}K"
    return str(int(n)) if n > 0 else ""


def _message(ctx: dict) -> str:
    return _clean(str(ctx.get("message") or ""))


def generate_hook(clip: dict) -> str:
    """Generate a short OSRS-aware overlay hook with no paid/cloud dependency."""
    event=str(clip.get("event_type") or "speech").lower()
    ctx=clip.get("event_context") if isinstance(clip.get("event_context"),dict) else {}
    archetype=str(clip.get("story_archetype") or ctx.get("moment_archetype") or "")
    text=" ".join([
        str(clip.get("title") or ""),
        str(clip.get("transcript") or ""),
        str(clip.get("reason") or ""),
    ])
    item=_context_item(ctx) or _item_name(text)

    if archetype == "pvp_smite":
        value=_gp(ctx.get("loot_value") or ctx.get("total_value"))
        return f"SMITED FOR {value}" if value else "HE GOT SMITED"
    if archetype in {"high_value_pk","pvp_finish"}:
        value=_gp(ctx.get("loot_value") or ctx.get("total_value"))
        hit=int(float(ctx.get("biggest_setup_hit",0) or 0))
        if value:
            return f"{value} ON THE FLOOR"
        if hit >= 55:
            return f"{hit} INTO THE KO"
        return "HE'S ACTUALLY DEAD"
    if archetype == "pvp_escape":
        hp=int(float(ctx.get("lowest_hp",0) or 0))
        hit=int(float(ctx.get("trigger_hit",0) or 0))
        if 0 < hp <= 10:
            return f"I LIVED ON {hp} HP"
        if hit >= 50:
            return f"{hit} HIT... AND I LIVED"
        return "HOW DID I SURVIVE THAT?"
    if archetype == "pet_reveal" or event == "pet_drop":
        return f"{item}. NO WAY." if item and item != "PET" else "THAT'S THE PET. NO WAY."
    if archetype == "reward_reveal" and item:
        return f"{item}. NO WAY."
    if archetype == "death_collapse":
        hit=int(float(ctx.get("biggest_hit_taken",0) or 0))
        return f"{hit} DAMAGE. I'M DEAD." if hit >= 45 else "THIS WENT WRONG FAST"
    if event == "combat_achievement":
        return "COMBAT TASK DONE"
    if event == "personal_best":
        return "NEW PB. LET'S GO."
    if event == "skill_milestone":
        msg=_message(ctx)
        lvl=re.search(r"\b(9[0-9]|[1-8][0-9]|\d)\b",msg)
        if lvl and lvl.group(1)=="99": return "99. FINALLY."
        return "ANOTHER MILESTONE DONE"
    if event == "quest_complete":
        return "QUEST COMPLETE"
    if event == "boss_kill":
        name=str(ctx.get("name") or "").strip().upper()
        return f"{name} IS DOWN" if name and len(name)<=26 else "BOSS DOWN"

    if item:
        if event in {"raid_reward","drop","rare_drop","collection_log","loot","npc_loot"}:
            return f"{item}. NO WAY."
        return f"WAIT... {item}?"
    if event in {"pvp","pvp_kill","player_loot","combat"}:
        return "HE DID NOT EXPECT THAT"
    if event=="big_hit":
        amount=int(float(ctx.get("amount",0) or 0))
        return f"{amount} DAMAGE?!" if amount >= 50 else "THAT SPEC WAS DISGUSTING"
    if event=="big_hit_taken":
        return "THAT ALMOST ENDED THE RUN"
    if event in {"raid_reward","raid_complete"}:
        return "THE RAID ACTUALLY PAID"
    if event in {"drop","rare_drop","collection_log","loot","npc_loot"}:
        return "THAT DROP WAS NOT REAL"
    if event in {"death","player_death"}:
        return "THIS WENT WRONG FAST"
    if event in {"reaction","chat_reaction"}:
        return "I WAS NOT READY FOR THIS"

    transcript=_clean(str(clip.get("transcript") or ""))
    excited=re.search(r"(?:no way|let'?s go|oh my god|what the|bro|dude|holy)[^.!?]{0,30}",transcript,re.I)
    if excited:
        phrase=_clean(excited.group(0)).upper()
        if 8 <= len(phrase) <= 46:
            return phrase
    return "YOU HAVE TO SEE HOW THIS ENDS"
