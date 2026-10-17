from __future__ import annotations

import subprocess
from pathlib import Path

from .captions import write_ass
from .config import Settings
from .media import require_ffmpeg
from .render import (
    _ffmpeg_filter_path,
    _focus_chain,
    _reaction_filter,
    _reaction_only_source,
    _webcam_crop,
    focus_mode,
    render_clip as _legacy_render_clip,
    tighten_dead_air,
    variant_window,
)


def _full_game_filter(source: Path, start: float, clip: dict, ass_path: str,
                      s: Settings, duration: float) -> tuple[str, str, str]:
    """Fill the entire 9:16 Short with gameplay, optionally overlaying a real webcam."""
    rw, rh = int(s.render_width), int(s.render_height)
    mode = focus_mode(clip)
    game_chain = _focus_chain(mode, rw, rh, duration, s)
    webcam = _webcam_crop(source, start, s)

    # If the source truly contains no meaningful gameplay, keep the existing reaction layout.
    if webcam:
        region, _ = webcam
        if _reaction_only_source(source, start, s, region):
            return _reaction_filter(source, start, ass_path, s, webcam)

    if webcam:
        region, cam_crop = webcam
        cam_w = max(300, min(int(s.webcam_overlay_width), int(rw * 0.42)))
        cam_h = int(round(cam_w * 9 / 16))
        cam_x = rw - cam_w - 42
        cam_y = 72
        graph = (
            f"[0:v]split=2[game][cam];"
            f"[game]{game_chain}[game2];"
            f"[cam]{cam_crop},scale={cam_w}:{cam_h}:force_original_aspect_ratio=increase,"
            f"crop={cam_w}:{cam_h},drawbox=x=0:y=0:w=iw:h=ih:color=white@0.90:t=5[cam2];"
            f"[game2][cam2]overlay={cam_x}:{cam_y}[stage1];"
            f"[stage1]ass='{ass_path}',setsar=1[v]"
        )
        return graph, region, "gameplay_fullscreen"

    graph = (
        f"[0:v]{game_chain},ass='{ass_path}',setsar=1[v]"
    )
    return graph, "", "gameplay_fullscreen"


def render_clip(source: Path, clip: dict, words: list[dict], output: Path, s: Settings,
                variant: str | None = None, progress=None):
    """Shorts renderer: full-frame gameplay first, webcam only as an overlay."""
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
        "focus": focus_mode(clip),
        "hook_text": hook_text,
        "dynamic_zoom": bool(s.dynamic_zoom_enabled),
        "webcam_region": webcam_region,
        "render_mode": render_mode,
        "resolution": f"{int(s.render_width)}x{int(s.render_height)}",
        "sar": "1:1",
    }
