from __future__ import annotations
import json, subprocess
from pathlib import Path
from .config import Settings
from .media import require_ffmpeg
from .captions import write_ass

SPEECHY_TYPES={"speech","reaction","chat"}
COMBAT_TYPES={"pvp","pvp_kill","death","player_death","big_hit","combat","player_loot","boss_kill"}
REWARD_TYPES={"drop","rare_drop","raid_reward","raid_complete","collection_log","loot","npc_loot"}

def _ffmpeg_filter_path(p: Path):
    x=str(p.resolve()).replace("\\","/")
    return x.replace(":","\\:").replace("'","\\'")

def _features(clip: dict) -> dict:
    raw=clip.get("features_json") or clip.get("features") or {}
    if isinstance(raw,dict): return raw
    try: return json.loads(raw)
    except Exception: return {}

def focus_mode(clip: dict) -> str:
    event=str(clip.get("event_type") or "").lower()
    f=_features(clip)
    if event in COMBAT_TYPES:
        return "combat"
    if event in REWARD_TYPES:
        return "chat"
    if float(f.get("ui_change",0) or 0) > max(float(f.get("chat_change",0) or 0),0.35):
        return "ui"
    if float(f.get("chat_change",0) or 0) > 0.35:
        return "chat"
    return "center"

def variant_window(clip: dict, variant: str, s: Settings) -> tuple[float,float]:
    start=float(clip["start"]); end=float(clip["end"])
    target=float(s.render_variants.get(variant,s.render_variants.get(s.primary_variant,end-start)))
    if target <= 0 or end-start <= target:
        return start,end
    anchor=start+(end-start)*0.56
    a=anchor-target*0.54; b=a+target
    if a<start: a=start; b=a+target
    if b>end: b=end; a=max(start,b-target)
    return a,b

def tighten_dead_air(words: list[dict], start: float, end: float, clip: dict, s: Settings) -> tuple[float,float]:
    if not s.dead_air_trim_enabled or str(clip.get("event_type") or "") not in SPEECHY_TYPES:
        return start,end
    relevant=[w for w in words if float(w["end"])>=start and float(w["start"])<=end]
    if not relevant: return start,end
    pad=max(0.0,float(s.dead_air_padding_seconds))
    a=max(start,float(relevant[0]["start"])-pad)
    b=min(end,float(relevant[-1]["end"])+pad)
    minimum=max(2.0,float(s.dead_air_min_clip_seconds))
    if b-a < minimum:
        mid=(a+b)/2; a=max(start,mid-minimum/2); b=min(end,a+minimum)
        a=max(start,b-minimum)
    return a,b

def _focus_crop(mode: str) -> str:
    if mode=="combat":
        return "crop=iw*0.62:ih*0.72:iw*0.10:ih*0.05"
    if mode=="chat":
        return "crop=iw*0.72:ih*0.43:0:ih*0.57"
    if mode=="ui":
        return "crop=iw*0.34:ih*0.86:iw*0.66:ih*0.04"
    return "crop=iw*0.66:ih*0.72:iw*0.08:ih*0.06"

def _osrs_focus_filter(clip: dict, ass_path: str, s: Settings) -> str:
    rw,rh=int(s.render_width),int(s.render_height)
    margin=max(20,int(s.osrs_focus_margin))
    panel_h=max(420,min(int(s.osrs_focus_panel_height),rh-850))
    panel_w=rw-margin*2
    full_w=rw-margin*2
    full_y=70
    focus_y=735
    crop=_focus_crop(focus_mode(clip))
    return (
        f"[0:v]split=3[bg][full][focus];"
        f"[bg]scale={rw}:{rh}:force_original_aspect_ratio=increase,crop={rw}:{rh},gblur=sigma=30[bg2];"
        f"[full]scale={full_w}:-2:force_original_aspect_ratio=decrease[full2];"
        f"[focus]{crop},scale={panel_w}:{panel_h}:force_original_aspect_ratio=increase,"
        f"crop={panel_w}:{panel_h},drawbox=x=0:y=0:w=iw:h=ih:color=white@0.72:t=4[focus2];"
        f"[bg2][full2]overlay=(W-w)/2:{full_y}[stage1];"
        f"[stage1][focus2]overlay=(W-w)/2:{focus_y},ass='{ass_path}'[v]"
    )

def render_clip(source: Path, clip: dict, words: list[dict], output: Path, s: Settings,
                variant: str|None=None, progress=None):
    require_ffmpeg()
    output.parent.mkdir(parents=True,exist_ok=True)
    variant=variant or s.primary_variant
    start,end=variant_window(clip,variant,s)
    start,end=tighten_dead_air(words,start,end,clip,s)
    dur=max(0.2,end-start)

    ass=output.with_suffix(".ass")
    write_ass(words,start,end,ass,s)
    ap=_ffmpeg_filter_path(ass)

    if s.layout=="center_crop":
        vf=(f"scale={s.render_width}:{s.render_height}:force_original_aspect_ratio=increase,"
            f"crop={s.render_width}:{s.render_height},ass='{ap}'")
        cmd=["ffmpeg","-hide_banner","-loglevel","warning","-y","-ss",str(start),"-i",str(source),
             "-t",str(dur),"-vf",vf]
    elif s.layout=="osrs_focus":
        fc=_osrs_focus_filter(clip,ap,s)
        cmd=["ffmpeg","-hide_banner","-loglevel","warning","-y","-ss",str(start),"-i",str(source),
             "-t",str(dur),"-filter_complex",fc,"-map","[v]","-map","0:a?"]
    else:
        fc=(f"[0:v]split=2[bg][fg];"
            f"[bg]scale={s.render_width}:{s.render_height}:force_original_aspect_ratio=increase,"
            f"crop={s.render_width}:{s.render_height},gblur=sigma=28[bg2];"
            f"[fg]scale={s.render_width}:-2:force_original_aspect_ratio=decrease[fg2];"
            f"[bg2][fg2]overlay=(W-w)/2:(H-h)/2,ass='{ap}'[v]")
        cmd=["ffmpeg","-hide_banner","-loglevel","warning","-y","-ss",str(start),"-i",str(source),
             "-t",str(dur),"-filter_complex",fc,"-map","[v]","-map","0:a?"]

    cmd += ["-c:v","libx264","-preset","medium","-crf","20","-pix_fmt","yuv420p",
            "-c:a","aac","-b:a","192k","-movflags","+faststart",str(output)]
    if progress:
        progress(f"Rendering {variant} vertical clip")
    subprocess.run(cmd,check=True)
    return {"path":output,"variant":variant,"start":start,"end":end,"duration":dur,"focus":focus_mode(clip)}
