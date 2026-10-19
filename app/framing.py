from __future__ import annotations

from typing import Any


def _finite_ratio(value: Any) -> float | None:
    try:
        x=float(value)
    except (TypeError,ValueError):
        return None
    if x != x or x in (float("inf"),float("-inf")):
        return None
    return max(0.0,min(1.0,x))


def build_focus_keyframes(game_events: list[dict] | None, start: float, end: float) -> list[dict[str,float]]:
    """Return de-duplicated RuneLite focus points for one rendered clip.

    Event times are recording-relative. Output times are clip-relative so they can be
    used directly by FFmpeg expressions after the input seek. bridge_focus samples
    provide motion continuity; exact gameplay events provide authoritative anchors.
    """
    if not game_events or end <= start:
        return []
    rows=[]
    for ev in game_events:
        t=float(ev.get("time",0.0) or 0.0)
        if t < start-2.0 or t > end+2.0:
            continue
        payload=ev.get("payload") or {}
        x=_finite_ratio(payload.get("focus_x_ratio"))
        y=_finite_ratio(payload.get("focus_y_ratio"))
        if x is None:
            continue
        typ=str(ev.get("event_type") or "")
        exact=0 if typ.startswith("bridge_") else 1
        rows.append({
            "time":max(0.0,min(end-start,t-start)),
            "x":x,
            "y":0.5 if y is None else y,
            "exact":float(exact),
        })
    if not rows:
        return []

    rows.sort(key=lambda r:(r["time"],-r["exact"]))
    dedup=[]
    for row in rows:
        if dedup and abs(row["time"]-dedup[-1]["time"]) < 0.18:
            # Prefer an exact kill/hit/drop anchor over a periodic bridge sample.
            if row["exact"] >= dedup[-1]["exact"]:
                dedup[-1]=row
            continue
        dedup.append(row)

    # Remove near-identical consecutive points so the FFmpeg expression remains small.
    compact=[]
    for row in dedup:
        if compact and abs(row["x"]-compact[-1]["x"]) < 0.012 and row["time"]-compact[-1]["time"] < 2.5:
            if row["exact"] > compact[-1]["exact"]:
                compact[-1]=row
            continue
        compact.append(row)
    return compact[:120]


def focus_ratio_expression(keyframes: list[dict[str,float]]) -> str:
    """Build a smooth piecewise-linear FFmpeg expression for horizontal focus."""
    if not keyframes:
        return "0.5"
    if len(keyframes)==1:
        return f"{float(keyframes[0]['x']):.6f}"

    def segment(i: int) -> str:
        a=keyframes[i]; b=keyframes[i+1]
        t0=float(a["time"]); t1=float(b["time"]); x0=float(a["x"]); x1=float(b["x"])
        dt=max(0.001,t1-t0)
        interp=f"({x0:.6f}+({x1-x0:.6f})*max(0,min(1,(t-{t0:.3f})/{dt:.3f})))"
        if i==len(keyframes)-2:
            return f"if(lt(t,{t1:.3f}),{interp},{x1:.6f})"
        return f"if(lt(t,{t1:.3f}),{interp},{segment(i+1)})"

    first=keyframes[0]
    body=segment(0)
    if float(first["time"]) > 0.001:
        body=f"if(lt(t,{float(first['time']):.3f}),{float(first['x']):.6f},{body})"
    return body


def crop_x_expression(keyframes: list[dict[str,float]]) -> str:
    """Center a vertical crop on the RuneLite focus ratio while clamping to source bounds."""
    ratio=focus_ratio_expression(keyframes)
    return f"max(0,min(iw-ow,iw*({ratio})-ow/2))"
