from __future__ import annotations

import json
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.json"


@dataclass
class SeenFile:
    size: int
    mtime: float
    first_stable_at: float


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise SystemExit(
            f"Missing {CONFIG_PATH}. Copy config.example.json to config.json and edit it first."
        )
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def state_path(cfg: dict) -> Path:
    p = Path(str(cfg.get("state_file") or "streaming_agent_state.json"))
    return p if p.is_absolute() else HERE / p


def load_state(cfg: dict) -> dict:
    p = state_path(cfg)
    if not p.exists():
        return {"copied": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError
        data.setdefault("copied", {})
        return data
    except Exception:
        return {"copied": {}}


def save_state(cfg: dict, state: dict) -> None:
    p = state_path(cfg)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(p)


def iter_recordings(cfg: dict) -> Iterable[Path]:
    allowed = {str(x).lower() for x in cfg.get("extensions", [])}
    for folder in cfg.get("recording_folders", []):
        root = Path(os.path.expandvars(os.path.expanduser(str(folder))))
        if not root.exists():
            continue
        for p in root.iterdir():
            if p.is_file() and p.suffix.lower() in allowed:
                yield p


def fingerprint(p: Path) -> str:
    st = p.stat()
    return f"{p.resolve()}|{st.st_size}|{int(st.st_mtime)}"


def target_name(p: Path) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(p.stat().st_mtime))
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in p.name)
    return f"{stamp}_{safe}"


def copy_atomic(src: Path, share: Path, retries: int, retry_seconds: int) -> Path:
    share.mkdir(parents=True, exist_ok=True)
    final = share / target_name(src)
    partial = final.with_suffix(final.suffix + ".partial")

    if final.exists() and final.stat().st_size == src.stat().st_size:
        return final

    for attempt in range(1, retries + 1):
        try:
            if partial.exists():
                partial.unlink()
            print(f"[copy] {src} -> {final} (attempt {attempt}/{retries})", flush=True)
            shutil.copy2(src, partial)
            if partial.stat().st_size != src.stat().st_size:
                raise IOError("copied size does not match source")
            partial.replace(final)
            return final
        except Exception as exc:
            print(f"[copy-error] {type(exc).__name__}: {exc}", flush=True)
            if attempt >= retries:
                raise
            time.sleep(retry_seconds)
    raise RuntimeError("copy retries exhausted")


def write_sidecar(src: Path, dst: Path) -> None:
    st = src.stat()
    payload = {
        "source_name": src.name,
        "source_path": str(src),
        "source_size": st.st_size,
        "source_mtime": st.st_mtime,
        "received_at": time.time(),
        "streaming_pc": os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "unknown",
    }
    sidecar = dst.with_suffix(dst.suffix + ".json")
    sidecar.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    cfg = load_config()
    share = Path(str(cfg["server_share"]))
    poll_seconds = max(5, int(cfg.get("poll_seconds", 20)))
    stable_seconds = max(30, int(cfg.get("stable_seconds", 120)))
    retries = max(1, int(cfg.get("copy_retries", 10)))
    retry_seconds = max(5, int(cfg.get("retry_seconds", 30)))
    state = load_state(cfg)
    observed: Dict[str, SeenFile] = {}

    print("Postal streaming handoff agent started.")
    print(f"Server share: {share}")
    print(f"Stability window: {stable_seconds}s")

    while True:
        now = time.time()
        current_paths = set()

        for p in iter_recordings(cfg):
            try:
                st = p.stat()
            except FileNotFoundError:
                continue

            key = str(p.resolve())
            current_paths.add(key)
            fp = fingerprint(p)
            if fp in state["copied"]:
                continue

            prior = observed.get(key)
            if prior is None or prior.size != st.st_size or prior.mtime != st.st_mtime:
                observed[key] = SeenFile(st.st_size, st.st_mtime, now)
                continue

            if now - prior.first_stable_at < stable_seconds:
                continue

            try:
                dst = copy_atomic(p, share, retries, retry_seconds)
                write_sidecar(p, dst)
                state["copied"][fp] = {
                    "copied_at": time.time(),
                    "destination": str(dst),
                }
                save_state(cfg, state)
                print(f"[done] {p.name} handed off to server", flush=True)
                observed.pop(key, None)
            except Exception as exc:
                print(f"[failed] {p}: {type(exc).__name__}: {exc}", flush=True)
                observed[key] = SeenFile(st.st_size, st.st_mtime, time.time())

        for key in list(observed):
            if key not in current_paths:
                observed.pop(key, None)

        time.sleep(poll_seconds)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nPostal streaming handoff agent stopped.")
        raise SystemExit(0)
