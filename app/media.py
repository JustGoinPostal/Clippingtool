from __future__ import annotations
import json, subprocess, shutil
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".webm", ".m4v", ".ts"}

def require_ffmpeg():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("FFmpeg/ffprobe not found in PATH. Run install.ps1 or install FFmpeg.")

def probe(path: Path) -> dict:
    require_ffmpeg()
    cmd=["ffprobe","-v","error","-show_format","-show_streams","-of","json",str(path)]
    return json.loads(subprocess.check_output(cmd, text=True, encoding="utf-8", errors="replace"))

def duration(path: Path) -> float:
    d=probe(path)
    try: return float(d.get("format",{}).get("duration",0))
    except Exception: return 0.0

def audio_energy(path: Path, out_txt: Path) -> list[tuple[float,float]]:
    require_ffmpeg(); out_txt.parent.mkdir(parents=True, exist_ok=True)
    filt=("aresample=8000,asetnsamples=n=16000:p=0,"
          "astats=metadata=1:reset=1,"
          f"ametadata=print:key=lavfi.astats.Overall.RMS_level:file='{str(out_txt).replace(chr(92),'/')}'")
    cmd=["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(path),"-vn","-af",filt,"-f","null","-"]
    subprocess.run(cmd, check=True)
    values=[]; t=None
    for line in out_txt.read_text(encoding="utf-8",errors="ignore").splitlines():
        if "pts_time:" in line:
            try: t=float(line.split("pts_time:",1)[1].strip())
            except: t=None
        elif "lavfi.astats.Overall.RMS_level=" in line and t is not None:
            raw=line.split("=",1)[1].strip()
            try: values.append((t,float(raw)))
            except: pass
    return values
