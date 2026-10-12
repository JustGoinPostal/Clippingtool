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


def generate_hook(clip: dict) -> str:
    """Generate a short, deterministic overlay hook with no paid/cloud AI dependency."""
    event=str(clip.get("event_type") or "speech").lower()
    text=" ".join([
        str(clip.get("title") or ""),
        str(clip.get("transcript") or ""),
        str(clip.get("reason") or ""),
    ])
    item=_item_name(text)

    if item:
        if event in {"raid_reward","drop","rare_drop","collection_log","loot","npc_loot"}:
            return f"{item}. NO WAY."
        return f"WAIT... {item}?"
    if event in {"pvp","pvp_kill","player_loot","combat"}:
        return "HE DID NOT EXPECT THAT"
    if event=="big_hit":
        return "THAT SPEC WAS DISGUSTING"
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
    excited=re.search(r"(?:no way|let'?s go|oh my god|what the|bro|dude)[^.!?]{0,30}",transcript,re.I)
    if excited:
        phrase=_clean(excited.group(0)).upper()
        if 8 <= len(phrase) <= 46:
            return phrase
    return "YOU HAVE TO SEE HOW THIS ENDS"
