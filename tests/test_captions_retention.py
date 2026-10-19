from pathlib import Path

from app.captions import write_ass
from app.config import Settings


def test_captions_use_active_word_highlight_and_short_hook(tmp_path: Path):
    words=[
        {"start":0.0,"end":0.30,"word":"why"},
        {"start":0.31,"end":0.60,"word":"are"},
        {"start":0.61,"end":0.95,"word":"these"},
        {"start":0.96,"end":1.30,"word":"monkeys"},
    ]
    out=tmp_path/"captions.ass"
    s=Settings()
    write_ass(
        words,0.0,3.0,out,s,
        hook_text="WAIT THESE MONKEYS DROP SMALL BONES FOR SOME REASON REALLY",
    )
    text=out.read_text(encoding="utf-8-sig")
    assert "\\1c&H0000EFFF&" in text
    assert "\\fscx" in text
    assert text.count("Dialogue: 0,") >= 4
    hook=[line for line in text.splitlines() if ",Hook," in line][0]
    assert "REASON" not in hook
    assert "REALLY" not in hook
