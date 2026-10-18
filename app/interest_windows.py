from __future__ import annotations

import math
import statistics
from typing import Any

from .config import Settings
from .osrs_events import event_strength, normalize_event_type


def _split_long_window(row: dict[str, Any], max_seconds: float) -> list[dict[str, Any]]:
    start=float(row["start"]); end=float(row["end"])
    max_seconds=max(10.0,float(max_seconds))
    if end-start <= max_seconds:
        return [row]
    out=[]; cursor=start
    while cursor < end:
        chunk_end=min(end,cursor+max_seconds)
        x=dict(row); x["start"]=cursor; x["end"]=chunk_end
        out.append(x)
        cursor=chunk_end
    return out


def _merge_windows(
    windows: list[dict[str, Any]],
    duration: float,
    gap: float,
    limit: int,
    max_window_seconds: float,
) -> list[dict[str, Any]]:
    if not windows or duration <= 0:
        return []
    normalized=[]
    for row in windows:
        start=max(0.0,min(duration,float(row.get("start",0.0) or 0.0)))
        end=max(start,min(duration,float(row.get("end",start) or start)))
        if end-start < 0.25:
            continue
        normalized.append({
            "start":start,
            "end":end,
            "priority":float(row.get("priority",0.0) or 0.0),
            "sources":set(row.get("sources") or []),
        })
    if not normalized:
        return []
    normalized.sort(key=lambda x:(x["start"],x["end"]))
    merged=[]
    for row in normalized:
        if merged and row["start"] <= merged[-1]["end"] + gap:
            merged[-1]["end"]=max(merged[-1]["end"],row["end"])
            merged[-1]["priority"]=max(merged[-1]["priority"],row["priority"])
            merged[-1]["sources"].update(row["sources"])
        else:
            merged.append(row)

    bounded=[]
    for row in merged:
        bounded.extend(_split_long_window(row,max_window_seconds))
    merged=bounded

    if len(merged) > limit:
        keep=sorted(merged,key=lambda x:(x["priority"],x["end"]-x["start"]),reverse=True)[:limit]
        merged=sorted(keep,key=lambda x:x["start"])
    return [
        {
            "start":round(x["start"],3),
            "end":round(x["end"],3),
            "priority":round(x["priority"],2),
            "sources":sorted(x["sources"]),
        }
        for x in merged
    ]


def _runelite_candidates(game_events: list[dict], duration: float, s: Settings) -> list[dict[str, Any]]:
    ranked=[]
    for ev in game_events:
        typ=normalize_event_type(ev.get("event_type",""),ev.get("payload") or {})
        if typ.startswith("bridge_"):
            continue
        t=float(ev.get("time",0.0) or 0.0)
        if not (0.0 <= t <= duration):
            continue
        strength=float(ev.get("strength",event_strength(ev)) or 0.0)
        ranked.append((strength,t,typ,ev))
    ranked.sort(reverse=True,key=lambda x:x[0])

    chosen=[]; seen=[]
    max_events=max(60,int(s.max_candidates)*5)
    for strength,t,typ,ev in ranked:
        if any(typ==seen_type and abs(t-seen_t)<2.5 for seen_t,seen_type in seen):
            continue
        seen.append((t,typ)); chosen.append((strength,t,typ,ev))
        if len(chosen)>=max_events:
            break
    return [
        {"strength":strength,"time":t,"type":typ,"event":ev}
        for strength,t,typ,ev in chosen
    ]


def build_interest_windows(
    transcript: dict,
    energy: list[tuple[float,float]],
    game_events: list[dict],
    duration: float,
    s: Settings,
) -> list[dict[str, Any]]:
    """Build dense-analysis windows around exact game events and human reactions.

    RuneLite events get the highest priority. Strong audio reactions and speech segments
    containing configured highlight keywords are also included so funny/personality
    moments can still be discovered even when the game itself did not emit an event.
    """
    if duration <= 0:
        return []

    pre=max(2.0,float(s.targeted_video_pre_seconds))
    post=max(4.0,float(s.targeted_video_post_seconds))
    windows: list[dict[str, Any]]=[]

    for row in _runelite_candidates(game_events,duration,s):
        t=float(row["time"]); typ=str(row["type"]); strength=float(row["strength"])
        # Frequent hits need less context than a kill, death, unique, or raid reward.
        if typ in {"big_hit","big_hit_taken"}:
            ev_pre=min(pre,8.0); ev_post=min(post,12.0)
        elif typ in {"npc_loot","loot"}:
            ev_pre=min(pre,10.0); ev_post=min(post,16.0)
        else:
            ev_pre=pre; ev_post=post
        windows.append({
            "start":t-ev_pre,
            "end":t+ev_post,
            "priority":100.0+strength,
            "sources":["runelite",typ],
        })

    finite=[float(v) for _,v in energy if math.isfinite(float(v)) and float(v)>-120]
    if finite:
        mean=statistics.mean(finite)
        std=max(statistics.pstdev(finite),3.0)
        ranked=[]
        for t,v in energy:
            v=float(v)
            if not math.isfinite(v):
                continue
            z=(v-mean)/std
            if z >= float(s.targeted_video_audio_z):
                ranked.append((z,float(t)))
        ranked.sort(reverse=True)
        chosen=[]
        for z,t in ranked:
            if any(abs(t-x)<6.0 for x in chosen):
                continue
            chosen.append(t)
            windows.append({
                "start":t-min(pre,10.0),
                "end":t+min(post,18.0),
                "priority":45.0+z*6.0,
                "sources":["audio_reaction"],
            })
            if len(chosen) >= max(12,int(s.max_candidates)*2):
                break

    keyword_rows=[]
    for seg in transcript.get("segments",[]):
        text=str(seg.get("text","") or "").lower()
        score=0.0
        for phrase,weight in s.keywords.items():
            if phrase.lower() in text:
                score+=float(weight)
        if score <= 0:
            continue
        start=float(seg.get("start",0.0) or 0.0)
        end=float(seg.get("end",start) or start)
        mid=(start+end)/2.0
        keyword_rows.append((score,mid))
    keyword_rows.sort(reverse=True)
    for score,t in keyword_rows[:max(12,int(s.max_candidates)*2)]:
        windows.append({
            "start":t-min(pre,9.0),
            "end":t+min(post,16.0),
            "priority":35.0+min(35.0,score),
            "sources":["speech_keyword"],
        })

    return _merge_windows(
        windows,
        duration,
        max(0.0,float(s.targeted_video_merge_gap_seconds)),
        max(1,int(s.targeted_video_max_windows)),
        max(10.0,float(s.targeted_video_max_window_seconds)),
    )


def window_coverage_seconds(windows: list[dict[str, Any]]) -> float:
    return round(sum(max(0.0,float(w.get("end",0))-float(w.get("start",0))) for w in windows),3)
