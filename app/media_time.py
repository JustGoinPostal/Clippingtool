from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _parse_iso(s: str) -> float | None:
    try:
        s=s.strip()
        if s.endswith("Z"): s=s[:-1]+"+00:00"
        dt=datetime.fromisoformat(s)
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def recording_start_epoch(path: Path, duration: float) -> tuple[float,str]:
    try:
        raw=subprocess.check_output([
            "ffprobe","-v","error","-print_format","json",
            "-show_entries","format_tags=creation_time:stream_tags=creation_time",
            str(path)
        ],text=True,stderr=subprocess.DEVNULL,timeout=20)
        data=json.loads(raw)
        candidates=[]
        ft=(data.get("format") or {}).get("tags") or {}
        if ft.get("creation_time"): candidates.append(ft["creation_time"])
        for stream in data.get("streams") or []:
            tags=stream.get("tags") or {}
            if tags.get("creation_time"): candidates.append(tags["creation_time"])
        for value in candidates:
            ts=_parse_iso(str(value))
            if ts and 946684800 < ts < 4102444800:
                return ts,"metadata"
    except Exception:
        pass
    stat=path.stat()
    return max(0.0,float(stat.st_mtime)-max(0.0,float(duration))),"mtime-duration"
