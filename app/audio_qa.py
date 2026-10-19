from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from .media import require_ffmpeg


def saturation_stats_from_pcm(raw: bytes, *, near_fullscale: int=32600, hard_fullscale: int=32760) -> dict[str,Any]:
    """Measure finished-audio samples pinned near integer full scale.

    This is evidence of digital saturation, not a semantic judgment about whether a
    creator intentionally used a limiter. The release gate therefore keeps a broad
    warning band and blocks only sustained/severe saturation.
    """
    usable=(len(raw)//2)*2
    if usable<=0:
        return {
            "sample_count":0,"max_abs":0,"near_fullscale_samples":0,"hard_fullscale_samples":0,
            "near_fullscale_ratio":0.0,"hard_fullscale_ratio":0.0,"longest_hard_run":0,
        }
    samples=np.frombuffer(raw[:usable],dtype="<i2").astype(np.int32,copy=False)
    absolute=np.abs(samples)
    near=absolute>=int(near_fullscale)
    hard=absolute>=int(hard_fullscale)
    longest=0; current=0
    for value in hard:
        if bool(value):
            current+=1; longest=max(longest,current)
        else:
            current=0
    n=int(samples.size)
    near_count=int(np.count_nonzero(near)); hard_count=int(np.count_nonzero(hard))
    return {
        "sample_count":n,
        "max_abs":int(absolute.max(initial=0)),
        "near_fullscale_samples":near_count,
        "hard_fullscale_samples":hard_count,
        "near_fullscale_ratio":round(near_count/max(1,n),7),
        "hard_fullscale_ratio":round(hard_count/max(1,n),7),
        "longest_hard_run":int(longest),
    }


def pcm_saturation_stats(path: Path, duration: float) -> dict[str,Any]:
    """Decode the actual finished MP4 audio to signed PCM and inspect saturation."""
    require_ffmpeg()
    limit=max(0.8,min(66.0,float(duration or 0)))
    cmd=[
        "ffmpeg","-hide_banner","-nostats","-v","error","-i",str(path),
        "-t",f"{limit:.3f}","-vn","-map","0:a:0","-c:a","pcm_s16le","-f","s16le","pipe:1",
    ]
    result=subprocess.run(cmd,capture_output=True,timeout=max(45.0,limit*2.0+20.0),check=False)
    if result.returncode!=0:
        err=(result.stderr or b"").decode("utf-8",errors="replace")[-2000:]
        raise RuntimeError(f"PCM saturation decode failed: {err.strip()}")
    return saturation_stats_from_pcm(result.stdout)
