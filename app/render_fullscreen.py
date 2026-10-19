from __future__ import annotations

import subprocess
from pathlib import Path

from .captions import write_ass
from .config import Settings
from .media import require_ffmpeg
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


def _shorts_focus_mode(clip: dict) -> str:
    """Shorts never frame OSRS chat/UI as the subject; only gameplay gets the main frame."""
    mode = focus_mode(clip)
    return "combat" if mode == "combat" else "center"


def _gameplay_chain(mode: str, width: int, height: int, duration: float, s: Settings) -> str:
    """Create a full-height 9:16 gameplay crop centered on the source frame."""
    base = (
        "crop="
        "w='trunc(ih*9/16/2)*2':"
        "h='trunc(ih/2)*2':"
        "x='(iw-ow)/2':y=0,"
        f"scale={width}:{height}:flags=lanczos"
    )
    if not s.dynamic_zoom_enabled or duration < 2.0:
        return base

    fps = 30.0
    strength = max(0.0, min(0.24, float(s.dynamic_zoom_strength)))
    if mode == "combat":
        strength = min(0.26, strength * 1.18)
    interval = max(3.5, float(s.dynamic_beat_interval_seconds))
    beat = max(0.7, min(float(s.dynamic_beat_seconds), interval * 0.45))
    interval_f = max(2, int(round(interval * fps)))
    beat_f = max(1, int(round(beat * fps)))
    pulse = max(0.022, min(0.055, strength * 0.24))
    payoff_mid = int(round(duration * 0.60 * fps))
    payoff_half = max(1, int(round(min(float(s.dynamic_zoom_seconds), duration * 0.45) * fps / 2)))
    payoff_start = max(0, payoff_mid - payoff_half)
    payoff_end = max(payoff_start + 1, payoff_mid + payoff_half)

    beat_expr = (
        f"if(lt(mod(on,{interval_f}),{beat_f}),"
        f"sin(PI*mod(on,{interval_f})/{beat_f}),0)"
    )
    payoff_expr = (
        f"if(between(on,{payoff_start},{payoff_end}),"
        f"max(0,1-abs(on-{payoff_mid})/{payoff_half}),0)"
    )
    z = f"min(1.28,1+{pulse:.4f}*({beat_expr})+{strength:.4f}*({payoff_expr}))"
    x = "iw/2-(iw/zoom/2)"
    y = "ih/2-(ih/zoom/2)"
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

    xr = max(0.0, min(0.98, float(s.webcam_manual_x_ratio)))
    yr = max(0.0, min(0.98, float(s.webcam_manual_y_ratio)))
    wr = max(0.02, min(1.0 - xr, float(s.webcam_manual_width_ratio)))
    hr = max(0.02, min(1.0 - yr, float(s.webcam_manual_height_ratio)))

    x = int(round(width * xr))
    y = int(round(height * yr))
    w = max(2, int(round(width * wr)))
    h = max(2, int(round(height * hr)))
    if x + w > width:
        w = width - x
    if y + h > height:
        h = height - y
    if w < 2 or h < 2:
        return None
    return "manual", f"crop={w}:{h}:{x}:{y}", w / h


def _full_game_filter(source: Path, start: float, clip: dict, ass_path: str,
                      s: Settings, duration: float) -> tuple[str, str, str]:
    """Fill the Short with centered gameplay plus only the real configured webcam."""
    rw, rh = int(s.render_width), int(s.render_height)
    mode = _shorts_focus_mode(clip)
    game_chain = _gameplay_chain(mode, rw, rh, duration, s)

    configured_region = str(s.webcam_region or "auto").lower()
    manual = _manual_webcam_crop(source, s) if configured_region in {"auto", "manual"} else None
    webcam = None
    camera_aspect = 16 / 9
    if manual:
        region, cam_crop, camera_aspect = manual
        webcam = (region, cam_crop)
    elif configured_region != "auto":
        webcam = _webcam_crop(source, start, s)

    # The old reaction-only detector assumes one of the four 16:9 corner boxes.
    # Do not run it against the calibrated manual rectangle.
    if webcam:
        region, _ = webcam
        if region != "manual" and _reaction_only_source(source, start, s, region):
            return _reaction_filter(source, start, ass_path, s, webcam)

    if webcam:
        region, cam_crop = webcam
        cam_w = max(300, min(int(s.webcam_overlay_width), int(rw * 0.42)))
        cam_h = max(160, int(round(cam_w / max(0.5, camera_aspect))))
        cam_h = min(cam_h, int(rh * 0.30))
        cam_x = (rw - cam_w) // 2
        cam_y = 54
        graph = (
            f"[0:v]split=2[game][cam];"
            f"[game]{game_chain}[game2];"
            f"[cam]{cam_crop},scale={cam_w}:{cam_h}:force_original_aspect_ratio=increase,"
            f"crop={cam_w}:{cam_h},drawbox=x=0:y=0:w=iw:h=ih:color=white@0.90:t=5[cam2];"
            f"[game2][cam2]overlay={cam_x}:{cam_y}[stage1];"
            f"[stage1]ass='{ass_path}',setsar=1[v]"
        )
        return graph, region, "gameplay_fullscreen"

    graph = f"[0:v]{game_chain},ass='{ass_path}',setsar=1[v]"
    return graph, "", "gameplay_fullscreen"


def render_clip(source: Path, clip: dict, words: list[dict], output: Path, s: Settings,
                variant: str | None = None, progress=None):
    """Shorts renderer: centered gameplay plus the calibrated Postal webcam."""
    if s.layout != "osrs_focus":
        return _legacy_render_clip(source, clip, words, output, s, variant=variant, progress=progress)

    require_ffmpeg()
    output.parent.mkdir(parents=True, exist_ok=True)
    variant = variant or s.primary_variant
    start, end = variant_window(clip, variant, s)
    start, end = tighten_dead_air(words, start, end, clip, s)
    dur = max(0.2, end - start)

    ass = output.with_suffix(".ass")
    hook_text = str(clip.get("hook_text") or "") if s.auto_hook_enabled else ""
    write_ass(words, start, end, ass, s, hook_text=hook_text)
    ap = _ffmpeg_filter_path(ass)

    fc, webcam_region, render_mode = _full_game_filter(source, start, clip, ap, s, dur)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
        "-ss", str(start), "-i", str(source), "-t", str(dur),
        "-filter_complex", fc, "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output),
    ]
    if progress:
        progress(f"Rendering {variant} vertical clip ({render_mode})")
    subprocess.run(cmd, check=True)

    return {
        "path": output,
        "variant": variant,
        "start": start,
        "end": end,
        "duration": dur,
        "focus": mode if (mode := _shorts_focus_mode(clip)) else "center",
        "hook_text": hook_text,
        "dynamic_zoom": bool(s.dynamic_zoom_enabled),
        "webcam_region": webcam_region,
        "webcam_position": "top_center" if webcam_region else "",
        "render_mode": render_mode,
        "resolution": f"{int(s.render_width)}x{int(s.render_height)}",
        "sar": "1:1",
        "chat_visible": False,
    }
