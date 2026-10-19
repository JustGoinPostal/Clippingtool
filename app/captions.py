from __future__ import annotations

from pathlib import Path

from .config import Settings

EMPHASIS = {
    "no","way","lets","let's","go","omg","god","bro","dead","killed","kill",
    "smite","smited","spec","purple","unique","rare","tbow","scythe","shadow",
    "pet","what","fuck","shit","insane","huge","clapped","wait","why",
}


def _ass_time(sec: float):
    sec=max(0,sec); h=int(sec//3600); sec-=h*3600; m=int(sec//60); sec-=m*60
    return f"{h}:{m:02d}:{sec:05.2f}"


def _esc(text: str):
    return text.replace("\\","\\\\").replace("{","\\{").replace("}","\\}").replace("\n"," ")


def _token(text: str):
    return "".join(c.lower() for c in text if c.isalnum() or c in {"'"})


def _short_hook(text: str, max_words: int, max_chars: int) -> str:
    words=[x for x in str(text or "").strip().split() if x]
    if not words:
        return ""
    words=words[:max(1,int(max_words))]
    out=" ".join(words)
    if len(out) > max(8,int(max_chars)):
        limit=max(8,int(max_chars))
        trimmed=[]
        used=0
        for word in words:
            extra=len(word)+(1 if trimmed else 0)
            if used+extra > limit:
                break
            trimmed.append(word); used+=extra
        out=" ".join(trimmed) or out[:limit].rstrip()
    return out.strip()


def _wrap_hook(text: str, line_chars: int = 22) -> str:
    words=text.split()
    if len(words) < 2:
        return _esc(text)
    lines=[""]
    for word in words:
        trial=(lines[-1]+" "+word).strip()
        if lines[-1] and len(trial)>line_chars and len(lines)<2:
            lines.append(word)
        else:
            lines[-1]=trial
    return r"\N".join(_esc(line) for line in lines if line)


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
Style: Default,{s.caption_font},{s.caption_font_size},&H00FFFFFF,&H0000EFFF,&H00101010,&H74000000,-1,0,0,0,100,100,0,0,1,6,3,2,72,72,{s.caption_margin_v},1
Style: Hook,{s.caption_font},{s.hook_font_size},&H00FFFFFF,&H0000FFFF,&H00101010,&H90000000,-1,0,0,0,100,100,0,0,1,7,3,8,85,85,{s.hook_margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines=[]; group=[]
    max_words=max(2,min(5,int(s.caption_words_per_group)))
    max_chars=max(18,min(48,int(getattr(s,"caption_max_chars",34))))
    active_scale=max(104,min(132,int(getattr(s,"caption_active_word_scale",112))))
    emph_scale=max(active_scale,int(s.caption_emphasis_scale))

    if s.auto_hook_enabled and (hook_text or "").strip():
        hook=_short_hook(
            hook_text,
            int(getattr(s,"hook_max_words",7)),
            int(getattr(s,"hook_max_chars",44)),
        )
        hook=_wrap_hook(hook.upper(),max(16,min(26,int(getattr(s,"hook_line_chars",22)))))
        requested=min(2.3,float(s.hook_duration_seconds))
        hook_end=min(max(0.8,requested),max(0.8,clip_end-clip_start))
        anim="{\\fad(70,150)\\fscx108\\fscy108\\t(0,160,\\fscx100\\fscy100)}"
        lines.append(
            f"Dialogue: 2,{_ass_time(0)},{_ass_time(hook_end)},Hook,,0,0,0,,{anim}{hook}"
        )

    def phrase_text(g, active_index: int) -> str:
        chunks=[]
        for idx,x in enumerate(g):
            raw=x["word"].upper() if s.caption_uppercase else x["word"]
            escaped=_esc(raw)
            if idx==active_index:
                scale=emph_scale if _token(x["word"]) in EMPHASIS else active_scale
                chunks.append(
                    f"{{\\1c&H0000EFFF&\\b1\\fscx{scale}\\fscy{scale}}}{escaped}"
                    "{\\1c&H00FFFFFF&\\b1\\fscx100\\fscy100}"
                )
            else:
                chunks.append(escaped)
        return " ".join(chunks)

    def flush(g):
        if not g:
            return
        group_start=g[0]["start"]
        group_end=max(g[-1]["end"],group_start+0.35)
        for idx,x in enumerate(g):
            start=max(group_start,float(x["start"]))
            next_start=float(g[idx+1]["start"]) if idx+1<len(g) else group_end
            end=max(start+0.10,min(group_end,max(float(x["end"]),next_start)))
            if idx==0:
                pop="{\\fad(20,0)\\fscx104\\fscy104\\t(0,100,\\fscx100\\fscy100)}"
            else:
                pop=""
            lines.append(
                f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,"
                + pop + phrase_text(g,idx)
            )

    for w in relevant:
        prospective=" ".join([x["word"] for x in group]+[w["word"]])
        previous=str(group[-1]["word"]) if group else ""
        if group and (
            len(group)>=max_words
            or len(prospective)>max_chars
            or w["start"]-group[0]["start"]>2.0
            or w["start"]-group[-1]["end"]>0.50
            or (len(group)>=2 and previous.rstrip().endswith((".","!","?")))
        ):
            flush(group); group=[]
        group.append(w)
    flush(group)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(header+"\n".join(lines),encoding="utf-8-sig")
