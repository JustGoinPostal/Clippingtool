from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any


def _resource_root() -> Path:
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        return Path(frozen).resolve()
    return Path(__file__).resolve().parents[1]


RESOURCE_ROOT = _resource_root()
PROGRAM_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else RESOURCE_ROOT


def _default_app_home() -> Path:
    override = os.getenv("POSTAL_AUTOCLIP_HOME", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if "pytest" in sys.modules:
        return (RESOURCE_ROOT / ".pytest-home").resolve()
    if os.name == "nt":
        local = os.getenv("LOCALAPPDATA", "").strip()
        if local:
            return (Path(local) / "PostalAutoClip").resolve()
        return (Path.home() / "AppData" / "Local" / "PostalAutoClip").resolve()
    xdg = os.getenv("XDG_DATA_HOME", "").strip()
    if xdg:
        return (Path(xdg) / "PostalAutoClip").resolve()
    return (Path.home() / ".local" / "share" / "PostalAutoClip").resolve()


APP_HOME = _default_app_home()
DATA_DIR = APP_HOME / "data"
SECRETS_DIR = APP_HOME / "secrets"
LOG_DIR = APP_HOME / "logs"
PRIVATE_BENCHMARK_DIR = APP_HOME / "benchmarks" / "private"
MIGRATION_REPORT = APP_HOME / "migration.json"


def _copy_if_missing(source: Path, destination: Path) -> bool:
    if not source.exists() or destination.exists():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)
    return True


def _legacy_config_payload(source_root: Path) -> dict[str, Any] | None:
    path = source_root / "config.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    for key in ("watch_folder", "output_folder"):
        raw = str(payload.get(key) or "").strip()
        if not raw:
            continue
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = (source_root / p).resolve()
            payload[key] = str(p)
    payload["cache_folder"] = "data/cache"
    return payload


def _protect_secret_json_files() -> list[str]:
    """Immediately DPAPI-wrap migrated/legacy secret JSON on Windows.

    This closes the migration window where an old plaintext credential could
    otherwise sit in the new AppData secrets directory until that platform was
    next opened. Non-Windows development leaves the restricted-file fallback.
    """
    if os.name != "nt" or not SECRETS_DIR.exists():
        return []
    protected: list[str] = []
    try:
        from .secure_store import read_secure_json
    except Exception:
        return protected
    for path in SECRETS_DIR.glob("*.json"):
        try:
            raw = path.read_text(encoding="utf-8")
            if '"__postal_secure__"' in raw:
                continue
            value = read_secure_json(path, migrate_legacy=True)
            if isinstance(value, dict):
                protected.append(path.name)
        except Exception:
            # A malformed credential should be surfaced by the account flow; do
            # not destroy it during startup migration.
            continue
    return protected


def migrate_legacy_install(source_root: Path = RESOURCE_ROOT) -> dict[str, Any]:
    """Copy small creator state from the old repo-folder layout into AppData.

    Large recordings/renders are never copied. Relative legacy media paths are
    converted to absolute paths so existing jobs continue to resolve. Existing
    AppData files always win; migration is non-destructive. On Windows, migrated
    credential JSON is DPAPI-protected before normal startup continues.
    """
    report: dict[str, Any] = {"source": str(source_root), "migrated": []}
    try:
        if source_root.resolve() == APP_HOME.resolve():
            _protect_secret_json_files()
            return report
    except Exception:
        pass

    config_target = APP_HOME / "config.json"
    if not config_target.exists():
        payload = _legacy_config_payload(source_root)
        if payload is not None:
            config_target.parent.mkdir(parents=True, exist_ok=True)
            config_target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            report["migrated"].append("config.json")

    old_db = source_root / "data" / "postal_autoclip.db"
    if _copy_if_missing(old_db, DATA_DIR / "postal_autoclip.db"):
        report["migrated"].append("database")

    old_secrets = source_root / "secrets"
    if old_secrets.exists():
        SECRETS_DIR.mkdir(parents=True, exist_ok=True)
        for src in old_secrets.iterdir():
            if src.is_file() and _copy_if_missing(src, SECRETS_DIR / src.name):
                report["migrated"].append(f"secret:{src.name}")

    protected = _protect_secret_json_files()
    report["migrated"].extend(f"dpapi:{name}" for name in protected)

    for relative in (
        Path("data/public_reference_catalog.json"),
        Path("data/benchmark_labels"),
        Path("data/covers"),
    ):
        src = source_root / relative
        dst = APP_HOME / relative
        if _copy_if_missing(src, dst):
            report["migrated"].append(str(relative).replace("\\", "/"))

    if report["migrated"]:
        MIGRATION_REPORT.parent.mkdir(parents=True, exist_ok=True)
        MIGRATION_REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _inject_runtime_dashboard_scripts(static_dst: Path) -> None:
    """Attach small runtime-only dashboard extensions after static mirroring."""
    index = static_dst / "index.html"
    if not index.exists():
        return
    tag = '<script src="/static/render_guard.js"></script>'
    try:
        html = index.read_text(encoding="utf-8")
        if tag not in html and "</body>" in html:
            index.write_text(html.replace("</body>", tag + "</body>"), encoding="utf-8")
    except Exception:
        # Static mirroring must never prevent AutoClip from launching.
        pass


def _sync_runtime_resources() -> None:
    static_src = RESOURCE_ROOT / "app" / "static"
    static_dst = APP_HOME / "app" / "static"
    if static_src.exists() and static_src.resolve() != static_dst.resolve():
        shutil.copytree(static_src, static_dst, dirs_exist_ok=True)
        _inject_runtime_dashboard_scripts(static_dst)

    for relative in (
        Path("config.example.json"),
        Path("benchmarks/corpus.example.json"),
        Path("references/osrs_public_metadata_seeds.json"),
    ):
        src = RESOURCE_ROOT / relative
        dst = APP_HOME / relative
        if src.exists() and src.resolve() != dst.resolve():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def configure_process_environment() -> None:
    cache = DATA_DIR / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(cache / "huggingface"))
    tools = RESOURCE_ROOT / "tools"
    if tools.exists():
        current = os.environ.get("PATH", "")
        prefix = str(tools)
        if prefix.lower() not in current.lower():
            os.environ["PATH"] = prefix + os.pathsep + current


def ensure_app_home() -> Path:
    for path in (
        APP_HOME,
        DATA_DIR,
        DATA_DIR / "input",
        DATA_DIR / "output",
        DATA_DIR / "cache",
        DATA_DIR / "covers",
        DATA_DIR / "benchmark_labels",
        SECRETS_DIR,
        LOG_DIR,
        PRIVATE_BENCHMARK_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
    migrate_legacy_install()
    _protect_secret_json_files()
    _sync_runtime_resources()
    configure_process_environment()
    return APP_HOME


ensure_app_home()
