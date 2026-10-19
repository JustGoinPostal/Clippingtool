from __future__ import annotations
import re


def _gp(value) -> str:
    try: n=float(value or 0)
    except Exception: return ""
    if n >= 1_000_000_000: return f"{n/1_000_000_000:.1f}B".replace(".0B","B")
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M".replace(".0M","M")
    if n >= 1_000: return f"{n/1_000:.0f}K"
    return str(int(n)) if n > 0 else ""


def _item(ctx: dict) -> str:
    if ctx.get("name") and str(ctx.get("moment_archetype") or "") == "reward_reveal":
        return str(ctx["name"]).strip()
    for row in ctx.get("items") or []:
        if isinstance(row,dict) and row.get("name"):
            return str(row["name"]).strip()
    return ""


def _osrs_title(candidate: dict, fallback: str) -> str:
    event_type=str(candidate.get("event_type") or "speech")
    ctx=candidate.get("event_context") if isinstance(candidate.get("event_context"),dict) else {}
    archetype=str(candidate.get("story_archetype") or ctx.get("moment_archetype") or "")
    name=str(ctx.get("name") or ctx.get("source") or "").strip()
    item=_item(ctx)
    value=_gp(ctx.get("loot_value") or ctx.get("total_value"))
    biggest=int(float(ctx.get("biggest_setup_hit",ctx.get("amount",0)) or 0))

    if archetype == "high_value_pk":
        if value and name: return f"{value} PK on {name}"
        if value: return f"That Was a {value} PK"
    if archetype == "pvp_finish":
        if biggest >= 55 and name: return f"{biggest} Damage Into the KO on {name}"
        if name: return f"{name} Did Not Survive This"
    if archetype == "reward_reveal":
        if item and name and item.lower() != name.lower(): return f"{item} From {name}"
        if item: return f"We Actually Got {item}"
        if value: return f"A {value} Drop Out of Nowhere"
    if archetype == "death_collapse":
        hit=int(float(ctx.get("biggest_hit_taken",0) or 0))
        return f"A {hit} Hit Ended the Run" if hit >= 45 else "This Death Happened Fast"
    if event_type == "big_hit" and biggest >= 50:
        return f"{biggest} Damage in One Hit"
    return fallback


def make_metadata(candidate: dict):
    text=re.sub(r"\s+"," ",candidate.get("transcript","")).strip()
    event_type=str(candidate.get("event_type") or "speech")
    event_summary=re.sub(r"\s+"," ",candidate.get("event_summary","")).strip()
    hook=text[:90].strip(" ,.-")
    if not hook and event_summary:
        hook=event_summary.split(":",1)[-1].strip()
    if not hook:
        hook=event_type.replace("_"," ").title() if event_type != "speech" else "OSRS stream highlight"
    if len(hook)>70:
        hook=hook[:67].rsplit(" ",1)[0]+"..."
    fallback=hook[0].upper()+hook[1:] if hook else "OSRS Stream Highlight"
    title=_osrs_title(candidate,fallback)
    if len(title)>100:
        title=title[:97].rsplit(" ",1)[0]+"..."

    tags=["#OSRS","#RuneScape","#Gaming","#Shorts"]
    low=text.lower()+" "+event_summary.lower()+" "+str(candidate.get("story_archetype") or "").lower()
    if event_type in {"pvp_kill","player_loot"} or any(x in low for x in ["pk","pker","kill","smite"]): tags.insert(2,"#OSRSPvP")
    if event_type in {"raid_reward","raid_complete"} or any(x in low for x in ["cox","tob","toa","raid","chambers","theatre of blood","tombs of amascut"]): tags.insert(2,"#OSRSRaids")
    if event_type in {"rare_drop","collection_log","raid_reward"}: tags.insert(2,"#OSRSDrops")
    if str(candidate.get("story_archetype") or "") == "high_value_pk": tags.insert(2,"#PKing")

    desc_source=text or event_summary
    desc=(desc_source[:220]+("..." if len(desc_source)>220 else "")) or "Highlight from the stream."
    return title,desc," ".join(dict.fromkeys(tags))
