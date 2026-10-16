from __future__ import annotations
import json, subprocess
from pathlib import Path
import numpy as np
from .config import Settings
from .media import require_ffmpeg, probe
from .captions import write_ass

SPEECHY_TYPES={"speech","reaction","chat"}
COMBAT_TYPES={"pvp","pvp_kill","death","player_death","big_hit","big_hit_taken","combat","player_loot","boss_kill"}
REWARD_TYPES={"drop","rare_drop","raid_reward","raid_complete","collection_log","loot","npc_loot"}
WEBCAM_REGIONS=("top_left","top_right","bottom_left","bottom_right")

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

def _payoff_ratio(mode: str) -> float:
    if mode=="combat": return 0.60
    if mode=="chat": return 0.52
    if mode=="ui": return 0.55
    return 0.58

def _focus_chain(mode: str, panel_w: int, panel_h: int, duration: float, s: Settings) -> str:
    crop=_focus_crop(mode)
    base=(f"{crop},scale={panel_w}:{panel_h}:force_original_aspect_ratio=increase,"
          f"crop={panel_w}:{panel_h}")
    if not s.dynamic_zoom_enabled or duration < 2.0:
        return base
    fps=30.0
    payoff_pulse=max(0.8,min(float(s.dynamic_zoom_seconds),duration*0.50))
    payoff_mid=duration*_payoff_ratio(mode)
    a=max(0.0,payoff_mid-payoff_pulse/2); b=min(duration,payoff_mid+payoff_pulse/2)
    payoff_mid=(a+b)/2; half=max(0.25,(b-a)/2)
    sf=int(round(a*fps)); ef=int(round(b*fps)); mf=int(round(payoff_mid*fps)); hf=max(1,int(round(half*fps)))

    strength=max(0.0,min(0.35,float(s.dynamic_zoom_strength)))
    if mode=="combat": strength=min(0.30,strength*1.30)
    elif mode=="chat": strength=min(0.28,strength*1.08)
    elif mode=="ui": strength=min(0.28,strength*1.15)
    else: strength=min(0.28,strength*1.18)

    interval=max(3.5,float(s.dynamic_beat_interval_seconds))
    beat=max(0.7,min(float(s.dynamic_beat_seconds),interval*0.45))
    interval_f=max(2,int(round(interval*fps)))
    beat_f=max(1,int(round(beat*fps)))
    micro=max(0.025,min(0.065,strength*0.27))
    beat_expr=(f"if(lt(mod(on,{interval_f}),{beat_f}),"
               f"sin(PI*mod(on,{interval_f})/{beat_f}),0)")
    payoff_expr=f"if(between(on,{sf},{ef}),max(0,1-abs(on-{mf})/{hf}),0)"
    z=f"min(1.32,1+{micro:.4f}*({beat_expr})+{strength:.4f}*({payoff_expr}))"
    x="iw/2-(iw/zoom/2)+sin(on/55)*(iw-iw/zoom)*0.12"
    y="ih/2-(ih/zoom/2)+cos(on/70)*(ih-ih/zoom)*0.08"
    return (base+f",fps=30,zoompan=z='{z}':x='{x}':y='{y}':"
                 f"d=1:s={panel_w}x{panel_h}:fps=30")

def _source_size(source: Path) -> tuple[int,int]:
    try:
        info=probe(source)
        for stream in info.get("streams",[]):
            if stream.get("codec_type")=="video":
                w=int(stream.get("width") or 0); h=int(stream.get("height") or 0)
                if w>0 and h>0: return w,h
    except Exception:
        pass
    return 1920,1080

def _corner_box(region: str, width: int, height: int, ratio: float) -> tuple[int,int,int,int]:
    ratio=max(0.18,min(0.45,float(ratio)))
    crop_w=max(160,int(round(width*ratio)))
    crop_h=max(90,int(round(crop_w*9/16)))
    crop_h=min(crop_h,max(90,int(height*0.42)))
    pad_x=max(0,int(width*0.012)); pad_y=max(0,int(height*0.018))
    if region.endswith("right"):
        x=max(0,width-crop_w-pad_x)
    else:
        x=pad_x
    if region.startswith("bottom"):
        y=max(0,height-crop_h-pad_y)
    else:
        y=pad_y
    return x,y,crop_w,crop_h

def _auto_webcam_region(source: Path, start: float, ratio: float) -> str:
    """Guess a corner webcam using only color/motion/texture, never for clip scoring."""
    sw,sh=320,180
    try:
        cmd=["ffmpeg","-hide_banner","-loglevel","error","-ss",str(max(0.0,start)),"-i",str(source),
             "-t","3.2","-vf",f"fps=1,scale={sw}:{sh}","-an","-pix_fmt","rgb24","-f","rawvideo","-"]
        raw=subprocess.check_output(cmd,stderr=subprocess.DEVNULL)
        frame_bytes=sw*sh*3
        frames=[]
        for i in range(0,len(raw)-frame_bytes+1,frame_bytes):
            frames.append(np.frombuffer(raw[i:i+frame_bytes],dtype=np.uint8).reshape(sh,sw,3))
        if not frames: return "top_right"
        scores={}
        for region in WEBCAM_REGIONS:
            x,y,w,h=_corner_box(region,sw,sh,ratio)
            patches=[f[y:y+h,x:x+w] for f in frames]
            skin=[]; texture=[]
            for p in patches:
                rgb=p.astype(np.float32); r=rgb[:,:,0]; g=rgb[:,:,1]; b=rgb[:,:,2]
                cb=128-0.168736*r-0.331264*g+0.5*b
                cr=128+0.5*r-0.418688*g-0.081312*b
                mask=(cb>=75)&(cb<=135)&(cr>=128)&(cr<=180)&(r>35)
                skin.append(float(mask.mean()))
                gray=0.299*r+0.587*g+0.114*b
                texture.append(float(gray.std()/255.0))
            motion=[]
            for a,b in zip(patches,patches[1:]):
                motion.append(float(np.abs(a.astype(np.int16)-b.astype(np.int16)).mean()/255.0))
            scores[region]=(2.1*float(np.mean(skin))+
                            1.35*(float(np.mean(motion)) if motion else 0.0)+
                            0.18*float(np.mean(texture)))
        return max(scores,key=scores.get)
    except Exception:
        return "top_right"

def _webcam_crop(source: Path, start: float, s: Settings) -> tuple[str,str]|None:
    if not s.webcam_overlay_enabled:
        return None
    region=str(s.webcam_region or "auto").lower()
    if region not in WEBCAM_REGIONS:
        region=_auto_webcam_region(source,start,float(s.webcam_crop_width_ratio))
    width,height=_source_size(source)
    x,y,w,h=_corner_box(region,width,height,float(s.webcam_crop_width_ratio))
    return region,f"crop={w}:{h}:{x}:{y}"

def _osrs_focus_filter(source: Path, start: float, clip: dict, ass_path: str, s: Settings, duration: float) -> tuple[str,str]:
    rw,rh=int(s.render_width),int(s.render_height)
    margin=max(20,int(s.osrs_focus_margin))
    panel_h=max(420,min(int(s.osrs_focus_panel_height),rh-850))
    panel_w=rw-margin*2
    full_w=rw-margin*2
    full_y=70
    focus_y=760
    mode=focus_mode(clip)
    focus_chain=_focus_chain(mode,panel_w,panel_h,duration,s)
    webcam=_webcam_crop(source,start,s)
    if webcam:
        region,cam_crop=webcam
        cam_w=max(260,min(int(s.webcam_overlay_width),rw-margin*2))
        cam_h=int(round(cam_w*9/16))
        cam_x=rw-margin-cam_w
        cam_y=max(320,min(int(s.webcam_overlay_y),focus_y-cam_h//2))
        graph=(
            f"[0:v]split=4[bg][full][focus][cam];"
            f"[bg]scale={rw}:{rh}:force_original_aspect_ratio=increase,crop={rw}:{rh},gblur=sigma=30[bg2];"
            f"[full]scale={full_w}:-2:force_original_aspect_ratio=decrease[full2];"
            f"[focus]{focus_chain},drawbox=x=0:y=0:w=iw:h=ih:color=white@0.72:t=4[focus2];"
            f"[cam]{cam_crop},scale={cam_w}:{cam_h}:force_original_aspect_ratio=increase,crop={cam_w}:{cam_h},"
            f"drawbox=x=0:y=0:w=iw:h=ih:color=white@0.92:t=5[cam2];"
            f"[bg2][full2]overlay=(W-w)/2:{full_y}[stage1];"
            f"[stage1][focus2]overlay=(W-w)/2:{focus_y}[stage2];"
            f"[stage2][cam2]overlay={cam_x}:{cam_y},ass='{ass_path}'[v]"
        )
        return graph,region
    graph=(
        f"[0:v]split=3[bg][full][focus];"
        f"[bg]scale={rw}:{rh}:force_original_aspect_ratio=increase,crop={rw}:{rh},gblur=sigma=30[bg2];"
        f"[full]scale={full_w}:-2:force_original_aspect_ratio=decrease[full2];"
        f"[focus]{focus_chain},drawbox=x=0:y=0:w=iw:h=ih:color=white@0.72:t=4[focus2];"
        f"[bg2][full2]overlay=(W-w)/2:{full_y}[stage1];"
        f"[stage1][focus2]overlay=(W-w)/2:{focus_y},ass='{ass_path}'[v]"
    )
    return graph,""

def render_clip(source: Path, clip: dict, words: list[dict], output: Path, s: Settings,
                variant: str|None=None, progress=None):
    require_ffmpeg()
    output.parent.mkdir(parents=True,exist_ok=True)
    variant=variant or s.primary_variant
    start,end=variant_window(clip,variant,s)
    start,end=tighten_dead_air(words,start,end,clip,s)
    dur=max(0.2,end-start)

    ass=output.with_suffix(".ass")
    hook_text=str(clip.get("hook_text") or "") if s.auto_hook_enabled else ""
    write_ass(words,start,end,ass,s,hook_text=hook_text)
    ap=_ffmpeg_filter_path(ass)
    webcam_region=""

    if s.layout=="center_crop":
        vf=(f"scale={s.render_width}:{s.render_height}:force_original_aspect_ratio=increase,"
            f"crop={s.render_width}:{s.render_height},ass='{ap}'")
        cmd=["ffmpeg","-hide_banner","-loglevel","warning","-y","-ss",str(start),"-i",str(source),
             "-t",str(dur),"-vf",vf]
    elif s.layout=="osrs_focus":
        fc,webcam_region=_osrs_focus_filter(source,start,clip,ap,s,dur)
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
    return {"path":output,"variant":variant,"start":start,"end":end,"duration":dur,
            "focus":focus_mode(clip),"hook_text":hook_text,
            "dynamic_zoom":bool(s.dynamic_zoom_enabled and s.layout=="osrs_focus"),
            "webcam_region":webcam_region,
            "resolution":f"{int(s.render_width)}x{int(s.render_height)}"}
