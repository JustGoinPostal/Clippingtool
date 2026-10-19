from pathlib import Path

from app.config import Settings
import app.pipeline as pipeline
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


def test_freeze_parser_closes_open_freeze_at_eof():
    text = """
    [freezedetect] lavfi.freezedetect.freeze_start: 2.0
    [freezedetect] lavfi.freezedetect.freeze_duration: 3.25
    [freezedetect] lavfi.freezedetect.freeze_end: 5.25
    [freezedetect] lavfi.freezedetect.freeze_start: 9.0
    """
    result=render_qa.parse_freezedetect(text,12.0)
    assert result["max_seconds"] == 3.25
    assert result["total_seconds"] == 6.25
    assert result["ratio"] == round(6.25/12.0,4)


def test_volume_and_pixel_parsers():
    levels=render_qa.parse_volumedetect("mean_volume: -18.4 dB\nmax_volume: -0.1 dB")
    assert levels == {"mean_db":-18.4,"max_db":-0.1}
    boxes=render_qa.parse_cropdetect("crop=800:120:140:80\ncrop=900:140:90:1600\ncrop=900:140:90:1600")
    assert boxes == [{"w":800,"h":120,"x":140,"y":80},{"w":900,"h":140,"x":90,"y":1600}]
    luma=render_qa.parse_signalstats_luma("lavfi.signalstats.YAVG=220\nlavfi.signalstats.YAVG=230")
    assert luma["median"] == 225.0


def test_stream_timing_detects_av_offset_and_duration_delta():
    video={"start_time":"0.000","duration":"22.000"}
    audio={"start_time":"0.620","duration":"20.700","sample_rate":"48000"}
    timing=render_qa._stream_timing(video,[audio])
    assert timing["start_offset_seconds"] == 0.62
    assert timing["duration_delta_seconds"] == 1.3
    assert timing["audio_sample_rate"] == 48000


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
    streams=[{"codec_type":"video","width":1080,"height":1920,"codec_name":"h264","start_time":"0","duration":str(duration)}]
    if audio:
        streams.append({"codec_type":"audio","codec_name":"aac","start_time":"0.02","duration":str(duration-0.02),"sample_rate":"48000"})
    return {"streams":streams,"format":{"duration":str(duration)}}


def _safe_saturation():
    return {
        "sample_count":1000,
        "max_abs":20000,
        "near_fullscale_samples":0,
        "hard_fullscale_samples":0,
        "near_fullscale_ratio":0.0,
        "hard_fullscale_ratio":0.0,
        "longest_hard_run":0,
    }


def _patch_safe_media(monkeypatch):
    monkeypatch.setattr(render_qa,"_black_stats",lambda p,d:{"segments":[],"total_seconds":0.0,"max_seconds":0.0,"ratio":0.0})
    monkeypatch.setattr(render_qa,"_freeze_stats",lambda p,d:{"segments":[],"total_seconds":0.0,"max_seconds":0.0,"ratio":0.0})
    monkeypatch.setattr(render_qa,"_silence_stats",lambda p,d:{"segments":[],"total_seconds":0.0,"max_seconds":0.0,"ratio":0.0})
    monkeypatch.setattr(render_qa,"_audio_level_stats",lambda p,d:{"mean_db":-18.0,"max_db":-1.0})
    monkeypatch.setattr(render_qa,"pcm_saturation_stats",lambda p,d:_safe_saturation())
    monkeypatch.setattr(render_qa,"_caption_pixel_bounds",lambda p,w,h,d:{"available":False,"boxes":[],"upper":[],"lower":[]})


def test_finished_render_passes_when_media_is_safe(tmp_path: Path, monkeypatch):
    path=tmp_path/"safe.mp4"; path.write_bytes(b"x"*120_000)
    monkeypatch.setattr(render_qa,"probe",lambda p:_safe_probe())
    _patch_safe_media(monkeypatch)
    s=Settings()
    words=[{"start":1.0,"end":1.2,"word":"no"},{"start":1.3,"end":1.6,"word":"way"}]
    result=render_qa.evaluate_render_qa(path,{"hook_text":"TWISTED BOW. NO WAY."},words,
        {"start":0.0,"end":22.0,"focus":"center","webcam_region":"manual"},s,game_events=[])
    assert result["passed"] is True
    assert result["status"] == "pass"
    assert result["blockers"] == []
    assert result["checks"]["width"] == 1080
    assert result["checks"]["audio_streams"] == 1
    assert result["checks"]["audio_levels"]["mean_db"] == -18.0
    assert result["checks"]["audio_saturation"]["hard_fullscale_ratio"] == 0.0


def test_severe_full_scale_saturation_blocks_finished_render(tmp_path: Path, monkeypatch):
    path=tmp_path/"saturated.mp4"; path.write_bytes(b"x"*120_000)
    monkeypatch.setattr(render_qa,"probe",lambda p:_safe_probe())
    _patch_safe_media(monkeypatch)
    monkeypatch.setattr(render_qa,"pcm_saturation_stats",lambda p,d:{
        "sample_count":480000,
        "max_abs":32768,
        "near_fullscale_samples":12000,
        "hard_fullscale_samples":4800,
        "near_fullscale_ratio":0.025,
        "hard_fullscale_ratio":0.01,
        "longest_hard_run":400,
    })
    result=render_qa.evaluate_render_qa(path,{"hook_text":""},[],
        {"start":0.0,"end":22.0,"focus":"center","webcam_region":""},Settings(),game_events=[])
    assert result["passed"] is False
    assert any("full-scale saturation" in x for x in result["blockers"])
    assert result["checks"]["audio_saturation"]["longest_hard_run"] == 400


def test_finished_render_fails_closed_on_missing_audio_black_and_freeze(tmp_path: Path, monkeypatch):
    path=tmp_path/"bad.mp4"; path.write_bytes(b"x"*120_000)
    monkeypatch.setattr(render_qa,"probe",lambda p:_safe_probe(audio=False))
    monkeypatch.setattr(render_qa,"_black_stats",lambda p,d:{"segments":[{"duration":2.0}],"total_seconds":2.0,"max_seconds":2.0,"ratio":0.10})
    monkeypatch.setattr(render_qa,"_freeze_stats",lambda p,d:{"segments":[{"duration":7.0}],"total_seconds":7.0,"max_seconds":7.0,"ratio":0.32})
    monkeypatch.setattr(render_qa,"_caption_pixel_bounds",lambda p,w,h,d:{"available":False,"boxes":[],"upper":[],"lower":[]})
    s=Settings()
    words=[{"start":1.0,"end":1.2,"word":"THISISANEXTREMELYLONGCAPTIONWORDTHATCANNOTFITSANELY"}]
    result=render_qa.evaluate_render_qa(path,{"hook_text":"THIS HOOK IS FAR TOO LONG TO BE SAFELY READ AS A SHORT OVERLAY"},words,
        {"start":0.0,"end":22.0,"focus":"center","webcam_region":"manual"},s,game_events=[])
    joined=" | ".join(result["blockers"])
    assert result["passed"] is False
    assert result["status"] == "review"
    assert "no audio stream" in joined
    assert "black frame" in joined
    assert "frozen" in joined
    assert "caption group is too wide" in joined
    assert "opening hook is too long" in joined


def test_caption_pixels_fail_when_the_real_render_enters_safe_zones(tmp_path: Path, monkeypatch):
    path=tmp_path/"caption.mp4"; path.write_bytes(b"x"*120_000)
    monkeypatch.setattr(render_qa,"probe",lambda p:_safe_probe())
    _patch_safe_media(monkeypatch)
    monkeypatch.setattr(render_qa,"_caption_pixel_bounds",lambda p,w,h,d:{
        "available":True,
        "boxes":[{"w":1040,"h":100,"x":10,"y":40},{"w":800,"h":120,"x":140,"y":1740}],
        "upper":[{"w":1040,"h":100,"x":10,"y":40}],
        "lower":[{"w":800,"h":120,"x":140,"y":1740}],
    })
    s=Settings()
    words=[{"start":1.0,"end":1.2,"word":"no"}]
    result=render_qa.evaluate_render_qa(path,{"hook_text":"NO WAY"},words,
        {"start":0.0,"end":22.0,"webcam_region":""},s,game_events=[])
    joined=" | ".join(result["blockers"])
    assert "horizontal platform safe margin" in joined
    assert "top platform safe zone" in joined


def test_webcam_border_is_verified_from_encoded_pixels(tmp_path: Path, monkeypatch):
    path=tmp_path/"cam.mp4"; path.write_bytes(b"x"*120_000)
    monkeypatch.setattr(render_qa,"probe",lambda p:_safe_probe())
    _patch_safe_media(monkeypatch)
    calls=[]
    def luma(p,box,d,border_only=False):
        calls.append(border_only)
        return {"samples":6,"mean":220.0 if border_only else 80.0,"median":220.0 if border_only else 80.0,"min":70.0,"max":230.0}
    monkeypatch.setattr(render_qa,"_region_luma_stats",luma)
    s=Settings()
    result=render_qa.evaluate_render_qa(path,{"hook_text":""},[],{
        "start":0.0,"end":22.0,"webcam_region":"manual",
        "webcam_box":{"x":345,"y":54,"w":390,"h":220,"border":5},
    },s,game_events=[])
    assert result["passed"] is True
    assert calls == [True,False]
    assert result["checks"]["webcam_pixels"]["border"]["median"] == 220.0


def test_webcam_missing_border_blocks_publish(tmp_path: Path, monkeypatch):
    path=tmp_path/"cam_bad.mp4"; path.write_bytes(b"x"*120_000)
    monkeypatch.setattr(render_qa,"probe",lambda p:_safe_probe())
    _patch_safe_media(monkeypatch)
    monkeypatch.setattr(render_qa,"_region_luma_stats",lambda p,b,d,border_only=False:{
        "samples":6,"mean":50.0,"median":50.0,"min":40.0,"max":60.0})
    s=Settings()
    result=render_qa.evaluate_render_qa(path,{"hook_text":""},[],{
        "start":0.0,"end":22.0,"webcam_region":"manual",
        "webcam_box":{"x":345,"y":54,"w":390,"h":220,"border":5},
    },s,game_events=[])
    assert result["passed"] is False
    assert any("webcam border" in x for x in result["blockers"])


def test_failed_variant_does_not_clear_an_existing_safe_best(monkeypatch):
    calls=[]
    monkeypatch.setattr(pipeline.db,"exec_sql",lambda sql,args=(): calls.append((sql,args)))
    best={"id":7,"variant":"medium","qa_status":"pass"}
    returned=pipeline._apply_render_state(42,{"passed":False},best)
    assert returned is best
    assert len(calls)==1
    assert "status='rendered'" in calls[0][0]
    assert "best_variant=''" not in calls[0][0]
