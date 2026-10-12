from __future__ import annotations
from pathlib import Path
from .config import Settings

EMPHASIS = {
    "no","way","lets","let's","go","omg","god","bro","dead","killed","kill",
    "smite","smited","spec","purple","unique","rare","tbow","scythe","shadow",
    "pet","what","fuck","shit","insane","huge","clapped"
}

def _ass_time(sec: float):
    sec=max(0,sec); h=int(sec//3600); sec-=h*3600; m=int(sec//60); sec-=m*60
    return f"{h}:{m:02d}:{sec:05.2f}"

def _esc(text: str):
    return text.replace("\\","\\\\").replace("{","\\{").replace("}","\\}").replace("\n"," ")

def _token(text: str):
    return "".join(c.lower() for c in text if c.isalnum() or c in {"'"})

def write_ass(words: list[dict], clip_start: float, clip_end: float, out: Path, s: Settings,
              hook_text: str=""):
    relevant=[]
    for w in words:
        if float(w["end"]) < clip_start or float(w["start"]) > clip_end:
            continue
        relevant.append({
            "start":max(0.0,float(w["start"])-clip_start),
            "end":max(0.0,float(w["end"])-clip_start),
            "word":str(w["word"]).strip()
        })
    header=f"""[Script Info]
ScriptType: v4.00+
PlayResX: {s.render_width}
PlayResY: {s.render_height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{s.caption_font},{s.caption_font_size},&H00FFFFFF,&H0000F2FF,&H00101010,&H74000000,-1,0,0,0,100,100,0,0,1,6,3,2,72,72,{s.caption_margin_v},1
Style: Hook,{s.caption_font},{s.hook_font_size},&H00FFFFFF,&H0000FFFF,&H00101010,&H90000000,-1,0,0,0,100,100,0,0,1,7,3,8,85,85,{s.hook_margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines=[]; group=[]
    max_words=max(2,int(s.caption_words_per_group))
    emph_scale=max(100,int(s.caption_emphasis_scale))

    if s.auto_hook_enabled and (hook_text or "").strip():
        hook=_esc((hook_text or "").strip().upper()[:72])
        hook_end=min(max(0.8,float(s.hook_duration_seconds)),max(0.8,clip_end-clip_start))
        anim="{\\fad(80,160)\\fscx112\\fscy112\\t(0,180,\\fscx100\\fscy100)}"
        lines.append(
            f"Dialogue: 2,{_ass_time(0)},{_ass_time(hook_end)},Hook,,0,0,0,,{anim}{hook}"
        )

    def flush(g):
        if not g: return
        start=g[0]["start"]; end=max(g[-1]["end"],start+0.45)
        chunks=[]
        for x in g:
            cs=max(1,round((x["end"]-x["start"])*100))
            raw=x["word"].upper() if s.caption_uppercase else x["word"]
            escaped=_esc(raw)
            if _token(x["word"]) in EMPHASIS:
                chunks.append(
                    f"{{\\kf{cs}\\b1\\fscx{emph_scale}\\fscy{emph_scale}}}"
                    f"{escaped}{{\\b0\\fscx100\\fscy100}}"
                )
            else:
                chunks.append(f"{{\\kf{cs}}}{escaped}")
        pop="{\\fad(35,70)\\fscx106\\fscy106\\t(0,140,\\fscx100\\fscy100)}"
        lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,"
            + pop + " ".join(chunks)
        )

    for w in relevant:
        if group and (
            len(group)>=max_words
            or w["start"]-group[0]["start"]>2.15
            or w["start"]-group[-1]["end"]>0.55
        ):
            flush(group); group=[]
        group.append(w)
    flush(group)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(header+"\n".join(lines),encoding="utf-8-sig")
