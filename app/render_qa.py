from __future__ import annotations

import math
import re
import statistics
import subprocess
from pathlib import Path
from typing import Any

from .config import Settings
from .framing import build_focus_keyframes
from .media import probe, require_ffmpeg

_BLACK_RE = re.compile(r"black_start:(?P<start>[0-9.]+).*?black_end:(?P<end>[0-9.]+).*?black_duration:(?P<dur>[0-9.]+)")
_SILENCE_START_RE = re.compile(r"silence_start:\s*(?P<t>[0-9.]+)")
_SILENCE_END_RE = re.compile(r"silence_end:\s*(?P<end>[0-9.]+)\s*\|\s*silence_duration:\s*(?P<dur>[0-9.]+)")
_FREEZE_START_RE = re.compile(r"freeze_start:\s*(?P<t>[0-9.]+)")
_FREEZE_END_RE = re.compile(r"freeze_end:\s*(?P<t>[0-9.]+)")
_FREEZE_DURATION_RE = re.compile(r"freeze_duration:\s*(?P<d>[0-9.]+)")
_MEAN_VOLUME_RE = re.compile(r"mean_volume:\s*(?P<v>-?(?:[0-9.]+|inf))\s*dB", re.I)
_MAX_VOLUME_RE = re.compile(r"max_volume:\s*(?P<v>-?(?:[0-9.]+|inf))\s*dB", re.I)
_CROP_RE = re.compile(r"crop=(?P<w>\d+):(?P<h>\d+):(?P<x>\d+):(?P<y>\d+)")
_YAVG_RE = re.compile(r"lavfi\.signalstats\.YAVG=(?P<v>[0-9.]+)")


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


def parse_freezedetect(text: str, duration: float) -> dict[str,Any]:
    rows=[]; start=None; pending_duration=None
    for line in (text or "").splitlines():
        sm=_FREEZE_START_RE.search(line)
        if sm:
            start=float(sm.group("t")); pending_duration=None
        dm=_FREEZE_DURATION_RE.search(line)
        if dm:
            pending_duration=float(dm.group("d"))
        em=_FREEZE_END_RE.search(line)
        if em and start is not None:
            end=float(em.group("t")); dur=pending_duration if pending_duration is not None else max(0.0,end-start)
            rows.append({"start":round(start,3),"end":round(end,3),"duration":round(dur,3)})
            start=None; pending_duration=None
    if start is not None and duration>start:
        end=float(duration); dur=max(0.0,end-start)
        rows.append({"start":round(start,3),"end":round(end,3),"duration":round(dur,3)})
    total=sum(x["duration"] for x in rows)
    return {
        "segments":rows,
        "total_seconds":round(total,3),
        "max_seconds":round(max([x["duration"] for x in rows] or [0.0]),3),
        "ratio":round(min(1.0,total/max(0.001,duration)),4) if duration>0 else 0.0,
    }


def _db_value(raw: str | None) -> float | None:
    if raw is None: return None
    try:
        value=float(raw)
        return value if math.isfinite(value) else None
    except Exception:
        return None


def parse_volumedetect(text: str) -> dict[str,Any]:
    mean=_MEAN_VOLUME_RE.findall(text or "")
    peak=_MAX_VOLUME_RE.findall(text or "")
    return {
        "mean_db":_db_value(mean[-1]) if mean else None,
        "max_db":_db_value(peak[-1]) if peak else None,
    }


def parse_cropdetect(text: str) -> list[dict[str,int]]:
    rows=[]; seen=set()
    for m in _CROP_RE.finditer(text or ""):
        row={k:int(m.group(k)) for k in ("w","h","x","y")}
        key=(row["w"],row["h"],row["x"],row["y"])
        if row["w"]<8 or row["h"]<8 or key in seen: continue
        seen.add(key); rows.append(row)
    return rows


def parse_signalstats_luma(text: str) -> dict[str,Any]:
    vals=[float(m.group("v")) for m in _YAVG_RE.finditer(text or "")]
    if not vals: return {"samples":0,"mean":None,"median":None,"min":None,"max":None}
    return {
        "samples":len(vals),
        "mean":round(sum(vals)/len(vals),3),
        "median":round(float(statistics.median(vals)),3),
        "min":round(min(vals),3),
        "max":round(max(vals),3),
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


def _freeze_stats(path: Path, duration: float) -> dict[str,Any]:
    text=_run_ffmpeg(path,["-vf","freezedetect=n=-55dB:d=1.25","-an"],max(45.0,duration*2.0+20.0))
    return parse_freezedetect(text,duration)


def _silence_stats(path: Path, duration: float) -> dict[str,Any]:
    text=_run_ffmpeg(path,["-vn","-af","silencedetect=noise=-50dB:d=1.25"],max(45.0,duration*2.0+20.0))
    return parse_silencedetect(text,duration)


def _audio_level_stats(path: Path, duration: float) -> dict[str,Any]:
    text=_run_ffmpeg(path,["-vn","-af","volumedetect"],max(45.0,duration*2.0+20.0))
    return parse_volumedetect(text)


def _filter_filename(path: Path) -> str:
    value=str(path).replace("\\","/")
    return value.replace("\\","\\\\").replace(":","\\:").replace("'","\\'")


def _caption_pixel_bounds(path: Path, width: int, height: int, duration: float) -> dict[str,Any]:
    ass=path.with_suffix(".ass")
    if not ass.exists():
        return {"available":False,"boxes":[],"upper":[],"lower":[]}
    require_ffmpeg()
    d=max(0.8,min(65.0,float(duration)))
    filt=f"ass='{_filter_filename(ass)}',cropdetect=limit=0.015:round=2:reset=1"
    cmd=["ffmpeg","-hide_banner","-nostats","-v","info","-f","lavfi","-i",
         f"color=c=black:s={int(width)}x{int(height)}:r=4:d={d:.3f}","-vf",filt,"-an","-f","null","-"]
    result=subprocess.run(cmd,capture_output=True,text=True,encoding="utf-8",errors="replace",
                          timeout=max(45.0,d*1.5+20.0),check=False)
    boxes=parse_cropdetect((result.stderr or "")+"\n"+(result.stdout or ""))
    upper=[x for x in boxes if x["y"]+x["h"]/2 < height/2]
    lower=[x for x in boxes if x["y"]+x["h"]/2 >= height/2]
    return {"available":True,"boxes":boxes,"upper":upper,"lower":lower}


def _region_luma_stats(path: Path, box: dict[str,int], duration: float, *, border_only: bool=False) -> dict[str,Any]:
    x=max(0,int(box.get("x",0))); y=max(0,int(box.get("y",0)))
    w=max(2,int(box.get("w",0))); h=max(2,int(box.get("h",0))); border=max(1,int(box.get("border",5)))
    if border_only:
        x+=2; y+=1; w=max(2,w-4); h=max(2,min(border,h-1))
    else:
        pad=min(max(border+3,6),max(6,min(w,h)//4))
        x+=pad; y+=pad; w=max(2,w-pad*2); h=max(2,h-pad*2)
    sample=max(0.8,min(6.0,float(duration)))
    filt=f"fps=2,crop={w}:{h}:{x}:{y},signalstats,metadata=print:key=lavfi.signalstats.YAVG"
    text=_run_ffmpeg(path,["-t",f"{sample:.3f}","-vf",filt,"-an"],max(45.0,sample*5.0+20.0))
    return parse_signalstats_luma(text)


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


def _safe_float(value: Any) -> float | None:
    try:
        out=float(value)
        return out if math.isfinite(out) else None
    except Exception:
        return None


def _stream_timing(video: dict[str,Any] | None, audios: list[dict[str,Any]]) -> dict[str,Any]:
    if not video or not audios:
        return {"available":False}
    audio=audios[0]
    vs=_safe_float(video.get("start_time")); a_s=_safe_float(audio.get("start_time"))
    vd=_safe_float(video.get("duration")); ad=_safe_float(audio.get("duration"))
    out={"available":bool(vs is not None or vd is not None or a_s is not None or ad is not None)}
    if vs is not None and a_s is not None: out["start_offset_seconds"]=round(abs(a_s-vs),4)
    if vd is not None and ad is not None: out["duration_delta_seconds"]=round(abs(ad-vd),4)
    try: out["audio_sample_rate"]=int(audio.get("sample_rate") or 0)
    except Exception: out["audio_sample_rate"]=0
    return out


def evaluate_render_qa(
    path: Path,
    clip: dict,
    words: list[dict],
    render_result: dict,
    s: Settings,
    game_events: list[dict] | None = None,
) -> dict[str,Any]:
    """Inspect the actual encoded Short and fail closed on creator-visible defects."""
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

    video=None; audios=[]; actual_duration=0.0; width=0; height=0
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
        timing=_stream_timing(video,audios); checks["av_timing"]=timing
        start_offset=float(timing.get("start_offset_seconds",0) or 0)
        duration_delta=float(timing.get("duration_delta_seconds",0) or 0)
        if start_offset > float(s.render_qa_max_av_start_offset_seconds):
            blockers.append(f"audio/video start times differ by {start_offset:.3f}s")
        elif start_offset > 0.20:
            warnings.append(f"audio/video start offset is {start_offset:.3f}s")
        if duration_delta > float(s.render_qa_max_av_duration_delta_seconds):
            blockers.append(f"audio/video stream durations differ by {duration_delta:.3f}s")
        elif duration_delta > 0.40:
            warnings.append(f"audio/video duration delta is {duration_delta:.3f}s")
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
        try:
            freeze=_freeze_stats(path,actual_duration); checks["freeze_frames"]=freeze
            if float(freeze["max_seconds"]) > float(s.render_qa_max_freeze_seconds):
                blockers.append(f"video appears frozen for {freeze['max_seconds']:.2f}s")
            if float(freeze["ratio"]) > float(s.render_qa_max_freeze_ratio):
                blockers.append(f"frozen frames occupy {float(freeze['ratio'])*100:.1f}% of the render")
        except Exception as e:
            blockers.append(f"freeze-frame QA failed: {type(e).__name__}: {e}")

    if audios and actual_duration>0:
        try:
            silence=_silence_stats(path,actual_duration); checks["silence"]=silence
            if float(silence["ratio"]) >= float(s.render_qa_max_silence_ratio):
                blockers.append(f"audio is effectively silent for {float(silence['ratio'])*100:.1f}% of the render")
            elif float(silence["ratio"]) >= 0.75:
                warnings.append(f"render is unusually quiet ({float(silence['ratio'])*100:.1f}% detected silence)")
        except Exception as e:
            blockers.append(f"audio QA failed: {type(e).__name__}: {e}")
        try:
            levels=_audio_level_stats(path,actual_duration); checks["audio_levels"]=levels
            mean_db=levels.get("mean_db"); peak_db=levels.get("max_db")
            if mean_db is None or peak_db is None:
                warnings.append("audio loudness could not be measured")
            else:
                if float(mean_db) < float(s.render_qa_min_mean_volume_db):
                    blockers.append(f"audio level is too low ({float(mean_db):.1f} dB mean)")
                elif float(mean_db) > float(s.render_qa_loud_mean_volume_db):
                    warnings.append(f"audio is unusually loud ({float(mean_db):.1f} dB mean)")
                if float(peak_db) >= float(s.render_qa_peak_warning_db):
                    warnings.append(f"audio peak reaches {float(peak_db):.2f} dBFS; inspect for clipping")
        except Exception as e:
            blockers.append(f"loudness QA failed: {type(e).__name__}: {e}")

    start=float(render_result.get("start",0) or 0); end=float(render_result.get("end",0) or 0)
    captions=_caption_metrics(words,start,end,s,str(clip.get("hook_text") or "")); checks["captions"]=captions
    if int(captions["max_group_chars"]) > int(s.render_qa_max_caption_chars):
        blockers.append(f"caption group is too wide ({captions['max_group_chars']} characters)")
    if int(captions["caption_margin_v"]) < int(s.render_qa_caption_safe_margin):
        blockers.append("caption safe margin is too close to platform UI")
    if int(captions["hook_chars"]) > 54:
        blockers.append("opening hook is too long to read safely")
    if int(captions["hook_margin_v"]) < int(s.render_qa_hook_safe_margin):
        blockers.append("opening hook is too close to the top platform UI safe zone")

    if width>0 and height>0 and actual_duration>0:
        try:
            pixel=_caption_pixel_bounds(path,width,height,actual_duration); checks["caption_pixels"]=pixel
            if pixel.get("available"):
                hsafe=int(s.render_qa_text_horizontal_safe_margin)
                for box in pixel.get("boxes") or []:
                    if box["x"] < hsafe or box["x"]+box["w"] > width-hsafe:
                        blockers.append("rendered caption/hook pixels enter the horizontal platform safe margin")
                        break
                upper=pixel.get("upper") or []; lower=pixel.get("lower") or []
                if int(captions["hook_chars"])>0 and not upper:
                    blockers.append("opening hook was expected but no rendered hook pixels were detected")
                if int(captions["group_count"])>0 and not lower:
                    blockers.append("captions were expected but no rendered caption pixels were detected")
                if upper and min(x["y"] for x in upper) < int(s.render_qa_hook_safe_margin):
                    blockers.append("rendered hook pixels enter the top platform safe zone")
                if lower and max(x["y"]+x["h"] for x in lower) > height-int(s.render_qa_caption_safe_margin):
                    blockers.append("rendered caption pixels enter the bottom platform safe zone")
            else:
                warnings.append("subtitle pixel QA unavailable because the render ASS file is missing")
        except Exception as e:
            blockers.append(f"caption pixel QA failed: {type(e).__name__}: {e}")

    motion=focus_motion_metrics(game_events,start,end); checks["framing_motion"]=motion
    if int(motion["points"]) >= 2:
        if float(motion["max_speed_per_second"]) > float(s.render_qa_max_focus_speed):
            blockers.append(f"smart framing moves too fast ({motion['max_speed_per_second']:.2f} frame-widths/sec)")
        if float(motion["total_motion"]) > float(s.render_qa_max_focus_total_motion):
            blockers.append(f"smart framing travels too much ({motion['total_motion']:.2f} normalized distance)")

    webcam_expected=bool(s.webcam_overlay_enabled and str(render_result.get("webcam_region") or ""))
    webcam_box=render_result.get("webcam_box") if isinstance(render_result.get("webcam_box"),dict) else None
    if bool(s.webcam_overlay_enabled) and bool(s.webcam_manual_enabled) and not str(render_result.get("webcam_region") or ""):
        warnings.append("webcam overlay is enabled but no webcam region was rendered")
    elif webcam_expected and webcam_box and actual_duration>0:
        try:
            border=_region_luma_stats(path,webcam_box,actual_duration,border_only=True)
            interior=_region_luma_stats(path,webcam_box,actual_duration,border_only=False)
            checks["webcam_pixels"]={"border":border,"interior":interior,"box":webcam_box}
            if int(border.get("samples") or 0)<=0:
                blockers.append("webcam border could not be verified in the encoded render")
            elif float(border.get("median") or 0) < float(s.render_qa_webcam_border_min_luma):
                blockers.append("expected webcam border is missing or obscured in the encoded render")
            if int(interior.get("samples") or 0)>0 and float(interior.get("mean") or 0) < float(s.render_qa_webcam_blank_luma):
                warnings.append("webcam interior appears nearly black; review camera visibility")
        except Exception as e:
            blockers.append(f"webcam pixel QA failed: {type(e).__name__}: {e}")
    elif webcam_expected and not webcam_box:
        warnings.append("webcam pixel QA skipped because legacy render geometry is unavailable")

    status="review" if blockers else "pass"
    return {
        "status":status,
        "passed":not blockers,
        "blockers":blockers,
        "warnings":warnings,
        "checks":checks,
    }
