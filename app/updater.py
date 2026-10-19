from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from packaging.version import InvalidVersion, Version

from .config import load_settings
from .paths import APP_HOME, PROGRAM_ROOT

UPDATE_DIR = APP_HOME / "updates"
DOWNLOAD_DIR = UPDATE_DIR / "downloads"
RUNNER_DIR = UPDATE_DIR / "runner"
STATE_PATH = UPDATE_DIR / "state.json"
DEFAULT_MANIFEST_URL = "https://github.com/JustGoinPostal/Clippingtool/releases/latest/download/postal-autoclip-update.json"


def current_version() -> str:
    info = PROGRAM_ROOT / "BUILD_INFO.txt"
    if info.exists():
        try:
            for line in info.read_text(encoding="utf-8-sig").splitlines():
                if line.lower().startswith("version:"):
                    value = line.split(":", 1)[1].strip()
                    if value:
                        return value
        except Exception:
            pass
    try:
        from importlib.metadata import version
        return version("postal-autoclip")
    except Exception:
        return "0.0.0-dev"


def _is_newer(candidate: str, installed: str) -> bool:
    try:
        return Version(candidate) > Version(installed)
    except InvalidVersion:
        return candidate.strip() != installed.strip()


def _write_state(payload: dict[str, Any]) -> None:
    UPDATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        value = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def validate_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("Update manifest is not a JSON object")
    version = str(payload.get("version") or "").strip()
    installer_url = str(payload.get("installer_url") or "").strip()
    sha256 = str(payload.get("sha256") or "").strip().lower()
    signer = str(payload.get("signer_subject") or "").strip()
    if not version:
        raise RuntimeError("Update manifest is missing version")
    parsed = urlparse(installer_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise RuntimeError("Update installer URL must use HTTPS")
    if len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256):
        raise RuntimeError("Update manifest has an invalid SHA-256")
    if os.name == "nt" and not signer:
        raise RuntimeError("Windows update manifest is missing the expected Authenticode signer")
    return {
        "schema_version": int(payload.get("schema_version", 1) or 1),
        "version": version,
        "channel": str(payload.get("channel") or "beta"),
        "installer_url": installer_url,
        "sha256": sha256,
        "signer_subject": signer,
        "release_notes_url": str(payload.get("release_notes_url") or ""),
    }


def check_for_update(*, force: bool = False, manifest_url: str | None = None) -> dict[str, Any]:
    settings = load_settings()
    url = str(manifest_url or getattr(settings, "update_manifest_url", "") or DEFAULT_MANIFEST_URL).strip()
    now = time.time()
    state = _load_state()
    interval = max(1.0, float(getattr(settings, "update_check_hours", 6.0))) * 3600.0
    if not force and state.get("checked_at") and now - float(state["checked_at"]) < interval:
        return dict(state)
    result: dict[str, Any] = {"checked_at": now, "current_version": current_version(), "manifest_url": url, "available": False}
    try:
        with httpx.Client(timeout=20, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": "PostalAutoClip-Updater"})
            if response.status_code == 404:
                result["message"] = "No published update channel is available yet."
                _write_state(result)
                return result
            response.raise_for_status()
            manifest = validate_manifest(response.json())
        result["manifest"] = manifest
        result["available"] = _is_newer(manifest["version"], result["current_version"])
        result["message"] = f"Update {manifest['version']} is available." if result["available"] else "Postal AutoClip is up to date."
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    _write_state(result)
    return result


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def authenticode_info(path: Path) -> dict[str, str]:
    if os.name != "nt":
        return {"status": "NotWindows", "subject": ""}
    script = (
        "$s=Get-AuthenticodeSignature -LiteralPath $args[0];"
        "$o=[pscustomobject]@{status=$s.Status.ToString();subject=if($s.SignerCertificate){$s.SignerCertificate.Subject}else{''}};"
        "$o|ConvertTo-Json -Compress"
    )
    cp = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script, str(Path(path).resolve())], capture_output=True, text=True, timeout=30)
    if cp.returncode != 0:
        raise RuntimeError(f"Could not verify Authenticode signature: {cp.stderr.strip()}")
    try:
        value = json.loads(cp.stdout.strip().splitlines()[-1])
    except Exception as exc:
        raise RuntimeError(f"Could not parse Authenticode result: {cp.stdout!r}") from exc
    return {"status": str(value.get("status") or ""), "subject": str(value.get("subject") or "")}


def verify_installer(path: Path, expected_sha256: str, expected_subject: str) -> dict[str, Any]:
    path = Path(path)
    actual = _sha256(path)
    if actual.lower() != str(expected_sha256).lower():
        raise RuntimeError("Downloaded update failed SHA-256 verification")
    signature = authenticode_info(path)
    if os.name == "nt":
        if signature["status"].lower() != "valid":
            raise RuntimeError(f"Downloaded update has an invalid Authenticode signature: {signature['status']}")
        if expected_subject and expected_subject.lower() not in signature["subject"].lower():
            raise RuntimeError(f"Downloaded update signer did not match expected publisher: {signature['subject']!r}")
    return {"sha256": actual, "signature": signature}


def download_update(manifest: dict[str, Any]) -> Path:
    manifest = validate_manifest(manifest)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    final = DOWNLOAD_DIR / f"PostalAutoClip-{manifest['version']}-Setup.exe"
    if final.exists():
        try:
            verify_installer(final, manifest["sha256"], manifest["signer_subject"])
            return final
        except Exception:
            final.unlink(missing_ok=True)
    partial = final.with_suffix(".partial.exe")
    partial.unlink(missing_ok=True)
    with httpx.Client(timeout=httpx.Timeout(30, read=300, write=30, connect=20), follow_redirects=True) as client:
        with client.stream("GET", manifest["installer_url"], headers={"User-Agent": "PostalAutoClip-Updater"}) as response:
            response.raise_for_status()
            with partial.open("wb") as out:
                for chunk in response.iter_bytes(1024 * 1024):
                    if chunk:
                        out.write(chunk)
    partial.replace(final)
    verify_installer(final, manifest["sha256"], manifest["signer_subject"])
    return final


def launch_update(installer: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    if os.name != "nt":
        raise RuntimeError("Automatic install/rollback is currently supported on Windows only")
    manifest = validate_manifest(manifest)
    verify_installer(installer, manifest["sha256"], manifest["signer_subject"])
    updater = PROGRAM_ROOT / "PostalAutoClipUpdater.exe"
    if not updater.exists():
        raise RuntimeError("PostalAutoClipUpdater.exe is missing from this installation")
    RUNNER_DIR.mkdir(parents=True, exist_ok=True)
    runner = RUNNER_DIR / f"PostalAutoClipUpdater-{uuid.uuid4().hex}.exe"
    shutil.copy2(updater, runner)
    args = [
        str(runner), "--apply", str(Path(installer).resolve()),
        "--program-dir", str(PROGRAM_ROOT),
        "--app-exe", "PostalAutoClip.exe",
        "--parent-pid", str(os.getpid()),
        "--old-version", current_version(),
        "--new-version", manifest["version"],
        "--sha256", manifest["sha256"],
        "--signer-subject", manifest["signer_subject"],
    ]
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(args, cwd=str(APP_HOME), close_fds=True, creationflags=creationflags)
    _write_state({"checked_at": time.time(), "current_version": current_version(), "updating_to": manifest["version"], "installer": str(installer)})
    return {"started": True, "version": manifest["version"], "runner": str(runner)}


def automatic_update_check_and_prompt() -> None:
    settings = load_settings()
    if os.name != "nt" or not getattr(sys, "frozen", False) or not bool(getattr(settings, "auto_update_enabled", True)):
        return
    result = check_for_update(force=False)
    if not result.get("available") or not isinstance(result.get("manifest"), dict):
        return
    manifest = result["manifest"]
    try:
        answer = ctypes_message_box_yes_no(
            "Postal AutoClip Update",
            f"Postal AutoClip {manifest['version']} is available.\n\nDownload, verify, install, and automatically roll back if the new build fails its health check?",
        )
        if not answer:
            return
        installer = download_update(manifest)
        launch_update(installer, manifest)
        time.sleep(0.4)
        os._exit(0)
    except Exception as exc:
        _write_state({"checked_at": time.time(), "current_version": current_version(), "available": True, "manifest": manifest, "error": f"{type(exc).__name__}: {exc}"})


def ctypes_message_box_yes_no(title: str, message: str) -> bool:
    if os.name != "nt":
        return False
    import ctypes
    MB_YESNO = 0x00000004
    MB_ICONINFORMATION = 0x00000040
    IDYES = 6
    return ctypes.windll.user32.MessageBoxW(None, message, title, MB_YESNO | MB_ICONINFORMATION) == IDYES
