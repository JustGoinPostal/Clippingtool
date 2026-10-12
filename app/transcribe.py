from __future__ import annotations
import json
from pathlib import Path
from .config import Settings

def _resolve_device(settings: Settings):
    if settings.device != "auto": return settings.device, settings.compute_type
    try:
        import ctranslate2
        cuda = ctranslate2.get_cuda_device_count() > 0
    except Exception:
        cuda = False
    if cuda:
        return "cuda", ("float16" if settings.compute_type == "auto" else settings.compute_type)
    return "cpu", ("int8" if settings.compute_type == "auto" else settings.compute_type)

def transcribe(video: Path, settings: Settings, cache_file: Path, progress=None) -> dict:
    if cache_file.exists(): return json.loads(cache_file.read_text(encoding="utf-8"))
    from faster_whisper import WhisperModel
    device, compute = _resolve_device(settings)
    if progress: progress(f"Loading Whisper {settings.whisper_model} on {device} ({compute})")
    model=WhisperModel(settings.whisper_model, device=device, compute_type=compute)
    segments, info = model.transcribe(str(video), language=settings.language or None,
                                      word_timestamps=True, vad_filter=True, beam_size=5)
    out={"language": getattr(info,"language",settings.language), "segments":[], "words":[]}
    for i, seg in enumerate(segments):
        row={"start":float(seg.start),"end":float(seg.end),"text":seg.text.strip()}
        out["segments"].append(row)
        if getattr(seg,"words",None):
            for w in seg.words:
                if w.start is None or w.end is None: continue
                out["words"].append({"start":float(w.start),"end":float(w.end),"word":w.word.strip()})
        if progress and i and i % 50 == 0: progress(f"Transcribed {i} speech segments")
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out
