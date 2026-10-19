from __future__ import annotations

import re
from typing import Any

# Target/source names are authoritative RuneLite observations. The activity label
# is deterministic metadata derived from those names; no computer-vision guessing.
_ENCOUNTERS: list[tuple[tuple[str,...],str,str]] = [
    (("great olm","olm"),"cox","Chambers of Xeric"),
    (("verzik","maiden of sugadinti","pestilent bloat","nylocas","sotetseg","xarpus"),"tob","Theatre of Blood"),
    (("akkha","ba-ba","baba","kephri","zebak","elidinis' warden","tumeken's warden","warden"),"toa","Tombs of Amascut"),
    (("tzkal-zuk","zuk"),"inferno","Inferno"),
    (("sol heredit","sol"),"colosseum","Fortis Colosseum"),
    (("corrupted hunllef",),"cg","Corrupted Gauntlet"),
    (("hunllef",),"gauntlet","Gauntlet"),
    (("nex",),"nex","Nex"),
    (("vorkath",),"vorkath","Vorkath"),
    (("zulrah",),"zulrah","Zulrah"),
    (("phantom muspah",),"muspah","Phantom Muspah"),
    (("araxxor",),"araxxor","Araxxor"),
    (("vardorvis",),"vardorvis","Vardorvis"),
    (("the leviathan","leviathan"),"leviathan","The Leviathan"),
    (("duke sucellus",),"duke","Duke Sucellus"),
    (("the whisperer","whisperer"),"whisperer","The Whisperer"),
    (("alchemical hydra",),"hydra","Alchemical Hydra"),
    (("cerberus",),"cerberus","Cerberus"),
    (("commander zilyana",),"sara","Commander Zilyana"),
    (("general graardor",),"bandos","General Graardor"),
    (("kree'arra","kreearra"),"arma","Kree'arra"),
    (("k'ril tsutsaroth","kril tsutsaroth"),"zammy","K'ril Tsutsaroth"),
    (("corporeal beast",),"corp","Corporeal Beast"),
    (("phosani",),"phosani","Phosani's Nightmare"),
    (("the nightmare","nightmare"),"nightmare","The Nightmare"),
    (("yama",),"yama","Yama"),
    (("royal titan",),"royal_titans","Royal Titans"),
    (("hueycoatl",),"hueycoatl","The Hueycoatl"),
]


def _clean(value: Any) -> str:
    return re.sub(r"<[^>]+>","",str(value or "")).strip()


def context_from_text(value: Any) -> dict[str,str]:
    low=_clean(value).lower()
    if not low: return {}
    # Raid names may appear in reward/chat text even when no NPC is targeted.
    explicit=(
        ("chambers of xeric","cox","Chambers of Xeric"),
        ("theatre of blood","tob","Theatre of Blood"),
        ("tombs of amascut","toa","Tombs of Amascut"),
        ("fortis colosseum","colosseum","Fortis Colosseum"),
        ("inferno","inferno","Inferno"),
    )
    for needle,key,activity in explicit:
        if needle in low:
            return {"activity_key":key,"activity":activity}
    for aliases,key,activity in _ENCOUNTERS:
        for alias in aliases:
            if alias in low:
                return {"activity_key":key,"activity":activity,"encounter":activity if key not in {"cox","tob","toa"} else _canonical_boss(low,key)}
    return {}


def _canonical_boss(low: str,key: str) -> str:
    if key=="cox" and "olm" in low: return "Great Olm"
    if key=="tob":
        for needle,name in (("verzik","Verzik Vitur"),("maiden","Maiden of Sugadinti"),("bloat","Pestilent Bloat"),("nylocas","Nylocas"),("sotetseg","Sotetseg"),("xarpus","Xarpus")):
            if needle in low: return name
    if key=="toa":
        for needle,name in (("akkha","Akkha"),("ba-ba","Ba-Ba"),("baba","Ba-Ba"),("kephri","Kephri"),("zebak","Zebak"),("warden","Wardens")):
            if needle in low: return name
    return ""


def _payload(event: dict[str,Any]) -> dict[str,Any]:
    raw=event.get("payload")
    return dict(raw) if isinstance(raw,dict) else {}


def _direct_context(event: dict[str,Any]) -> dict[str,str]:
    p=_payload(event)
    values=[p.get("target_name"),p.get("source"),p.get("name"),p.get("message"),p.get("raid_name"),event.get("summary")]
    for value in values:
        ctx=context_from_text(value)
        if ctx: return ctx
    return {}


def enrich_encounter_context(events: list[dict[str,Any]] | None, max_carry_seconds: float=45.0) -> list[dict[str,Any]]:
    """Attach deterministic activity/encounter context to nearby RuneLite events.

    A known current target can carry forward briefly to hits/deaths/reactions that
    lack their own NPC name. Reward/chat events with explicit raid text override it.
    """
    rows=sorted([dict(e) for e in (events or [])],key=lambda e:float(e.get("time",0) or 0))
    last_ctx:dict[str,str]={}; last_t=-1e9
    out=[]
    for event in rows:
        t=float(event.get("time",0) or 0)
        p=_payload(event)
        direct=_direct_context(event)
        if direct:
            last_ctx=direct; last_t=t
        ctx=direct or (dict(last_ctx) if last_ctx and t-last_t<=float(max_carry_seconds) else {})
        if ctx:
            for key,value in ctx.items():
                p.setdefault(key,value)
        event["payload"]=p
        out.append(event)
    return out
