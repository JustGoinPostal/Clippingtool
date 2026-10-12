from __future__ import annotations

import math

HIGH_PAYOFF={"pvp","pvp_kill","player_loot","raid_reward","rare_drop","collection_log","big_hit","raid_complete"}
GAMEPLAY_TYPES=HIGH_PAYOFF|{"drop","loot","npc_loot","combat","death","player_death"}


def _clamp(x: float, lo: float=0.0, hi: float=100.0) -> float:
    return max(lo,min(hi,float(x)))


def _word_stats(words: list[dict], start: float, end: float) -> tuple[int,float,float]:
    rel=[w for w in words if float(w.get("end",0))>=start and float(w.get("start",0))<=end]
    if not rel:
        return 0,0.0,0.0
    spoken=0.0
    for w in rel:
        a=max(start,float(w.get("start",0))); b=min(end,float(w.get("end",0)))
        spoken += max(0.0,b-a)
    dur=max(0.01,end-start)
    return len(rel),len(rel)/dur,min(1.0,spoken/dur)


def evaluate_render(clip: dict, words: list[dict], render_result: dict, hook_text: str) -> dict:
    """Score a finished render using its final timing/content signals.

    This is deterministic local quality control. It does not claim to predict actual views.
    """
    start=float(render_result["start"]); end=float(render_result["end"])
    dur=max(0.01,end-start)
    event=str(clip.get("event_type") or "speech").lower()
    count,wps,speech_ratio=_word_stats(words,start,end)
    base=_clamp(float(clip.get("score",0) or 0))

    # Prefer hooks that are short enough to read instantly.
    hook_len=len((hook_text or "").strip())
    hook=100.0 if 10<=hook_len<=38 else 82.0 if 6<=hook_len<=52 else 58.0

    # Speech-heavy clips generally feel best around 2-3.5 words/sec. Gameplay clips are allowed to breathe.
    target=2.45 if event not in GAMEPLAY_TYPES else 1.35
    spread=1.8 if event not in GAMEPLAY_TYPES else 2.0
    pacing=100.0*math.exp(-((wps-target)/spread)**2) if count else (78.0 if event in GAMEPLAY_TYPES else 35.0)

    # Shorts sweet spot heuristic: reward concise clips while keeping longer context viable.
    if 18<=dur<=42: length_fit=100.0
    elif 12<=dur<18 or 42<dur<=55: length_fit=88.0
    elif 8<=dur<12 or 55<dur<=65: length_fit=72.0
    else: length_fit=54.0

    payoff=96.0 if event in HIGH_PAYOFF else 84.0 if event in GAMEPLAY_TYPES else min(92.0,58.0+base*0.35)
    context=min(100.0,52.0+base*0.42+(10.0 if dur>=20 else 0.0))

    if event in GAMEPLAY_TYPES:
        dead_air=max(65.0,100.0-(max(0.0,0.08-speech_ratio)*180.0))
    else:
        dead_air=_clamp(42.0+speech_ratio*90.0)

    focus=92.0 if render_result.get("focus") in {"combat","chat","ui","center"} else 72.0
    total=(hook*0.16+pacing*0.16+length_fit*0.14+payoff*0.21+context*0.15+dead_air*0.10+focus*0.08)
    total=_clamp(total)
    return {
        "score":round(total,1),
        "hook":round(hook,1),
        "pacing":round(_clamp(pacing),1),
        "length_fit":round(length_fit,1),
        "payoff":round(payoff,1),
        "context":round(_clamp(context),1),
        "dead_air":round(_clamp(dead_air),1),
        "focus":round(focus,1),
        "duration":round(dur,2),
        "words":count,
        "words_per_second":round(wps,2),
        "speech_ratio":round(speech_ratio,3),
    }
