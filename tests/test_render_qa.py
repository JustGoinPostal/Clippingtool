from pathlib import Path

from app.config import Settings
import app.render_qa as render_qa


def test_blackdetect_parser_measures_longest_and_total():
    text = """
    [blackdetect] black_start:0 black_end:0.4 black_duration:0.4
    [blackdetect] black_start:10 black_end:11.25 black_duration:1.25
    """
    result = render_qa.parse_blackdetect(text)
    assert result["total_seconds"] == 1.65
    assert result["max_seconds"] == 1.25
    assert len(result["segments"]) == 2


def test_silence_parser_closes_silence_at_eof():
    text = """
    [silencedetect] silence_start: 2.0
    [silencedetect] silence_end: 5.0 | silence_duration: 3.0
    [silencedetect] silence_start: 9.0
    """
    result = render_qa.parse_silencedetect(text, 12.0)
    assert result["total_seconds"] == 6.0
    assert result["max_seconds"] == 3.0
    assert result["ratio"] == 0.5


def test_focus_motion_uses_both_axes_and_speed():
    events = [
        {"time":1.0,"event_type":"bridge_focus","payload":{"focus_x_ratio":0.30,"focus_y_ratio":0.40}},
        {"time":2.0,"event_type":"bridge_focus","payload":{"focus_x_ratio":0.60,"focus_y_ratio":0.70}},
        {"time":4.0,"event_type":"pvp_kill","payload":{"focus_x_ratio":0.75,"focus_y_ratio":0.45}},
    ]
    result = render_qa.focus_motion_metrics(events,0.0,6.0)
    assert result["points"] == 3
    assert result["total_motion"] > 0.6
    assert result["max_speed_per_second"] > 0.4


def _safe_probe(duration: float = 22.0, audio: bool = True):
    streams=[{"codec_type":"video","width":1080,"height":1920,"codec_name":"h264"}]
    if audio: streams.append({"codec_type":"audio","codec_name":"aac"})
    return {"streams":streams,"format":{"duration":str(duration)}}


def test_finished_render_passes_when_media_is_safe(tmp_path: Path, monkeypatch):
    path=tmp_path/"safe.mp4"; path.write_bytes(b"x"*120_000)
    monkeypatch.setattr(render_qa,"probe",lambda p:_safe_probe())
    monkeypatch.setattr(render_qa,"_black_stats",lambda p,d:{"segments":[],"total_seconds":0.0,"max_seconds":0.0,"ratio":0.0})
    monkeypatch.setattr(render_qa,"_silence_stats",lambda p,d:{"segments":[],"total_seconds":0.0,"max_seconds":0.0,"ratio":0.0})
    s=Settings()
    words=[{"start":1.0,"end":1.2,"word":"no"},{"start":1.3,"end":1.6,"word":"way"}]
    result=render_qa.evaluate_render_qa(path,{"hook_text":"TWISTED BOW. NO WAY."},words,
        {"start":0.0,"end":22.0,"focus":"center","webcam_region":"manual"},s,game_events=[])
    assert result["passed"] is True
    assert result["status"] == "pass"
    assert result["blockers"] == []
    assert result["checks"]["width"] == 1080
    assert result["checks"]["audio_streams"] == 1


def test_finished_render_fails_closed_on_missing_audio_and_black_frames(tmp_path: Path, monkeypatch):
    path=tmp_path/"bad.mp4"; path.write_bytes(b"x"*120_000)
    monkeypatch.setattr(render_qa,"probe",lambda p:_safe_probe(audio=False))
    monkeypatch.setattr(render_qa,"_black_stats",lambda p,d:{"segments":[{"duration":2.0}],"total_seconds":2.0,"max_seconds":2.0,"ratio":0.10})
    s=Settings()
    words=[{"start":1.0,"end":1.2,"word":"THISISANEXTREMELYLONGCAPTIONWORDTHATCANNOTFITSANELY"}]
    result=render_qa.evaluate_render_qa(path,{"hook_text":"THIS HOOK IS FAR TOO LONG TO BE SAFELY READ AS A SHORT OVERLAY"},words,
        {"start":0.0,"end":22.0,"focus":"center","webcam_region":"manual"},s,game_events=[])
    joined=" | ".join(result["blockers"])
    assert result["passed"] is False
    assert result["status"] == "review"
    assert "no audio stream" in joined
    assert "black frame" in joined
    assert "caption group is too wide" in joined
    assert "opening hook is too long" in joined
