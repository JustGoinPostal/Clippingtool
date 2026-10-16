from __future__ import annotations

import json
import platform
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

from .config import ROOT, load_settings
from . import db

LOG_DIR = ROOT / "data" / "logs"
_lock = threading.Lock()
_SENSITIVE_KEYS = ("token", "secret", "password", "credential", "api_key", "apikey")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def job_log_path(job_id: int) -> Path:
    return LOG_DIR / f"analysis_job_{int(job_id)}.log"


def _append(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        with path.open("a", encoding="utf-8", errors="replace") as f:
            f.write(text)
            if not text.endswith("\n"):
                f.write("\n")


def start_job_log(job_id: int, source_path: str) -> None:
    _append(
        job_log_path(job_id),
        "\n" + "=" * 88 + "\n"
        f"ANALYSIS ATTEMPT START  {_utc_now()}\n"
        f"job_id={job_id}\n"
        f"source={source_path}\n"
        + "=" * 88,
    )


def append_job_log(job_id: int, message: str, level: str = "INFO") -> None:
    clean = str(message).replace("\r", "").rstrip("\n")
    _append(job_log_path(job_id), f"[{_utc_now()}] [{level}] {clean}")


def append_job_exception(job_id: int, traceback_text: str) -> None:
    _append(
        job_log_path(job_id),
        f"[{_utc_now()}] [ERROR] Full traceback follows:\n{traceback_text.rstrip()}\n",
    )


def _redact(value: Any, key: str = "") -> Any:
    low = key.lower()
    if any(part in low for part in _SENSITIVE_KEYS):
        return "<redacted>"
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    if isinstance(value, tuple):
        return [_redact(v) for v in value]
    return value


def _command_summary(cmd: list[str], timeout: int = 8) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout)
        text = (p.stdout or p.stderr or "").strip()
        return text if text else f"exit_code={p.returncode}"
    except Exception as e:
        return f"unavailable: {type(e).__name__}: {e}"


def _package_versions() -> dict[str, str]:
    names = [
        "postal-autoclip",
        "faster-whisper",
        "ctranslate2",
        "av",
        "numpy",
        "fastapi",
        "uvicorn",
        "httpx",
        "google-api-python-client",
        "google-auth-oauthlib",
    ]
    out: dict[str, str] = {}
    for name in names:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = "not installed"
        except Exception as e:
            out[name] = f"error: {e}"
    return out


def _cuda_summary() -> str:
    parts: list[str] = []
    try:
        import ctranslate2
        parts.append(f"ctranslate2_cuda_device_count={ctranslate2.get_cuda_device_count()}")
    except Exception as e:
        parts.append(f"ctranslate2_cuda_device_count=error: {type(e).__name__}: {e}")
    parts.append("nvidia-smi:\n" + _command_summary([
        "nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"
    ]))
    return "\n".join(parts)


def _source_summary(path_text: str) -> str:
    p = Path(path_text)
    try:
        st = p.stat()
        return f"exists=yes size_bytes={st.st_size} modified_epoch={st.st_mtime}"
    except Exception as e:
        return f"exists=no/unreadable ({type(e).__name__}: {e})"


def _source_stream_summary(path_text: str) -> str:
    p = Path(path_text)
    if not p.exists():
        return "source missing"
    try:
        raw = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_streams", "-of", "json", str(p)
        ], text=True, encoding="utf-8", errors="replace", timeout=12)
        data = json.loads(raw)
        rows=[]
        for stream in data.get("streams", []):
            row={
                "index": stream.get("index"),
                "codec_type": stream.get("codec_type"),
                "codec_name": stream.get("codec_name"),
            }
            if stream.get("codec_type")=="video":
                row.update({
                    "width": stream.get("width"),
                    "height": stream.get("height"),
                    "pix_fmt": stream.get("pix_fmt"),
                    "avg_frame_rate": stream.get("avg_frame_rate"),
                })
            elif stream.get("codec_type")=="audio":
                row.update({
                    "sample_rate": stream.get("sample_rate"),
                    "channels": stream.get("channels"),
                })
            rows.append(row)
        return json.dumps(rows, indent=2, sort_keys=True)
    except Exception as e:
        return f"unavailable: {type(e).__name__}: {e}"


def build_debug_report(job_id: int | None = None) -> str:
    settings = load_settings()
    if job_id is not None:
        rows = db.q("SELECT * FROM jobs WHERE id=?", (int(job_id),))
    else:
        rows = db.q("SELECT * FROM jobs ORDER BY id DESC LIMIT 20")

    lines: list[str] = [
        "POSTAL AUTOCLIP DEBUG REPORT",
        "=" * 88,
        f"generated_utc: {_utc_now()}",
        f"python: {sys.version.replace(chr(10), ' ')}",
        f"python_executable: {sys.executable}",
        f"platform: {platform.platform()}",
        f"machine: {platform.machine()}",
        f"working_directory: {Path.cwd()}",
        "",
        "PACKAGE VERSIONS",
        "-" * 88,
        json.dumps(_package_versions(), indent=2, sort_keys=True),
        "",
        "FFMPEG",
        "-" * 88,
        _command_summary(["ffmpeg", "-version"]),
        "",
        "GPU / CUDA DETECTION",
        "-" * 88,
        _cuda_summary(),
        "",
        "SANITIZED SETTINGS",
        "-" * 88,
        json.dumps(_redact(settings.model_dump()), indent=2, sort_keys=True, default=str),
        "",
        "NOTE: OAuth files, secrets/, environment variables, tokens, passwords, and secret-valued settings are not included.",
        "",
    ]

    if not rows:
        lines.extend(["JOBS", "-" * 88, "No matching analysis jobs found."])
        return "\n".join(lines) + "\n"

    for row in rows:
        jid = int(row["id"])
        source_path=str(row.get("source_path") or "")
        lines.extend([
            "",
            "#" * 88,
            f"JOB {jid}",
            "#" * 88,
            json.dumps(_redact(row), indent=2, sort_keys=True, default=str),
            f"source_file_check: {_source_summary(source_path)}",
            "",
            "SOURCE STREAMS (FFPROBE)",
            "-" * 88,
            _source_stream_summary(source_path),
            "",
            "ANALYSIS TIMELINE",
            "-" * 88,
        ])
        log_path = job_log_path(jid)
        if log_path.exists():
            try:
                lines.append(log_path.read_text(encoding="utf-8", errors="replace"))
            except Exception as e:
                lines.append(f"Could not read {log_path}: {type(e).__name__}: {e}")
        else:
            lines.append("No chronological log exists for this older job. The legacy traceback is included below if present.")

        legacy_error = settings.cache_path / f"job_{jid}_error.txt"
        if legacy_error.exists():
            lines.extend(["", "LEGACY ERROR TRACEBACK", "-" * 88])
            try:
                lines.append(legacy_error.read_text(encoding="utf-8", errors="replace"))
            except Exception as e:
                lines.append(f"Could not read {legacy_error}: {type(e).__name__}: {e}")

    return "\n".join(lines).rstrip() + "\n"


def debug_filename(job_id: int | None = None) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    suffix = f"-job-{int(job_id)}" if job_id is not None else "-all"
    return f"PostalAutoClip-Debug{suffix}-{stamp}.txt"
