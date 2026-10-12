from __future__ import annotations
from pathlib import Path
from .config import Settings

def _ass_time(sec: float):
    sec=max(0,sec); h=int(sec//3600); sec-=h*3600; m=int(sec//60); sec-=m*60
    return f"{h}:{m:02d}:{sec:05.2f}"

def _esc(s: str):
    return s.replace("\\","\\\\").replace("{","\\{").replace("}","\\}").replace("\n"," ")

def write_ass(words: list[dict], clip_start: float, clip_end: float, out: Path, s: Settings):
    relevant=[]
    for w in words:
        if w["end"] < clip_start or w["start"] > clip_end: continue
        relevant.append({"start":max(0,w["start"]-clip_start),"end":max(0,w["end"]-clip_start),"word":w["word"]})
    header=f"""[Script Info]
ScriptType: v4.00+
PlayResX: {s.render_width}
PlayResY: {s.render_height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{s.caption_font},{s.caption_font_size},&H00FFFFFF,&H0000FFFF,&H00101010,&H78000000,-1,0,0,0,100,100,0,0,1,5,2,2,70,70,190,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines=[]; group=[]
    def flush(g):
        if not g: return
        start=g[0]["start"]; end=max(g[-1]["end"],start+0.4); chunks=[]
        for x in g:
            cs=max(1,round((x["end"]-x["start"])*100)); chunks.append(f"{{\\k{cs}}}{_esc(x['word'].upper())}")
        lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,"+" ".join(chunks))
    for w in relevant:
        if group and (len(group)>=5 or w["start"]-group[0]["start"]>2.3 or w["start"]-group[-1]["end"]>0.6):
            flush(group); group=[]
        group.append(w)
    flush(group)
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(header+"\n".join(lines),encoding="utf-8-sig")
