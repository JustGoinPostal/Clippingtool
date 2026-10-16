from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
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
    smart_boundaries: bool = True
    diversity_per_type: int = 6
    default_clip_seconds: int = 50
    pre_roll_seconds: int = 12
    post_roll_seconds: int = 28

    # v0.4 editing / rendering
    layout: str = "osrs_focus"
    render_width: int = 1080
    render_height: int = 1920
    render_variants: dict[str, int] = Field(default_factory=lambda: {
        "short": 22, "medium": 38, "long": 58
    })
    primary_variant: str = "medium"
    dead_air_trim_enabled: bool = True
    dead_air_padding_seconds: float = 0.55
    dead_air_min_clip_seconds: float = 6.0
    osrs_focus_panel_height: int = 700
    osrs_focus_margin: int = 50

    # Keep a visible facecam in vertical edits without using it for clip scoring.
    webcam_overlay_enabled: bool = True
    webcam_region: str = "auto"  # auto, top_left, top_right, bottom_left, bottom_right
    webcam_crop_width_ratio: float = 0.30
    webcam_overlay_width: int = 390
    webcam_overlay_y: int = 500

    caption_font: str = "Arial"
    caption_font_size: int = 76
    caption_words_per_group: int = 4
    caption_margin_v: int = 205
    caption_emphasis_scale: int = 118
    caption_uppercase: bool = True

    # v0.5 automatic edit polish
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

    # v0.6 publishing queue
    publishing_enabled: bool = True
    publish_poll_seconds: int = 20
    youtube_default_privacy: str = "private"
    tiktok_default_privacy: str = "SELF_ONLY"

    # v0.7 distribution / covers / Instagram
    auto_cover_enabled: bool = True
    youtube_set_thumbnail: bool = True
    instagram_graph_version: str = "v26.0"
    instagram_default_privacy: str = "public"
    instagram_share_to_feed: bool = True
    duplicate_window_days: int = 30
    duplicate_similarity_threshold: float = 0.62
    distribution_slots: list[str] = Field(default_factory=lambda: ["12:00", "18:30"])
    platform_offsets_minutes: dict[str, int] = Field(default_factory=lambda: {
        "youtube": 0, "tiktok": 20, "instagram": 40
    })

    # v0.8 audience analytics / self-improvement
    analytics_enabled: bool = True
    analytics_refresh_hours: float = 6.0
    analytics_history_days: int = 90
    analytics_collection_min_age_hours: float = 6.0
    analytics_learning_enabled: bool = True
    analytics_learning_weight: float = 0.35
    analytics_learning_min_age_hours: float = 24.0
    analytics_learning_min_views: int = 100

    # v0.9 platform-specific learning without splitting the content calendar
    synchronized_crosspost_enabled: bool = True
    platform_fit_enabled: bool = True
    platform_variant_min_samples: int = 3

    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = ""
    runelite_bridge_enabled: bool = True
    runelite_bridge_token: str = "postal-local"
    runelite_event_window_seconds: float = 8.0
    big_hit_threshold: int = 35
    keywords: dict[str, float] = Field(default_factory=dict)

    def path(self, value: str) -> Path:
        p = Path(value)
        return p if p.is_absolute() else ROOT / p

    @property
    def watch_path(self) -> Path: return self.path(self.watch_folder)
    @property
    def output_path(self) -> Path: return self.path(self.output_folder)
    @property
    def cache_path(self) -> Path: return self.path(self.cache_folder)

def load_settings() -> Settings:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
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
    CONFIG_PATH.write_text(json.dumps(s.model_dump(), indent=2), encoding="utf-8")
    return s
