from pathlib import Path

from app import browser_preview


def _probe(video="h264",audio="aac"):
    streams=[{"codec_type":"video","codec_name":video}]
    if audio: streams.append({"codec_type":"audio","codec_name":audio})
    return {"streams":streams,"format":{}}


def test_safe_h264_mp4_is_served_directly(tmp_path: Path, monkeypatch):
    source=tmp_path/"vod.mp4"; source.write_bytes(b"x"*120_000)
    monkeypatch.setattr(browser_preview,"probe",lambda p:_probe("h264","aac"))
    out,mode=browser_preview.ensure_browser_preview(source,tmp_path/"cache")
    assert out==source.resolve()
    assert mode=="direct"


def test_mkv_h264_aac_is_remuxed_without_video_reencode(tmp_path: Path, monkeypatch):
    source=tmp_path/"vod.mkv"; source.write_bytes(b"x"*120_000)
    monkeypatch.setattr(browser_preview,"probe",lambda p:_probe("h264","aac"))
    monkeypatch.setattr(browser_preview,"require_ffmpeg",lambda:None)
    calls=[]
    def fake_run(cmd,check,timeout):
        calls.append(cmd)
        Path(cmd[-1]).write_bytes(b"p"*150_000)
    monkeypatch.setattr(browser_preview.subprocess,"run",fake_run)
    out,mode=browser_preview.ensure_browser_preview(source,tmp_path/"cache")
    assert mode=="generated"
    assert out.exists()
    cmd=calls[0]
    assert ["-c:v","copy"] == cmd[cmd.index("-c:v"):cmd.index("-c:v")+2]
    assert ["-c:a","copy"] == cmd[cmd.index("-c:a"):cmd.index("-c:a")+2]


def test_h264_opus_keeps_video_and_transcodes_audio_only(tmp_path: Path, monkeypatch):
    source=tmp_path/"vod.mkv"; source.write_bytes(b"x"*120_000)
    monkeypatch.setattr(browser_preview,"probe",lambda p:_probe("h264","opus"))
    monkeypatch.setattr(browser_preview,"require_ffmpeg",lambda:None)
    calls=[]
    def fake_run(cmd,check,timeout):
        calls.append(cmd); Path(cmd[-1]).write_bytes(b"p"*150_000)
    monkeypatch.setattr(browser_preview.subprocess,"run",fake_run)
    browser_preview.ensure_browser_preview(source,tmp_path/"cache")
    cmd=calls[0]
    assert cmd[cmd.index("-c:v")+1]=="copy"
    assert cmd[cmd.index("-c:a")+1]=="aac"


def test_non_h264_video_uses_compatibility_transcode(tmp_path: Path, monkeypatch):
    source=tmp_path/"vod.mov"; source.write_bytes(b"x"*120_000)
    monkeypatch.setattr(browser_preview,"probe",lambda p:_probe("hevc","aac"))
    monkeypatch.setattr(browser_preview,"require_ffmpeg",lambda:None)
    calls=[]
    def fake_run(cmd,check,timeout):
        calls.append(cmd); Path(cmd[-1]).write_bytes(b"p"*150_000)
    monkeypatch.setattr(browser_preview.subprocess,"run",fake_run)
    browser_preview.ensure_browser_preview(source,tmp_path/"cache")
    cmd=calls[0]
    assert cmd[cmd.index("-c:v")+1]=="libx264"
    assert "yuv420p" in cmd


def test_preview_cache_key_changes_when_source_changes(tmp_path: Path):
    source=tmp_path/"vod.mkv"; source.write_bytes(b"one")
    first=browser_preview.preview_key(source)
    source.write_bytes(b"a different recording")
    second=browser_preview.preview_key(source)
    assert first!=second
