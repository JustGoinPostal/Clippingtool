from __future__ import annotations
import re

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
    title=hook[0].upper()+hook[1:] if hook else "OSRS Stream Highlight"
    tags=["#OSRS","#RuneScape","#Gaming","#Shorts"]
    low=text.lower()+" "+event_summary.lower()
    if event_type in {"pvp_kill","player_loot"} or any(x in low for x in ["pk","pker","kill","smite"]): tags.insert(2,"#OSRSPvP")
    if event_type in {"raid_reward","raid_complete"} or any(x in low for x in ["cox","tob","toa","raid","chambers","theatre of blood","tombs of amascut"]): tags.insert(2,"#OSRSRaids")
    if event_type in {"rare_drop","collection_log","raid_reward"}: tags.insert(2,"#OSRSDrops")
    desc_source=text or event_summary
    desc=(desc_source[:220]+("..." if len(desc_source)>220 else "")) or "Highlight from the stream."
    return title,desc," ".join(dict.fromkeys(tags))
