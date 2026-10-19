from __future__ import annotations

import math
import re
import subprocess
from pathlib import Path
from typing import Any

from .config import Settings
from .framing import build_focus_keyframes
from .media import probe, require_ffmpeg

_BLACK_RE = re.compile(r"black_start:(?P<start>[0-9.]+).*?black_end:(?P<end>[0-9.]+).*?black_duration:(?P<dur>[0-9.]+)")
_SILENCE_START_RE = re.compile(r"silence_start:\s*(?P<t>[0-9.]+)")
_SILENCE_END_RE = re.compile(r"silence_end:\s*(?P<end>[0-9.]+)\s*\|\s*silence_duration:\s*(?P<dur>[0-9.]+)")


def parse_blackdetect(text: str) -> dict[str, Any]:
    rows=[]
    for m in _BLACK_RE.finditer(text or ""):
        rows.append({"start":float(m.group("start")),"end":float(m.group("end")),"duration":float(m.group("dur"))})
    return {
        "segments": rows,
        "total_seconds": round(sum(x["duration"] for x in rows),3),
        "max_seconds": round(max([x["duration"] for x in rows] or [0.0]),3),
    }


def parse_silencedetect(text: str, duration: float) -> dict[str, Any]:
    starts=[float(m.group("t")) for m in _SILENCE_START_RE.finditer(text or "")]
    ends=[(float(m.group("end")),float(m.group("dur"))) for m in _SILENCE_END_RE.finditer(text or "")]
    rows=[]
    used=0
    for end,dur in ends:
        start=max(0.0,end-dur)
        rows.append({"start":round(start,3),"end":round(end,3),"duration":round(dur,3)})
        used+=1
    # FFmpeg omits silence_end when a file ends while still silent.
    if len(starts)>used and duration>0:
        start=starts[-1]
        if start < duration:
            rows.append({"start":round(start,3),"end":round(duration,3),"duration":round(duration-start,3)})
    total=sum(x["duration"] for x in rows)
    return {
        "segments":rows,
        "total_seconds":round(total,3),
        "max_seconds":round(max([x["duration"] for x in rows] or [0.0]),3),
        "ratio":round(min(1.0,total/max(0.001,duration)),4) if duration>0 else 0.0,
    }


def _run_ffmpeg(path: Path, args: list[str], timeout: float) -> str:
    require_ffmpeg()
    cmd=["ffmpeg","-hide_banner","-nostats","-v","info","-i",str(path),*args,"-f","null","-"]
    result=subprocess.run(cmd,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=timeout,check=False)
    return (result.stderr or "") + "\n" + (result.stdout or "")


def _black_stats(path: Path, duration: float) -> dict[str,Any]:
    text=_run_ffmpeg(path,["-vf","blackdetect=d=0.25:pix_th=0.025","-an"],max(45.0,duration*2.0+20.0))
    out=parse_blackdetect(text)
    out["ratio"]=round(min(1.0,float(out["total_seconds"])/max(0.001,duration)),4) if duration>0 else 0.0
    return out


def _silence_stats(path: Path, duration: float) -> dict[str,Any]:
    text=_run_ffmpeg(path,["-vn","-af","silencedetect=noise=-50dB:d=1.25"],max(45.0,duration*2.0+20.0))
    return parse_silencedetect(text,duration)


def _caption_metrics(words: list[dict], start: float, end: float, s: Settings, hook_text: str) -> dict[str,Any]:
    visible=[]
    for row in words or []:
        if float(row.get("end",0) or 0) < start or float(row.get("start",0) or 0) > end:
            continue
        text=str(row.get("word") or row.get("text") or "").strip()
        if text: visible.append(text)
    n=max(1,int(s.caption_words_per_group))
    groups=[" ".join(visible[i:i+n]) for i in range(0,len(visible),n)]
    return {
        "group_count":len(groups),
        "max_group_chars":max([len(x) for x in groups] or [0]),
        "max_group":max(groups,key=len) if groups else "",
        "hook_chars":len((hook_text or "").strip()),
        "caption_margin_v":int(s.caption_margin_v),
        "hook_margin_v":int(s.hook_margin_v),
    }


def focus_motion_metrics(game_events: list[dict] | None, start: float, end: float) -> dict[str,Any]:
    rows=build_focus_keyframes(game_events or [],start,end)
    total=0.0; max_speed=0.0; max_jump=0.0
    for a,b in zip(rows,rows[1:]):
        dt=max(0.001,float(b["time"])-float(a["time"]))
        dist=math.hypot(float(b["x"])-float(a["x"]),float(b["y"])-float(a["y"]))
        total+=dist; max_jump=max(max_jump,dist); max_speed=max(max_speed,dist/dt)
    return {
        "points":len(rows),
        "total_motion":round(total,4),
        "max_jump":round(max_jump,4),
        "max_speed_per_second":round(max_speed,4),
    }


def _stream_summary(payload: dict[str,Any]) -> tuple[dict[str,Any]|None,list[dict[str,Any]],float]:
    streams=list(payload.get("streams") or [])
    videos=[x for x in streams if str(x.get("codec_type") or "")=="video"]
    audios=[x for x in streams if str(x.get("codec_type") or "")=="audio"]
    video=videos[0] if videos else None
    try: duration=float((payload.get("format") or {}).get("duration") or 0)
    except Exception: duration=0.0
    return video,audios,duration


def evaluate_render_qa(
    path: Path,
    clip: dict,
    words: list[dict],
    render_result: dict,
    s: Settings,
    game_events: list[dict] | None = None,
) -> dict[str,Any]:
    """Inspect the actual encoded Short and fail closed on technical defects."""
    if not bool(s.render_qa_enabled):
        return {"status":"pass","passed":True,"skipped":True,"blockers":[],"warnings":[],"checks":{}}

    blockers=[]; warnings=[]; checks: dict[str,Any]={}
    path=Path(path)
    if not path.exists():
        return {"status":"review","passed":False,"blockers":["render file is missing"],"warnings":[],"checks":{}}
    try:
        checks["file_size_bytes"]=int(path.stat().st_size)
        if path.stat().st_size < 100_000:
            blockers.append("render file is suspiciously small")
    except Exception as e:
        blockers.append(f"could not stat render: {type(e).__name__}")

    video=None; audios=[]; actual_duration=0.0
    try:
        media=probe(path)
        video,audios,actual_duration=_stream_summary(media)
        checks["duration"]=round(actual_duration,3)
        checks["audio_streams"]=len(audios)
        if not video:
            blockers.append("render has no video stream")
        else:
            width=int(video.get("width") or 0); height=int(video.get("height") or 0)
            checks["width"]=width; checks["height"]=height
            checks["aspect_ratio"]=round(width/max(1,height),5)
            if width < int(s.render_qa_min_width) or height < int(s.render_qa_min_height):
                blockers.append(f"render resolution is too small ({width}x{height})")
            if abs((width/max(1,height))-(9/16)) > 0.025:
                blockers.append(f"render is not a safe 9:16 vertical frame ({width}x{height})")
        if bool(s.render_qa_require_audio) and not audios:
            blockers.append("render has no audio stream")
        expected=max(0.0,float(render_result.get("end",0) or 0)-float(render_result.get("start",0) or 0))
        checks["expected_duration"]=round(expected,3)
        if actual_duration <= 0:
            blockers.append("render duration could not be verified")
        elif expected > 0 and abs(actual_duration-expected) > max(1.5,expected*0.08):
            blockers.append(f"render duration drifted from edit window ({actual_duration:.1f}s vs {expected:.1f}s)")
        if actual_duration < 6.0:
            blockers.append("render is too short for automatic posting")
        if actual_duration > 65.5:
            blockers.append("render is longer than the AutoClip short-form safety limit")
    except Exception as e:
        blockers.append(f"ffprobe validation failed: {type(e).__name__}: {e}")

    if video and actual_duration>0:
        try:
            black=_black_stats(path,actual_duration); checks["black_frames"]=black
            if float(black["max_seconds"]) > float(s.render_qa_max_black_seconds):
                blockers.append(f"black frame section lasts {black['max_seconds']:.2f}s")
            if float(black["ratio"]) > float(s.render_qa_max_black_ratio):
                blockers.append(f"black frames occupy {float(black['ratio'])*100:.1f}% of the render")
        except Exception as e:
            blockers.append(f"black-frame QA failed: {type(e).__name__}: {e}")

    if audios and actual_duration>0:
        try:
            silence=_silence_stats(path,actual_duration); checks["silence"]=silence
            if float(silence["ratio"]) >= float(s.render_qa_max_silence_ratio):
                blockers.append(f"audio is effectively silent for {float(silence['ratio'])*100:.1f}% of the render")
            elif float(silence["ratio"]) >= 0.75:
                warnings.append(f"render is unusually quiet ({float(silence['ratio'])*100:.1f}% detected silence)")
        except Exception as e:
            blockers.append(f"audio QA failed: {type(e).__name__}: {e}")

    start=float(render_result.get("start",0) or 0); end=float(render_result.get("end",0) or 0)
    captions=_caption_metrics(words,start,end,s,str(clip.get("hook_text") or "")); checks["captions"]=captions
    if int(captions["max_group_chars"]) > int(s.render_qa_max_caption_chars):
        blockers.append(f"caption group is too wide ({captions['max_group_chars']} characters)")
    if int(captions["caption_margin_v"]) < int(s.render_qa_caption_safe_margin):
        blockers.append("caption safe margin is too close to platform UI")
    if int(captions["hook_chars"]) > 54:
        blockers.append("opening hook is too long to read safely")
    if int(captions["hook_margin_v"]) < 70:
        warnings.append("opening hook is close to the top platform UI safe zone")

    motion=focus_motion_metrics(game_events,start,end); checks["framing_motion"]=motion
    if int(motion["points"]) >= 2:
        if float(motion["max_speed_per_second"]) > float(s.render_qa_max_focus_speed):
            blockers.append(f"smart framing moves too fast ({motion['max_speed_per_second']:.2f} frame-widths/sec)")
        if float(motion["total_motion"]) > float(s.render_qa_max_focus_total_motion):
            blockers.append(f"smart framing travels too much ({motion['total_motion']:.2f} normalized distance)")
    if bool(s.webcam_overlay_enabled) and bool(s.webcam_manual_enabled) and not str(render_result.get("webcam_region") or ""):
        warnings.append("webcam overlay is enabled but no webcam region was rendered")

    status="review" if blockers else "pass"
    return {
        "status":status,
        "passed":not blockers,
        "blockers":blockers,
        "warnings":warnings,
        "checks":checks,
    }
