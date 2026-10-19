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
    if ctx.get("name") and str(ctx.get("moment_archetype") or "") in {"reward_reveal","pet_reveal"}:
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
    opponent=str(ctx.get("opponent_name") or name).strip()
    item=_item(ctx)
    value=_gp(ctx.get("loot_value") or ctx.get("total_value"))
    biggest=int(float(ctx.get("biggest_setup_hit",ctx.get("amount",0)) or 0))

    if archetype == "pvp_smite":
        if value and opponent: return f"Smited {opponent} for {value}"
        if value: return f"That Smite Was Worth {value}"
        if opponent: return f"We Actually Smited {opponent}"
        return "That Smite Actually Worked"
    if archetype == "high_value_pk":
        if value and name: return f"{value} PK on {name}"
        if value: return f"That Was a {value} PK"
    if archetype == "pvp_finish":
        if biggest >= 55 and name: return f"{biggest} Damage Into the KO on {name}"
        if name: return f"{name} Did Not Survive This"
    if archetype == "pvp_escape":
        hp=int(float(ctx.get("lowest_hp",0) or 0))
        hit=int(float(ctx.get("trigger_hit",0) or 0))
        if 0 < hp <= 10: return f"Escaped on {hp} HP"
        if hit >= 50: return f"Survived a {hit} Hit and Escaped"
        return "I Should Not Have Survived This"
    if archetype == "pet_reveal" or event_type == "pet_drop":
        if item and item.lower() != "pet": return f"We Actually Got {item}"
        return "The Pet Finally Dropped"
    if archetype == "reward_reveal":
        if item and name and item.lower() != name.lower(): return f"{item} From {name}"
        if item: return f"We Actually Got {item}"
        if value: return f"A {value} Drop Out of Nowhere"
    if archetype == "death_collapse":
        hit=int(float(ctx.get("biggest_hit_taken",0) or 0))
        return f"A {hit} Hit Ended the Run" if hit >= 45 else "This Death Happened Fast"
    if event_type == "combat_achievement": return "Combat Task Completed"
    if event_type == "personal_best": return "New OSRS Personal Best"
    if event_type == "quest_complete": return "Quest Complete"
    if event_type == "skill_milestone":
        msg=str(ctx.get("message") or "")
        if re.search(r"\b99\b",msg): return "99 Finally Achieved"
        return "Another OSRS Milestone Done"
    if event_type == "boss_kill" and name: return f"{name} Down"
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
    if event_type in {"pvp_kill","pvp_escape","player_loot"} or any(x in low for x in ["pk","pker","kill","smite"]): tags.insert(2,"#OSRSPvP")
    if event_type in {"raid_reward","raid_complete"} or any(x in low for x in ["cox","tob","toa","raid","chambers","theatre of blood","tombs of amascut"]): tags.insert(2,"#OSRSRaids")
    if event_type in {"pet_drop","rare_drop","collection_log","raid_reward"}: tags.insert(2,"#OSRSDrops")
    if str(candidate.get("story_archetype") or "") in {"high_value_pk","pvp_smite"}: tags.insert(2,"#PKing")
    if event_type in {"combat_achievement","skill_milestone","quest_complete","personal_best"}: tags.insert(2,"#OSRSAchievements")

    desc_source=text or event_summary
    desc=(desc_source[:220]+("..." if len(desc_source)>220 else "")) or "Highlight from the stream."
    return title,desc," ".join(dict.fromkeys(tags))
