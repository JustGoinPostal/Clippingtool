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
    layout: str = "blur_fit"
    render_width: int = 1080
    render_height: int = 1920
    caption_font: str = "Arial"
    caption_font_size: int = 72
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
    for p in (s.watch_path, s.output_path, s.cache_path): p.mkdir(parents=True, exist_ok=True)
    return s


def save_settings(data: dict[str, Any]) -> Settings:
    current = load_settings().model_dump()
    current.update(data)
    s = Settings.model_validate(current)
    CONFIG_PATH.write_text(json.dumps(s.model_dump(), indent=2), encoding="utf-8")
    return s
