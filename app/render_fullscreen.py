from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .captions import write_ass
from .config import Settings
from .framing import build_focus_keyframes, crop_x_expression, zoompan_y_expression
from .media import require_ffmpeg, run_ffmpeg
from .retention_edit import enable_expression, event_punch_times, reaction_windows
from .render import (
    _ffmpeg_filter_path,
    _reaction_filter,
    _reaction_only_source,
    _source_size,
    _webcam_crop,
    focus_mode,
    render_clip as _legacy_render_clip,
    tighten_dead_air,
    variant_window,
)


def _load_cached_energy(source: Path, s: Settings) -> list:
    """Read the analysis-time audio energy cache without rerunning FFmpeg."""
    try:
        st=source.stat()
        raw=f"{source.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode()
        key=hashlib.sha1(raw).hexdigest()[:16]
        path=s.cache_path/key/"energy.json"
        payload=json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload,list) else []
    except Exception:
        return []


def _shorts_focus_mode(clip: dict) -> str:
    """Shorts never frame OSRS chat/UI as the subject; only gameplay gets the main frame."""
    mode = focus_mode(clip)
    return "combat" if mode == "combat" else "center"


def _punch_expression(times: list[float], fps: float, seconds: float) -> str:
    if not times:
        return "0"
    half=max(1,int(round(max(0.45,float(seconds))*fps/2)))
    pulses=[]
    for t in times[:8]:
        mid=max(0,int(round(float(t)*fps)))
        pulses.append(f"max(0,1-abs(on-{mid})/{half})")
    expr=pulses[0]
    for pulse in pulses[1:]:
        expr=f"max({expr},{pulse})"
    return expr


def _gameplay_chain(mode: str, width: int, height: int, duration: float, s: Settings,
                    focus_keyframes: list[dict] | None = None,
                    punch_times: list[float] | None = None) -> str:
    """Create a player-centered 9:16 crop with brief zooms only on real OSRS events."""
    keyframes=focus_keyframes or []
    crop_x=crop_x_expression(keyframes) if keyframes else "(iw-ow)/2"
    base = (
        "crop="
        "w='trunc(ih*9/16/2)*2':"
        "h='trunc(ih/2)*2':"
        f"x='{crop_x}':y=0,"
        f"scale={width}:{height}:flags=lanczos"
    )
    # Direct helper callers retain one deterministic payoff pulse for backwards
    # compatibility; production passes an explicit list (possibly empty), so real
    # renders only punch in when an actual RuneLite event exists.
    raw_punches=[duration*0.60] if punch_times is None else list(punch_times)
    punches=[float(x) for x in raw_punches if 0.0 <= float(x) <= duration]
    if not s.dynamic_zoom_enabled or duration < 2.0 or not punches:
        return base

    fps=30.0
    strength=max(0.05,min(0.18,float(getattr(s,"event_punch_zoom",0.12))))
    if mode=="combat":
        strength=min(0.20,strength*1.10)
    pulse=_punch_expression(punches,fps,float(getattr(s,"event_punch_seconds",1.10)))
    z=f"min(1.22,1+{strength:.4f}*({pulse}))"
    x="iw/2-(iw/zoom/2)"
    y=zoompan_y_expression(keyframes,fps) if keyframes else "ih/2-(ih/zoom/2)"
    return (
        base
        + f",fps=30,zoompan=z='{z}':x='{x}':y='{y}':"
          f"d=1:s={width}x{height}:fps=30"
    )


def _manual_webcam_crop(source: Path, s: Settings) -> tuple[str, str, float] | None:
    """Return Postal's exact OBS webcam rectangle using normalized source coordinates."""
    if not bool(getattr(s, "webcam_manual_enabled", False)):
        return None
    width, height = _source_size(source)
    if width <= 0 or height <= 0:
        return None

    xr=max(0.0,min(0.98,float(s.webcam_manual_x_ratio)))
    yr=max(0.0,min(0.98,float(s.webcam_manual_y_ratio)))
    wr=max(0.02,min(1.0-xr,float(s.webcam_manual_width_ratio)))
    hr=max(0.02,min(1.0-yr,float(s.webcam_manual_height_ratio)))

    x=int(round(width*xr)); y=int(round(height*yr))
    w=max(2,int(round(width*wr))); h=max(2,int(round(height*hr)))
    if x+w>width:
        w=width-x
    if y+h>height:
        h=height-y
    if w<2 or h<2:
        return None
    return "manual",f"crop={w}:{h}:{x}:{y}",w/h


def _full_game_filter(source: Path, start: float, clip: dict, ass_path: str,
                      s: Settings, duration: float, game_events: list[dict] | None = None,
                      reaction_windows_list: list[tuple[float,float]] | None = None,
                      punch_times: list[float] | None = None
                      ) -> tuple[str, str, str, int, dict | None]:
    """Fill the Short with player-anchored gameplay and an event-aware webcam."""
    rw,rh=int(s.render_width),int(s.render_height)
    mode=_shorts_focus_mode(clip)
    focus_keyframes=build_focus_keyframes(game_events or [],start,start+duration)
    punches=punch_times if punch_times is not None else event_punch_times(
        game_events or [],start,start+duration,int(getattr(s,"event_punch_max_events",6))
    )
    game_chain=_gameplay_chain(
        mode,rw,rh,duration,s,focus_keyframes=focus_keyframes,punch_times=punches
    )

    configured_region=str(s.webcam_region or "auto").lower()
    manual=_manual_webcam_crop(source,s) if configured_region in {"auto","manual"} else None
    webcam=None
    camera_aspect=16/9
    if manual:
        region,cam_crop,camera_aspect=manual
        webcam=(region,cam_crop)
    elif configured_region!="auto":
        webcam=_webcam_crop(source,start,s)

    if webcam:
        region,_=webcam
        if region!="manual" and _reaction_only_source(source,start,s,region):
            graph,region_name,render_mode=_reaction_filter(source,start,ass_path,s,webcam)
            return graph,region_name,render_mode,len(focus_keyframes),None

    if webcam:
        region,cam_crop=webcam
        cam_w=max(300,min(int(s.webcam_overlay_width),int(rw*0.42)))
        cam_h=max(160,int(round(cam_w/max(0.5,camera_aspect))))
        cam_h=min(cam_h,int(rh*0.30))
        cam_x=(rw-cam_w)//2
        cam_y=54
        border=5
        reactions=list(reaction_windows_list or [])
        use_reactions=bool(getattr(s,"reaction_webcam_enabled",True) and reactions)
        if use_reactions:
            scale=max(1.05,min(1.55,float(getattr(s,"reaction_webcam_scale",1.28))))
            react_w=min(int(rw*0.60),int(round(cam_w*scale)))
            react_h=min(int(rh*0.40),int(round(react_w/max(0.5,camera_aspect))))
            react_x=(rw-react_w)//2
            react_y=max(20,cam_y-(react_h-cam_h)//2)
            enabled=enable_expression(reactions)
            graph=(
                f"[0:v]setpts=PTS-STARTPTS,split=3[game][cam][react];"
                f"[game]{game_chain}[game2];"
                f"[cam]{cam_crop},scale={cam_w}:{cam_h}:force_original_aspect_ratio=increase,"
                f"crop={cam_w}:{cam_h},drawbox=x=0:y=0:w=iw:h=ih:color=white@0.90:t={border}[cam2];"
                f"[react]{cam_crop},scale={react_w}:{react_h}:force_original_aspect_ratio=increase,"
                f"crop={react_w}:{react_h},drawbox=x=0:y=0:w=iw:h=ih:color=white@0.95:t={border}[react2];"
                f"[game2][cam2]overlay={cam_x}:{cam_y}[stage1];"
                f"[stage1][react2]overlay={react_x}:{react_y}:enable='{enabled}'[stage2];"
                f"[stage2]ass='{ass_path}',setsar=1[v]"
            )
        else:
            graph=(
                f"[0:v]setpts=PTS-STARTPTS,split=2[game][cam];"
                f"[game]{game_chain}[game2];"
                f"[cam]{cam_crop},scale={cam_w}:{cam_h}:force_original_aspect_ratio=increase,"
                f"crop={cam_w}:{cam_h},drawbox=x=0:y=0:w=iw:h=ih:color=white@0.90:t={border}[cam2];"
                f"[game2][cam2]overlay={cam_x}:{cam_y}[stage1];"
                f"[stage1]ass='{ass_path}',setsar=1[v]"
            )
        box={"x":cam_x,"y":cam_y,"w":cam_w,"h":cam_h,"border":border}
        return graph,region,"gameplay_fullscreen",len(focus_keyframes),box

    graph=f"[0:v]setpts=PTS-STARTPTS,{game_chain},ass='{ass_path}',setsar=1[v]"
    return graph,"","gameplay_fullscreen",len(focus_keyframes),None


def render_clip(source: Path, clip: dict, words: list[dict], output: Path, s: Settings,
                variant: str | None = None, progress=None, game_events: list[dict] | None = None,
                energy_samples: list | None = None):
    """Shorts renderer: player-centric gameplay with retention editing tied to real events."""
    if s.layout!="osrs_focus":
        return _legacy_render_clip(source,clip,words,output,s,variant=variant,progress=progress)

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

    punches=event_punch_times(
        game_events or [],start,end,int(getattr(s,"event_punch_max_events",6))
    ) if bool(getattr(s,"event_punch_enabled",True)) else []
    if energy_samples is None:
        energy_samples=_load_cached_energy(source,s)
    reactions=reaction_windows(
        energy_samples or [],start,end,
        z_threshold=float(getattr(s,"reaction_audio_z",1.35)),
        hold_seconds=float(getattr(s,"reaction_webcam_seconds",1.45)),
        max_events=int(getattr(s,"reaction_webcam_max_events",5)),
    ) if bool(getattr(s,"reaction_webcam_enabled",True)) else []

    fc,webcam_region,render_mode,focus_points,webcam_box=_full_game_filter(
        source,start,clip,ap,s,dur,game_events=game_events,
        reaction_windows_list=reactions,punch_times=punches
    )
    cmd=[
        "ffmpeg","-hide_banner","-loglevel","error","-y",
        "-ss",str(start),"-i",str(source),"-t",str(dur),
        "-filter_complex",fc,"-map","[v]","-map","0:a?",
        "-c:v","libx264","-preset","medium","-crf","20","-pix_fmt","yuv420p",
        "-c:a","aac","-b:a","192k","-movflags","+faststart",str(output),
    ]
    if progress:
        framing=f", {focus_points} RuneLite framing points" if focus_points else ", centered fallback"
        retention=f", {len(punches)} event punch-ins, {len(reactions)} reaction enlargements"
        progress(f"Rendering {variant} vertical clip ({render_mode}{framing}{retention})")
    run_ffmpeg(cmd,label=f"Render {variant}")

    return {
        "path":output,
        "variant":variant,
        "start":start,
        "end":end,
        "duration":dur,
        "focus":mode if (mode:=_shorts_focus_mode(clip)) else "center",
        "hook_text":hook_text,
        "dynamic_zoom":bool(punches),
        "event_punches":len(punches),
        "reaction_webcam_events":len(reactions),
        "smart_framing":bool(focus_points),
        "smart_framing_points":focus_points,
        "webcam_region":webcam_region,
        "webcam_position":"top_center" if webcam_region else "",
        "webcam_box":webcam_box,
        "render_mode":render_mode,
        "resolution":f"{int(s.render_width)}x{int(s.render_height)}",
        "sar":"1:1",
        "chat_visible":False,
    }
