from __future__ import annotations
import json
import httpx
from .config import Settings


def _clean_title(x: str) -> str:
    x=" ".join(str(x or "").replace("\n"," ").split()).strip(' "')
    return x[:90]


def local_ai_second_pass(candidates: list[dict], s: Settings) -> list[dict]:
    if not s.ollama_model or not candidates:
        return candidates
    payload=[]
    for i,c in enumerate(candidates[:20]):
        payload.append({
            "id":i,"event_type":c.get("event_type"),"score":c.get("score"),
            "reason":c.get("reason"),"transcript":(c.get("transcript") or "")[:1000]
        })
    prompt=(
        "You rank short-form clips from an Old School RuneScape gaming stream. "
        "Judge whether a stranger could understand the setup/payoff and whether the moment has a strong hook, emotion, comedy, surprise, PvP payoff, or valuable-drop payoff. "
        "Do not reward ordinary gameplay. Return ONLY JSON as an object with key 'clips'. "
        "Each item must contain id (integer), virality (0-100 integer), and title (short punchy title <= 70 chars). "
        "Input:\n"+json.dumps(payload,ensure_ascii=False)
    )
    try:
        r=httpx.post(s.ollama_url.rstrip("/")+"/api/generate",json={
            "model":s.ollama_model,"prompt":prompt,"format":"json","stream":False,
            "options":{"temperature":0.2}
        },timeout=120.0)
        r.raise_for_status(); raw=r.json().get("response","")
        data=json.loads(raw); items=data.get("clips",[]) if isinstance(data,dict) else []
        by_id={int(x.get("id")) : x for x in items if isinstance(x,dict) and str(x.get("id","")).isdigit()}
        for i,c in enumerate(candidates[:20]):
            x=by_id.get(i)
            if not x: continue
            try: v=max(0,min(100,int(x.get("virality",50))))
            except Exception: v=50
            c["ai_virality"]=v
            c["score"]=round(float(c["score"])+(v-50)*0.22,1)
            c["reason"]=(c.get("reason","")+f"; local AI {v}/100").strip("; ")
            title=_clean_title(x.get("title",""))
            if title: c["ai_title"]=title
        candidates.sort(key=lambda c:float(c.get("score",0)),reverse=True)
    except Exception:
        return candidates
    return candidates
