from __future__ import annotations

from pathlib import Path

import pytest

from app.updater import _is_newer, validate_manifest, verify_installer
from app.updater_runner import backup_program, restore_program


def test_version_comparison():
    assert _is_newer("0.9.1", "0.9.0") is True
    assert _is_newer("1.0.0", "0.9.9") is True
    assert _is_newer("0.9.0", "0.9.0") is False


def test_manifest_requires_https_hash_and_signer_on_windows(monkeypatch):
    import app.updater as updater
    monkeypatch.setattr(updater.os, "name", "nt", raising=False)
    base = {
        "version": "0.9.1",
        "installer_url": "https://example.com/PostalAutoClip.exe",
        "sha256": "a" * 64,
        "signer_subject": "CN=Postal AutoClip",
    }
    assert validate_manifest(base)["version"] == "0.9.1"
    bad = dict(base, installer_url="http://example.com/file.exe")
    with pytest.raises(RuntimeError):
        validate_manifest(bad)
    bad = dict(base, sha256="nope")
    with pytest.raises(RuntimeError):
        validate_manifest(bad)
    bad = dict(base, signer_subject="")
    with pytest.raises(RuntimeError):
        validate_manifest(bad)


def test_hash_verification_fails_closed_before_signature(tmp_path: Path):
    path = tmp_path / "installer.exe"
    path.write_bytes(b"not the expected installer")
    with pytest.raises(RuntimeError, match="SHA-256"):
        verify_installer(path, "0" * 64, "Postal AutoClip")


def test_program_backup_and_restore_do_not_touch_external_data(tmp_path: Path):
    program = tmp_path / "Programs" / "Postal AutoClip"
    data = tmp_path / "AppData" / "PostalAutoClip"
    program.mkdir(parents=True)
    data.mkdir(parents=True)
    (program / "PostalAutoClip.exe").write_text("old-build", encoding="utf-8")
    (data / "creator.db").write_text("creator-history", encoding="utf-8")

    backup = backup_program(program, data / "updates" / "rollback", "0.9.0")
    (program / "PostalAutoClip.exe").write_text("broken-new-build", encoding="utf-8")
    restore_program(backup, program)

    assert (program / "PostalAutoClip.exe").read_text(encoding="utf-8") == "old-build"
    assert (data / "creator.db").read_text(encoding="utf-8") == "creator-history"
