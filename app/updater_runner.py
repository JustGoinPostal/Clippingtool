from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path


def _wait_for_pid_exit(pid: int, timeout: float = 90.0) -> None:
    if pid <= 0:
        return
    if os.name != "nt":
        deadline = time.time() + timeout
        while time.time() < deadline:
            try: os.kill(pid, 0)
            except OSError: return
            time.sleep(0.25)
        raise TimeoutError(f"Timed out waiting for PID {pid} to exit")
    import ctypes
    handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, int(pid))
    if not handle: return
    try:
        if ctypes.windll.kernel32.WaitForSingleObject(handle, int(timeout * 1000)) != 0:
            raise TimeoutError(f"Timed out waiting for PID {pid} to exit")
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _safe_version(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ".-_" else "_" for ch in str(value or "unknown"))[:80]


def backup_program(program_dir: Path, backup_root: Path, old_version: str) -> Path:
    program_dir = Path(program_dir).resolve(); backup_root = Path(backup_root).resolve(); backup_root.mkdir(parents=True, exist_ok=True)
    destination = backup_root / f"{_safe_version(old_version)}-{time.strftime('%Y%m%d-%H%M%S')}" / "program"
    if destination.exists(): shutil.rmtree(destination, ignore_errors=True)
    shutil.copytree(program_dir, destination); return destination


def restore_program(backup_program: Path, program_dir: Path) -> None:
    backup_program = Path(backup_program).resolve(); program_dir = Path(program_dir).resolve()
    if not backup_program.exists(): raise FileNotFoundError(backup_program)
    failed = program_dir.with_name(program_dir.name + ".failed-update")
    if failed.exists(): shutil.rmtree(failed, ignore_errors=True)
    if program_dir.exists():
        try: program_dir.replace(failed)
        except Exception: shutil.rmtree(program_dir, ignore_errors=True)
    shutil.copytree(backup_program, program_dir, dirs_exist_ok=True); shutil.rmtree(failed, ignore_errors=True)


def _run_installer(installer: Path) -> None:
    cp = subprocess.run([str(Path(installer).resolve()), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"], timeout=300)
    if cp.returncode != 0:
        raise RuntimeError(f"Installer did not complete successfully (Inno Setup exit code {cp.returncode})")


def _run_self_test(app_exe: Path) -> None:
    cp = subprocess.run([str(app_exe), "--self-test"], timeout=120, capture_output=True, text=True)
    if cp.returncode != 0:
        output = (cp.stdout or "") + "\n" + (cp.stderr or "")
        raise RuntimeError(f"New build self-test failed with exit code {cp.returncode}: {output[-3000:]}")


def _launch(path: Path) -> None:
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([str(path)], cwd=str(path.parent), close_fds=True, creationflags=flags)


def _prune_rollbacks(root: Path, keep: int = 3) -> None:
    root = Path(root); rows = sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True) if root.exists() else []
    for path in rows[max(1, keep):]: shutil.rmtree(path, ignore_errors=True)


def apply_update(installer: Path, program_dir: Path, app_exe_name: str, parent_pid: int,
                 old_version: str, new_version: str, expected_sha256: str,
                 signer_subject: str, signer_thumbprint: str, relaunch: bool = True) -> int:
    from .paths import APP_HOME
    from .updater import verify_installer

    installer = Path(installer).resolve(); program_dir = Path(program_dir).resolve(); app_exe = program_dir / app_exe_name
    updates = APP_HOME / "updates"; rollback_root = updates / "rollback"; log_path = updates / "updater-last.json"; updates.mkdir(parents=True, exist_ok=True)
    status = {"started_at": time.time(), "old_version": old_version, "new_version": new_version, "program_dir": str(program_dir), "installer": str(installer), "status": "starting", "trusted_signer_subject": signer_subject, "trusted_signer_thumbprint": signer_thumbprint}
    try:
        verify_installer(installer, expected_sha256, signer_subject, signer_thumbprint)
        status["status"] = "verified"; _wait_for_pid_exit(parent_pid)
        backup = backup_program(program_dir, rollback_root, old_version); status["backup"] = str(backup); status["status"] = "installing"
        _run_installer(installer)
        if not app_exe.exists(): raise RuntimeError("Installer completed but PostalAutoClip.exe is missing")
        status["status"] = "health_check"; _run_self_test(app_exe)
        status["status"] = "updated"; status["completed_at"] = time.time(); log_path.write_text(json.dumps(status, indent=2), encoding="utf-8")
        _prune_rollbacks(rollback_root, keep=3)
        if relaunch: _launch(app_exe)
        return 0
    except Exception as exc:
        status["error"] = f"{type(exc).__name__}: {exc}"; status["status"] = "rolling_back"
        try:
            backup_path = Path(str(status.get("backup") or ""))
            if backup_path.exists():
                restore_program(backup_path, program_dir); old_exe = program_dir / app_exe_name; _run_self_test(old_exe); status["status"] = "rolled_back"
                if relaunch: _launch(old_exe)
            else: status["status"] = "rollback_unavailable"
        except Exception as rollback_exc:
            status["rollback_error"] = f"{type(rollback_exc).__name__}: {rollback_exc}"; status["status"] = "rollback_failed"
        status["completed_at"] = time.time()
        try: log_path.write_text(json.dumps(status, indent=2), encoding="utf-8")
        except Exception: pass
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Postal AutoClip update/rollback runner")
    parser.add_argument("--apply", required=True, type=Path); parser.add_argument("--program-dir", required=True, type=Path)
    parser.add_argument("--app-exe", default="PostalAutoClip.exe"); parser.add_argument("--parent-pid", type=int, default=0)
    parser.add_argument("--old-version", default="unknown"); parser.add_argument("--new-version", required=True)
    parser.add_argument("--sha256", required=True); parser.add_argument("--signer-subject", required=True); parser.add_argument("--signer-thumbprint", required=True)
    parser.add_argument("--no-relaunch", action="store_true", help="Do not launch AutoClip after success/rollback (CI lifecycle validation only)")
    args = parser.parse_args(argv)
    return apply_update(args.apply, args.program_dir, args.app_exe, args.parent_pid, args.old_version, args.new_version, args.sha256, args.signer_subject, args.signer_thumbprint, relaunch=not args.no_relaunch)


if __name__ == "__main__":
    raise SystemExit(main())
