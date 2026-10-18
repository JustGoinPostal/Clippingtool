from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
import numpy as np

from .media import require_ffmpeg
from .config import Settings


def _mean_abs(a: np.ndarray, b: np.ndarray) -> float:
    if a is None or b is None:
        return 0.0
    return float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean()) / 255.0


def _color_ratios(frame: np.ndarray) -> tuple[float,float,float]:
    r = frame[:, :, 0].astype(np.int16)
    g = frame[:, :, 1].astype(np.int16)
    b = frame[:, :, 2].astype(np.int16)
    purple = (r > 80) & (b > 90) & (r > g + 22) & (b > g + 24)
    gold = (r > 150) & (g > 105) & (g < r - 18) & (b < 100)
    red = (r > 145) & (r > g + 45) & (r > b + 40)
    return float(purple.mean()), float(gold.mean()), float(red.mean())


def _scan_window(path: Path, start: float, end: float, sample_seconds: float) -> list[dict]:
    width, height = 320, 180
    start=max(0.0,float(start)); end=max(start,float(end))
    span=end-start
    if span <= 0:
        return []
    fps=max(0.1,1.0/max(0.5,float(sample_seconds)))
    cmd=[
        "ffmpeg","-hide_banner","-loglevel","error",
        "-ss",f"{start:.3f}","-i",str(path),"-t",f"{span:.3f}",
        "-an","-vf",f"fps={fps},scale={width}:{height}",
        "-pix_fmt","rgb24","-f","rawvideo","-"
    ]
    proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    frame_bytes=width*height*3
    rows=[]; prev=None; index=0
    assert proc.stdout is not None
    while True:
        raw=proc.stdout.read(frame_bytes)
        if len(raw) != frame_bytes:
            break
        frame=np.frombuffer(raw,dtype=np.uint8).reshape((height,width,3)).copy()
        t=min(end,start+(index/fps))
        whole=_mean_abs(frame,prev)
        chat=frame[int(height*0.60):height,0:int(width*0.62)]
        prev_chat=None if prev is None else prev[int(height*0.60):height,0:int(width*0.62)]
        inv=frame[int(height*0.18):int(height*0.94),int(width*0.74):width]
        prev_inv=None if prev is None else prev[int(height*0.18):int(height*0.94),int(width*0.74):width]
        center=frame[int(height*0.22):int(height*0.78),int(width*0.18):int(width*0.78)]
        prev_center=None if prev is None else prev[int(height*0.22):int(height*0.78),int(width*0.18):int(width*0.78)]
        purple,gold,red=_color_ratios(frame)
        rows.append({
            "time":round(float(t),3),
            "visual_change":round(whole,6),
            "chat_change":round(_mean_abs(chat,prev_chat),6),
            "ui_change":round(_mean_abs(inv,prev_inv),6),
            "center_change":round(_mean_abs(center,prev_center),6),
            "purple_ratio":round(purple,6),
            "gold_ratio":round(gold,6),
            "red_ratio":round(red,6),
        })
        prev=frame; index+=1
    proc.stdout.close()
    stderr=b""
    if proc.stderr is not None:
        stderr=proc.stderr.read()
    rc=proc.wait(timeout=30)
    if rc != 0:
        raise RuntimeError(f"ffmpeg visual scan failed ({rc}): {stderr.decode(errors='replace')[-800:]}")
    return rows


def _normalize_windows(windows: list[dict[str, Any]] | None, duration: float) -> list[tuple[float,float]]:
    if not windows:
        return []
    out=[]
    for row in windows:
        start=max(0.0,min(duration,float(row.get("start",0.0) or 0.0)))
        end=max(start,min(duration,float(row.get("end",start) or start)))
        if end-start >= 0.25:
            out.append((start,end))
    out.sort()
    merged=[]
    for start,end in out:
        if merged and start <= merged[-1][1] + 0.05:
            merged[-1]=(merged[-1][0],max(merged[-1][1],end))
        else:
            merged.append((start,end))
    return merged


def analyze_video(
    path: Path,
    duration: float,
    s: Settings,
    windows: list[dict[str, Any]] | None = None,
) -> list[dict]:
    if not s.video_analysis_enabled or duration <= 0:
        return []
    require_ffmpeg()
    targeted=_normalize_windows(windows,duration)
    if not targeted:
        return _scan_window(path,0.0,duration,float(s.video_sample_seconds))

    rows=[]
    for start,end in targeted:
        rows.extend(_scan_window(path,start,end,float(s.video_sample_seconds)))

    # Windows are already merged, but seek rounding can still produce duplicate timestamps.
    # Prefer the later row so targeted rescans remain deterministic.
    dedup={round(float(row.get("time",0.0)),3):row for row in rows}
    return [dedup[key] for key in sorted(dedup)]
