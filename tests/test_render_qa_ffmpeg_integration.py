from pathlib import Path
import subprocess

from app.captions import write_ass
from app.config import Settings
from app.render_qa import evaluate_render_qa


def _ffmpeg_filter_path(path: Path) -> str:
    value=str(path).replace("\\","/")
    return value.replace(":","\\:").replace("'","\\'")


def test_real_ffmpeg_finished_render_passes_commercial_qa(tmp_path: Path):
    """Exercise the actual FFmpeg/libass/pixel/audio QA path, not mocks."""
    s=Settings(
        render_width=720,
        render_height=1280,
        caption_font_size=50,
        hook_font_size=44,
        caption_margin_v=170,
        hook_margin_v=95,
        webcam_overlay_width=280,
        render_qa_min_width=720,
        render_qa_min_height=1280,
        render_qa_caption_safe_margin=100,
        render_qa_text_horizontal_safe_margin=24,
        render_qa_hook_safe_margin=50,
        render_qa_webcam_border_min_luma=135.0,
    )
    output=tmp_path/"qa_smoke.mp4"
    ass=output.with_suffix(".ass")
    words=[
        {"start":1.00,"end":1.35,"word":"NO"},
        {"start":1.38,"end":1.85,"word":"WAY"},
        {"start":2.00,"end":2.55,"word":"PURPLE"},
    ]
    write_ass(words,0.0,6.4,ass,s,hook_text="BIG DROP")

    webcam={"x":220,"y":54,"w":280,"h":160,"border":5}
    vf=(
        f"drawbox=x={webcam['x']}:y={webcam['y']}:w={webcam['w']}:h={webcam['h']}:"
        f"color=white@0.95:t={webcam['border']},"
        f"ass='{_ffmpeg_filter_path(ass)}'"
    )
    cmd=[
        "ffmpeg","-hide_banner","-loglevel","error","-y",
        "-f","lavfi","-i","testsrc2=size=720x1280:rate=15:duration=6.4",
        "-f","lavfi","-i","sine=frequency=880:sample_rate=48000:duration=6.4",
        "-vf",vf,"-map","0:v:0","-map","1:a:0",
        "-c:v","libx264","-preset","ultrafast","-crf","28","-pix_fmt","yuv420p",
        "-c:a","aac","-b:a","128k","-shortest",str(output),
    ]
    subprocess.run(cmd,check=True,capture_output=True,text=True,timeout=90)
    assert output.exists() and output.stat().st_size>100_000

    result=evaluate_render_qa(
        output,
        {"hook_text":"BIG DROP"},
        words,
        {
            "start":0.0,"end":6.4,"focus":"center","webcam_region":"manual",
            "webcam_box":webcam,
        },
        s,
        game_events=[],
    )
    assert result["passed"] is True, result
    assert result["checks"]["caption_pixels"]["available"] is True
    assert result["checks"]["caption_pixels"]["upper"]
    assert result["checks"]["caption_pixels"]["lower"]
    assert result["checks"]["webcam_pixels"]["border"]["median"] >= s.render_qa_webcam_border_min_luma
    assert result["checks"]["audio_levels"]["mean_db"] is not None
    assert result["checks"]["audio_saturation"]["hard_fullscale_ratio"] < s.render_qa_saturation_warning_ratio
    assert result["checks"]["audio_saturation"]["longest_hard_run"] < s.render_qa_saturation_block_run_samples
    assert result["checks"]["freeze_frames"]["max_seconds"] <= s.render_qa_max_freeze_seconds
