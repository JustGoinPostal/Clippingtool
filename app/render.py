from __future__ import annotations
import subprocess, os
from pathlib import Path
from .config import Settings
from .media import require_ffmpeg
from .captions import write_ass

def _ffmpeg_filter_path(p: Path):
    x=str(p.resolve()).replace("\\","/")
    x=x.replace(":","\\:").replace("'","\\'")
    return x

def render_clip(source: Path, clip: dict, words: list[dict], output: Path, s: Settings, progress=None):
    require_ffmpeg(); output.parent.mkdir(parents=True,exist_ok=True)
    ass=output.with_suffix(".ass"); write_ass(words,float(clip["start"]),float(clip["end"]),ass,s)
    dur=max(0.2,float(clip["end"])-float(clip["start"])); ap=_ffmpeg_filter_path(ass)
    if s.layout == "center_crop":
        vf=(f"scale={s.render_width}:{s.render_height}:force_original_aspect_ratio=increase,"
            f"crop={s.render_width}:{s.render_height},ass='{ap}'")
        cmd=["ffmpeg","-hide_banner","-loglevel","warning","-y","-ss",str(clip["start"]),"-i",str(source),"-t",str(dur),"-vf",vf]
    else:
        fc=(f"[0:v]split=2[bg][fg];"
            f"[bg]scale={s.render_width}:{s.render_height}:force_original_aspect_ratio=increase,crop={s.render_width}:{s.render_height},gblur=sigma=28[bg2];"
            f"[fg]scale={s.render_width}:-2:force_original_aspect_ratio=decrease[fg2];"
            f"[bg2][fg2]overlay=(W-w)/2:(H-h)/2,ass='{ap}'[v]")
        cmd=["ffmpeg","-hide_banner","-loglevel","warning","-y","-ss",str(clip["start"]),"-i",str(source),"-t",str(dur),"-filter_complex",fc,"-map","[v]","-map","0:a?"]
    cmd += ["-c:v","libx264","-preset","medium","-crf","20","-pix_fmt","yuv420p","-c:a","aac","-b:a","192k","-movflags","+faststart",str(output)]
    if progress: progress("Rendering vertical clip")
    subprocess.run(cmd,check=True)
    return output
