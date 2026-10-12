from __future__ import annotations

import subprocess
from pathlib import Path
import numpy as np

from .media import require_ffmpeg
from .config import Settings


def _mean_abs(a: np.ndarray, b: np.ndarray) -> float:
    if a is None or b is None:
        return 0.0
    return float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean()) / 255.0


def _color_ratios(frame: np.ndarray) -> tuple[float,float,float]:
    r = frame[:, :, 0].astype(np.int16)
    g = frame[:, :, 1].astype(np.int16)
    b = frame[:, :, 2].astype(np.int16)
    purple = (r > 80) & (b > 90) & (r > g + 22) & (b > g + 24)
    gold = (r > 150) & (g > 105) & (g < r - 18) & (b < 100)
    red = (r > 145) & (r > g + 45) & (r > b + 40)
    return float(purple.mean()), float(gold.mean()), float(red.mean())


def _purple_ratio(frame: np.ndarray) -> float:
    r = frame[:, :, 0].astype(np.int16)
    g = frame[:, :, 1].astype(np.int16)
    b = frame[:, :, 2].astype(np.int16)
    mask = (r > 80) & (b > 90) & (r > g + 22) & (b > g + 24)
    return float(mask.mean())


def analyze_video(path: Path, duration: float, s: Settings) -> list[dict]:
    if not s.video_analysis_enabled or duration <= 0:
        return []
    require_ffmpeg()
    width, height = 320, 180
    fps = max(0.1, 1.0 / max(0.5, float(s.video_sample_seconds)))
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
        "-an", "-vf", f"fps={fps},scale={width}:{height}",
        "-pix_fmt", "rgb24", "-f", "rawvideo", "-"
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    frame_bytes = width * height * 3
    rows: list[dict] = []
    prev = None
    index = 0
    assert proc.stdout is not None
    while True:
        raw = proc.stdout.read(frame_bytes)
        if len(raw) != frame_bytes:
            break
        frame = np.frombuffer(raw, dtype=np.uint8).reshape((height, width, 3)).copy()
        t = min(duration, index / fps)
        whole = _mean_abs(frame, prev)
        chat = frame[int(height * 0.60):height, 0:int(width * 0.62)]
        prev_chat = None if prev is None else prev[int(height * 0.60):height, 0:int(width * 0.62)]
        inv = frame[int(height * 0.18):int(height * 0.94), int(width * 0.74):width]
        prev_inv = None if prev is None else prev[int(height * 0.18):int(height * 0.94), int(width * 0.74):width]
        center = frame[int(height * 0.22):int(height * 0.78), int(width * 0.18):int(width * 0.78)]
        prev_center = None if prev is None else prev[int(height * 0.22):int(height * 0.78), int(width * 0.18):int(width * 0.78)]
        purple,gold,red = _color_ratios(frame)
        rows.append({
            "time": round(float(t), 3),
            "visual_change": round(whole, 6),
            "chat_change": round(_mean_abs(chat, prev_chat), 6),
            "ui_change": round(_mean_abs(inv, prev_inv), 6),
            "center_change": round(_mean_abs(center, prev_center), 6),
            "purple_ratio": round(purple, 6),
            "gold_ratio": round(gold, 6),
            "red_ratio": round(red, 6),
        })
        prev = frame
        index += 1
    proc.stdout.close()
    proc.wait(timeout=30)
    return rows
