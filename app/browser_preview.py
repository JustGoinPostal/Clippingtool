from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from .media import probe, require_ffmpeg

_BROWSER_VIDEO={"h264"}
_BROWSER_AUDIO={"aac","mp3"}


def _streams(payload: dict[str,Any]) -> tuple[dict[str,Any]|None,dict[str,Any]|None]:
    rows=list(payload.get("streams") or [])
    video=next((x for x in rows if str(x.get("codec_type") or "")=="video"),None)
    audio=next((x for x in rows if str(x.get("codec_type") or "")=="audio"),None)
    return video,audio


def browser_safe_mp4(path: Path, payload: dict[str,Any]|None=None) -> bool:
    path=Path(path)
    if path.suffix.lower() not in {".mp4",".m4v"}: return False
    data=payload or probe(path); video,audio=_streams(data)
    if not video or str(video.get("codec_name") or "").lower() not in _BROWSER_VIDEO: return False
    return audio is None or str(audio.get("codec_name") or "").lower() in _BROWSER_AUDIO


def preview_key(path: Path) -> str:
    path=Path(path).resolve(); stat=path.stat()
    raw=json.dumps({"path":str(path),"size":stat.st_size,"mtime_ns":stat.st_mtime_ns},sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


def ensure_browser_preview(source: Path, cache_dir: Path) -> tuple[Path,str]:
    """Return a browser-safe preview without modifying the creator's recording.

    Safe H.264 MP4 is served directly. Other containers/codecs are cached as MP4.
    When the source video is already H.264 we stream-copy it and only transcode an
    incompatible audio track; otherwise a compatibility transcode is used.
    """
    source=Path(source).resolve()
    if not source.exists(): raise FileNotFoundError(source)
    media=probe(source)
    if browser_safe_mp4(source,media): return source,"direct"

    require_ffmpeg(); cache_dir=Path(cache_dir); cache_dir.mkdir(parents=True,exist_ok=True)
    output=cache_dir/f"{preview_key(source)}.mp4"
    if output.exists() and output.stat().st_size>100_000: return output,"cached"
    tmp=output.with_suffix(".partial.mp4"); tmp.unlink(missing_ok=True)
    video,audio=_streams(media)
    vcodec=str((video or {}).get("codec_name") or "").lower()
    acodec=str((audio or {}).get("codec_name") or "").lower()
    cmd=["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(source),"-map","0:v:0","-map","0:a:0?"]
    if vcodec in _BROWSER_VIDEO:
        cmd += ["-c:v","copy"]
    else:
        cmd += ["-c:v","libx264","-preset","veryfast","-crf","23","-pix_fmt","yuv420p"]
    if audio is None:
        cmd += ["-an"]
    elif acodec in _BROWSER_AUDIO:
        cmd += ["-c:a","copy"]
    else:
        cmd += ["-c:a","aac","-b:a","160k"]
    cmd += ["-movflags","+faststart",str(tmp)]
    try:
        subprocess.run(cmd,check=True,timeout=60*60*6)
        if not tmp.exists() or tmp.stat().st_size<=100_000:
            raise RuntimeError("browser preview output is unexpectedly small")
        tmp.replace(output)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return output,"generated"
