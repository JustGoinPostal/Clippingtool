from __future__ import annotations
import json
import secrets as pysecrets
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

from .paths import APP_HOME as ROOT, ensure_app_home

CONFIG_PATH = ROOT / "config.json"
EXAMPLE_PATH = ROOT / "config.example.json"

class Settings(BaseModel):
    watch_folder: str = "data/input"
    output_folder: str = "data/output"
    cache_folder: str = "data/cache"
    auto_process_new_files: bool = True
    poll_seconds: int = 45
    whisper_model: str = "small.en"
    device: str = "auto"
    compute_type: str = "auto"
    language: str = "en"
    max_candidates: int = 20
    video_analysis_enabled: bool = True
    video_sample_seconds: float = 2.0
    targeted_video_analysis_enabled: bool = True
    targeted_video_pre_seconds: float = 16.0
    targeted_video_post_seconds: float = 28.0
    targeted_video_audio_z: float = 1.35
    targeted_video_merge_gap_seconds: float = 6.0
    targeted_video_max_window_seconds: float = 120.0
    targeted_video_max_windows: int = 80
    smart_boundaries: bool = True
    diversity_per_type: int = 6
    default_clip_seconds: int = 50
    pre_roll_seconds: int = 12
    post_roll_seconds: int = 28

    layout: str = "osrs_focus"
    render_width: int = 1080
    render_height: int = 1920
    render_variants: dict[str, int] = Field(default_factory=lambda: {"short": 22, "medium": 38, "long": 58})
    primary_variant: str = "medium"
    dead_air_trim_enabled: bool = True
    dead_air_padding_seconds: float = 0.55
    dead_air_min_clip_seconds: float = 6.0
    osrs_focus_panel_height: int = 700
    osrs_focus_margin: int = 50

    webcam_overlay_enabled: bool = True
    webcam_region: str = "auto"
    webcam_crop_width_ratio: float = 0.30
    webcam_manual_enabled: bool = True
    webcam_manual_x_ratio: float = 0.720
    webcam_manual_y_ratio: float = 0.000
    webcam_manual_width_ratio: float = 0.280
    webcam_manual_height_ratio: float = 0.340
    webcam_overlay_width: int = 390
    webcam_overlay_y: int = 500

    caption_font: str = "Arial"
    caption_font_size: int = 76
    caption_words_per_group: int = 4
    caption_margin_v: int = 205
    caption_emphasis_scale: int = 118
    caption_uppercase: bool = True

    auto_hook_enabled: bool = True
    hook_duration_seconds: float = 2.8
    hook_font_size: int = 68
    hook_margin_v: int = 110
    dynamic_zoom_enabled: bool = True
    dynamic_zoom_strength: float = 0.16
    dynamic_zoom_seconds: float = 2.6
    dynamic_beat_interval_seconds: float = 5.0
    dynamic_beat_seconds: float = 1.15
    quality_scoring_enabled: bool = True
    best_variant_auto_select: bool = True

    render_qa_enabled: bool = True
    render_qa_block_publish: bool = True
    render_qa_require_audio: bool = True
    render_qa_min_width: int = 720
    render_qa_min_height: int = 1280
    render_qa_max_black_seconds: float = 0.90
    render_qa_max_black_ratio: float = 0.08
    render_qa_max_silence_ratio: float = 0.97
    render_qa_max_focus_speed: float = 0.55
    render_qa_max_focus_total_motion: float = 2.80
    render_qa_max_caption_chars: int = 44
    render_qa_caption_safe_margin: int = 120
    render_qa_text_horizontal_safe_margin: int = 36
    render_qa_hook_safe_margin: int = 60
    render_qa_max_freeze_seconds: float = 4.5
    render_qa_max_freeze_ratio: float = 0.28
    render_qa_min_mean_volume_db: float = -40.0
    render_qa_loud_mean_volume_db: float = -8.0
    render_qa_peak_warning_db: float = -0.10
    render_qa_saturation_warning_ratio: float = 0.0001
    render_qa_saturation_block_ratio: float = 0.005
    render_qa_saturation_block_run_samples: int = 256
    render_qa_max_av_start_offset_seconds: float = 0.45
    render_qa_max_av_duration_delta_seconds: float = 0.90
    render_qa_webcam_border_min_luma: float = 150.0
    render_qa_webcam_blank_luma: float = 12.0

    publishing_enabled: bool = True
    publish_poll_seconds: int = 20
    publish_max_attempts: int = 5
    publish_retry_base_seconds: int = 60
    publish_retry_max_seconds: int = 3600
    publish_stale_seconds: int = 600
    youtube_resumable_retries: int = 5
    youtube_default_privacy: str = "private"
    tiktok_default_privacy: str = "SELF_ONLY"

    auto_cover_enabled: bool = True
    youtube_set_thumbnail: bool = True
    instagram_graph_version: str = "v26.0"
    instagram_default_privacy: str = "public"
    instagram_share_to_feed: bool = True
    duplicate_window_days: int = 30
    duplicate_similarity_threshold: float = 0.62
    distribution_slots: list[str] = Field(default_factory=lambda: ["12:00", "18:30"])
    platform_offsets_minutes: dict[str, int] = Field(default_factory=lambda: {"youtube": 0, "tiktok": 20, "instagram": 40})

    analytics_enabled: bool = True
    analytics_refresh_hours: float = 6.0
    analytics_history_days: int = 90
    analytics_collection_min_age_hours: float = 6.0
    analytics_learning_enabled: bool = True
    analytics_learning_weight: float = 0.35
    analytics_learning_min_age_hours: float = 24.0
    analytics_learning_min_views: int = 100

    synchronized_crosspost_enabled: bool = True
    platform_fit_enabled: bool = True
    platform_variant_min_samples: int = 3

    auto_update_enabled: bool = True
    update_check_hours: float = 6.0
    update_manifest_url: str = "https://github.com/JustGoinPostal/Clippingtool/releases/latest/download/postal-autoclip-update.json"

    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = ""
    runelite_bridge_enabled: bool = True
    runelite_bridge_token: str = "postal-local"
    runelite_event_window_seconds: float = 8.0
    big_hit_threshold: int = 35
    keywords: dict[str, float] = Field(default_factory=dict)

    def path(self, value: str) -> Path:
        p = Path(value).expanduser()
        return p if p.is_absolute() else ROOT / p

    @property
    def watch_path(self) -> Path: return self.path(self.watch_folder)
    @property
    def output_path(self) -> Path: return self.path(self.output_folder)
    @property
    def cache_path(self) -> Path: return self.path(self.cache_folder)


def _new_config_payload() -> dict[str, Any]:
    if EXAMPLE_PATH.exists():
        try:
            data = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
            data = dict(data) if isinstance(data, dict) else {}
        except Exception:
            data = {}
    else:
        data = {}
    if not str(data.get("runelite_bridge_token") or "").strip() or data.get("runelite_bridge_token") == "postal-local":
        data["runelite_bridge_token"] = pysecrets.token_urlsafe(24)
    return Settings.model_validate(data).model_dump()


def load_settings() -> Settings:
    ensure_app_home()
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(_new_config_payload(), indent=2), encoding="utf-8")
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    s = Settings.model_validate(data)
    for p in (s.watch_path, s.output_path, s.cache_path):
        p.mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "covers").mkdir(parents=True, exist_ok=True)
    (ROOT / "secrets").mkdir(parents=True, exist_ok=True)
    return s


def save_settings(data: dict[str, Any]) -> Settings:
    current = load_settings().model_dump()
    current.update(data)
    s = Settings.model_validate(current)
    for p in (s.watch_path, s.output_path, s.cache_path):
        p.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(s.model_dump(), indent=2), encoding="utf-8")
    return s
