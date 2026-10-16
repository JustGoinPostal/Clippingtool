from __future__ import annotations
import math, statistics, re
from .config import Settings
from .learning import preference_bonus
from .osrs_events import normalize_event_type, event_strength, summarize_event


def _energy_at(samples, t, radius=4.0):
    vals=[v for ts,v in samples if abs(ts-t)<=radius and math.isfinite(v)]
    return statistics.mean(vals) if vals else -60.0


def _z_energy(samples):
    vals=[v for _,v in samples if math.isfinite(v) and v > -120]
    if not vals: return -45.0, 8.0
    return statistics.mean(vals), max(statistics.pstdev(vals),3.0)


def _clip_text(segments,start,end):
    return " ".join(s["text"] for s in segments if s["end"]>=start and s["start"]<=end).strip()


def _keyword_score(text, keywords):
    low=text.lower(); total=0; hits=[]
    for phrase,weight in keywords.items():
        count=low.count(phrase.lower())
        if count:
            total += float(weight)*min(count,2); hits.append(phrase)
    return total,hits


def _iou(a,b):
    inter=max(0,min(a[1],b[1])-max(a[0],b[0])); union=max(a[1],b[1])-min(a[0],b[0])
    return inter/union if union else 0


def _text_similarity(a: str, b: str) -> float:
    wa=set(re.findall(r"[a-z0-9']+",a.lower())); wb=set(re.findall(r"[a-z0-9']+",b.lower()))
    if not wa or not wb: return 0.0
    return len(wa & wb) / max(1, len(wa | wb))


def _stats(rows, key):
    vals=[float(r.get(key,0)) for r in rows if math.isfinite(float(r.get(key,0)))]
    if not vals: return 0.0, 1.0
    return statistics.mean(vals), max(statistics.pstdev(vals), 0.002)


def _visual_at(rows, t, radius):
    near=[r for r in rows if abs(float(r.get("time",0))-t)<=radius]
    if not near:
        return {"visual_change":0.0,"chat_change":0.0,"ui_change":0.0,"center_change":0.0,"purple_ratio":0.0,"gold_ratio":0.0,"red_ratio":0.0}
    return {k:max(float(x.get(k,0)) for x in near) for k in ("visual_change","chat_change","ui_change","center_change","purple_ratio","gold_ratio","red_ratio")}


def _smart_window(segs, t: float, total: float, s: Settings):
    if not s.smart_boundaries or not segs:
        start=max(0,t-s.pre_roll_seconds); end=min(total,max(t+s.post_roll_seconds,start+s.default_clip_seconds))
        return start,min(end,start+75)
    idx=min(range(len(segs)), key=lambda i: abs(((segs[i]["start"]+segs[i]["end"])/2)-t))
    nearest=segs[idx]
    dist=0.0 if float(nearest["start"]) <= t <= float(nearest["end"]) else min(abs(t-float(nearest["start"])),abs(t-float(nearest["end"])))
    if dist > 12.0:
        start=max(0.0,t-s.pre_roll_seconds); end=min(total,max(t+s.post_roll_seconds,start+s.default_clip_seconds))
        return start,min(end,start+75)
    left=idx; right=idx
    while left>0:
        gap=float(segs[left]["start"])-float(segs[left-1]["end"])
        if gap >= 1.15 or t-float(segs[left-1]["start"]) > 20: break
        left-=1
    while right<len(segs)-1:
        gap=float(segs[right+1]["start"])-float(segs[right]["end"])
        if gap >= 1.35 or float(segs[right+1]["end"])-t > 38: break
        right+=1
    start=max(0.0,float(segs[left]["start"])-2.0)
    end=min(total,float(segs[right]["end"])+2.5)
    if end-start < 22:
        start=max(0.0,min(start,t-10)); end=min(total,max(end,t+16))
    if end-start > 70: end=start+70
    return start,end


def _classify(text: str, hits: list[str], f: dict, z: dict) -> tuple[str,list[str]]:
    low=text.lower(); tags=[]
    if f["purple"] > 0.45 or z.get("purple",0)>1.5: tags.append("purple/reward visual")
    if z.get("chat",0)>1.4: tags.append("chatbox spike")
    if z.get("ui",0)>1.4: tags.append("inventory/UI change")
    if z.get("center",0)>1.5: tags.append("center-screen popup/change")
    if z.get("gold",0)>1.6: tags.append("gold/reward color burst")
    if z.get("red",0)>1.8: tags.append("red/damage color burst")
    if z.get("visual",0)>1.6: tags.append("gameplay action spike")
    if f["audio"]>0.55: tags.append("audio reaction")
    if any(x in low for x in ("smite","pk","pker","killed","kill","clapped","spec")):
        return "pvp",tags
    if any(x in low for x in ("purple","drop","unique","rare","tbow","twisted bow","scythe","shadow","pet")) or f["purple"]>0.45:
        return "drop",tags
    if any(x in low for x in ("dead","died","death")):
        return "death",tags
    if any(x in low for x in ("no way","oh my god","what the","bro","dude","walk on")):
        return "reaction",tags
    if z.get("chat",0)>1.4: return "chat",tags
    if z.get("visual",0)>1.6 or z.get("ui",0)>1.5: return "gameplay",tags
    return "speech",tags


def make_candidates(transcript: dict, energy: list[tuple[float,float]], total_duration: float, s: Settings,
                    video: list[dict] | None = None, learned: dict[str,float] | None = None,
                    game_events: list[dict] | None = None):
    segs=transcript.get("segments",[]); video=video or []; learned=learned or {}; game_events=game_events or []
    mean,std=_z_energy(energy); candidates=[]
    vstats={k:_stats(video,k) for k in ("visual_change","chat_change","ui_change","center_change","purple_ratio","gold_ratio","red_ratio")}

    def build(seed_t: float, source: str, extra: float=0.0, exact_event: dict | None = None):
        start,end=_smart_window(segs,seed_t,total_duration,s)
        text=_clip_text(segs,start,end)
        kw,hits=_keyword_score(text,s.keywords)
        words=len(re.findall(r"\w+",text)); density=words/max(end-start,1)
        e=_energy_at(energy,seed_t); ez=(e-mean)/std
        vis=_visual_at(video,seed_t,max(2.5,float(s.video_sample_seconds)*1.6))
        z={
            "visual":(vis["visual_change"]-vstats["visual_change"][0])/vstats["visual_change"][1],
            "chat":(vis["chat_change"]-vstats["chat_change"][0])/vstats["chat_change"][1],
            "ui":(vis["ui_change"]-vstats["ui_change"][0])/vstats["ui_change"][1],
            "center":(vis["center_change"]-vstats["center_change"][0])/vstats["center_change"][1],
            "purple":(vis["purple_ratio"]-vstats["purple_ratio"][0])/vstats["purple_ratio"][1],
            "gold":(vis["gold_ratio"]-vstats["gold_ratio"][0])/vstats["gold_ratio"][1],
            "red":(vis["red_ratio"]-vstats["red_ratio"][0])/vstats["red_ratio"][1],
        }
        exact_type = normalize_event_type((exact_event or {}).get("event_type", ""), (exact_event or {}).get("payload") or {}) if exact_event else ""
        exact_strength = event_strength(exact_event) if exact_event else 0.0
        positive_signals=[max(0.0,ez),max(0.0,z["visual"]),max(0.0,z["center"]),max(0.0,z["red"]),max(0.0,z["purple"]),max(0.0,z["gold"])]
        signal_hits=sum(1 for value in positive_signals if value>=1.0)
        synergy=max(0.0,(signal_hits-1)*2.6)
        features={
            "keyword":min(1.0,kw/45.0),
            "audio":min(1.0,max(0.0,ez)/3.0),
            "speech_density":min(1.0,max(0.0,density-1.2)/2.5),
            "visual_change":min(1.0,max(0.0,z["visual"])/3.0),
            "chat_change":min(1.0,max(0.0,z["chat"])/3.0),
            "ui_change":min(1.0,max(0.0,z["ui"])/3.0),
            "purple":min(1.0,max(max(0.0,z["purple"])/3.0, vis["purple_ratio"]/0.035)),
            "center_change":min(1.0,max(0.0,z["center"])/3.0),
            "gold":min(1.0,max(max(0.0,z["gold"])/3.0, vis["gold_ratio"]/0.04)),
            "red":min(1.0,max(max(0.0,z["red"])/3.0, vis["red_ratio"]/0.04)),
            "punctuation":1.0 if any(ch in text for ch in "!?") else 0.0,
            "runelite_event": min(1.0, exact_strength / 55.0),
            "multi_signal":min(1.0,signal_hits/4.0),
        }
        base=(14 + kw + max(0,ez)*9 + max(0,density-1.7)*7 +
              max(0,z["visual"])*5 + max(0,z["chat"])*6 + max(0,z["ui"])*4 +
              max(0,z["center"])*4 + max(0,z["purple"])*8 + max(0,z["gold"])*5 +
              max(0,z["red"])*3 + features["punctuation"]*3 + extra + exact_strength + synergy)
        personal=preference_bonus(features,learned)
        event_type,tags=_classify(text,hits,features,z)
        event_summary=""
        if exact_event:
            event_type = exact_type or event_type
            event_summary=summarize_event(exact_event)
            tags.insert(0, event_summary)
        reason=[]
        if hits: reason.append("keywords: "+", ".join(hits[:5]))
        if ez>0.8: reason.append(f"audio +{ez:.1f}σ")
        if signal_hits>=2: reason.append(f"{signal_hits} excitement signals aligned")
        reason.extend(tags[:4])
        if density>2.2: reason.append("fast speech")
        if abs(personal)>=0.7: reason.append(f"your taste {personal:+.1f}")
        if source != "speech": reason.append(source)
        if exact_event and exact_event.get("payload"):
            p = exact_event.get("payload") or {}
            if p.get("amount") is not None and event_type == "big_hit": reason.append(f"{p.get('amount')} damage")
        return {
            "start":round(start,2),"end":round(end,2),"score":round(min(100.0,base+personal),1),
            "base_score":round(min(100.0,base),1),"personal_score":round(personal,1),
            "reason":"; ".join(reason) or "speech moment","transcript":text,
            "event_type":event_type,"features":features,"event_summary":event_summary,
        }

    exact_ranked=sorted(game_events,key=lambda e:float(e.get("strength",event_strength(e)) or 0),reverse=True)
    exact_keep=[]
    for ev in exact_ranked:
        t=float(ev.get("time",0) or 0)
        if not (0 <= t <= total_duration): continue
        typ=normalize_event_type(ev.get("event_type",""),ev.get("payload") or {})
        if typ.startswith("bridge_"): continue
        if any(abs(t-float(k.get("time",0))) < 2.2 and typ == normalize_event_type(k.get("event_type",""),k.get("payload") or {}) for k in exact_keep):
            continue
        exact_keep.append(ev)
        if len(exact_keep) >= max(60,s.max_candidates*5): break
    for ev in exact_keep:
        t=float(ev.get("time",0) or 0)
        strength=float(ev.get("strength", event_strength(ev)) or 0)
        candidates.append(build(t,"RuneLite exact event",extra=min(24.0,strength*0.25),exact_event=ev))

    for seg in segs:
        mid=(float(seg["start"])+float(seg["end"]))/2
        candidates.append(build(mid,"speech"))

    ranked=sorted(energy,key=lambda x:x[1],reverse=True)[:max(24,s.max_candidates*3)]
    for t,e in ranked:
        ez=(e-mean)/std
        if ez >= 1.2: candidates.append(build(float(t),"audio peak",extra=8+ez*3))

    if video:
        for key,label,min_z in (
            ("visual_change","gameplay visual spike",1.7),
            ("chat_change","chatbox activity spike",1.55),
            ("ui_change","inventory/UI spike",1.65),
            ("center_change","center-screen change",1.75),
            ("purple_ratio","purple/reward visual",1.35),
            ("gold_ratio","gold/reward color burst",1.65),
            ("red_ratio","red/damage color burst",1.9),
        ):
            mu,sd=vstats[key]
            ranked_v=sorted(video,key=lambda r:float(r.get(key,0)),reverse=True)[:max(16,s.max_candidates*2)]
            for row in ranked_v:
                z=(float(row.get(key,0))-mu)/sd
                if z>=min_z:
                    candidates.append(build(float(row["time"]),label,extra=min(18,z*4)))

        # Shorts usually feel strongest when several signals hit together. Seed candidates
        # where motion, a reaction/audio spike, and damage/reward/UI changes coincide.
        burst_rows=[]
        for row in video:
            t=float(row.get("time",0) or 0)
            ez=(_energy_at(energy,t,2.5)-mean)/std
            zvals={key:(float(row.get(key,0))-vstats[key][0])/vstats[key][1]
                   for key in ("visual_change","chat_change","ui_change","center_change","purple_ratio","gold_ratio","red_ratio")}
            action=max(0.0,zvals["visual_change"],zvals["center_change"],zvals["red_ratio"],
                       zvals["purple_ratio"],zvals["gold_ratio"],
                       zvals["chat_change"]*0.85,zvals["ui_change"]*0.85)
            secondary=sorted([max(0.0,ez),max(0.0,zvals["visual_change"]),max(0.0,zvals["center_change"]),
                              max(0.0,zvals["red_ratio"]),max(0.0,zvals["purple_ratio"]),max(0.0,zvals["gold_ratio"])],reverse=True)
            multi_bonus=sum(1 for x in secondary if x>=1.0)*0.65
            combined=action+max(0.0,ez)*0.80+multi_bonus
            if combined>=2.65:
                burst_rows.append((combined,t))
        burst_rows.sort(reverse=True)
        selected=[]
        for combined,t in burst_rows:
            if any(abs(t-prev)<4.0 for prev in selected):
                continue
            selected.append(t)
            candidates.append(build(t,"multi-signal dynamic moment",extra=min(30.0,combined*6.2)))
            if len(selected)>=max(12,s.max_candidates*2):
                break

    candidates.sort(key=lambda x:x["score"],reverse=True)
    keep=[]; counts={}
    for c in candidates:
        duplicate=False
        for k in keep:
            if _iou((c["start"],c["end"]),(k["start"],k["end"]))>0.42:
                duplicate=True; break
            if abs(c["start"]-k["start"])<20 and _text_similarity(c["transcript"],k["transcript"])>0.72:
                duplicate=True; break
        if duplicate: continue
        typ=c["event_type"]
        if counts.get(typ,0) >= max(2,int(s.diversity_per_type)): continue
        counts[typ]=counts.get(typ,0)+1
        keep.append(c)
        if len(keep)>=s.max_candidates: break
    return keep
