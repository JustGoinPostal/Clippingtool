from __future__ import annotations

import subprocess
from pathlib import Path

from .config import ROOT
from .media import require_ffmpeg

COMBAT_TYPES={"pvp","pvp_kill","death","player_death","big_hit","combat","player_loot","boss_kill"}
REWARD_TYPES={"drop","rare_drop","raid_reward","raid_complete","collection_log","loot","npc_loot"}


def select_cover_ms(clip: dict, render: dict) -> int:
    """Pick a representative frame within the final rendered clip."""
    duration=max(0.2,float(render.get("render_end",0))-float(render.get("render_start",0)))
    event=str(clip.get("event_type") or "").lower()
    if event in COMBAT_TYPES:
        frac=0.58
    elif event in REWARD_TYPES:
        frac=0.64
    elif event in {"reaction","chat"}:
        frac=0.44
    else:
        frac=0.52
    seconds=max(0.25,min(duration-0.15,duration*frac))
    return max(0,int(round(seconds*1000)))


def cover_path(render_id: int) -> Path:
    p=ROOT/"data"/"covers"/f"{int(render_id)}.jpg"
    p.parent.mkdir(parents=True,exist_ok=True)
    return p


def ensure_cover(render: dict, clip: dict|None=None) -> tuple[Path,int]:
    path=cover_path(int(render["id"]))
    clip=clip or {}
    cover_ms=select_cover_ms(clip,render)
    if path.exists() and path.stat().st_size>0:
        return path,cover_ms
    source=Path(render["output_path"])
    if not source.exists():
        raise FileNotFoundError(source)
    require_ffmpeg()
    subprocess.run([
        "ffmpeg","-hide_banner","-loglevel","error","-y",
        "-ss",f"{cover_ms/1000:.3f}","-i",str(source),
        "-frames:v","1","-q:v","2",str(path)
    ],check=True)
    return path,cover_ms
