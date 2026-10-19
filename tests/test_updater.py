from __future__ import annotations

from pathlib import Path

import pytest

from app.updater import _is_newer, validate_manifest, verify_installer
from app.updater_runner import backup_program, restore_program


def test_version_comparison():
    assert _is_newer("0.9.1", "0.9.0") is True
    assert _is_newer("1.0.0", "0.9.9") is True
    assert _is_newer("0.9.0", "0.9.0") is False


def _manifest(**overrides):
    row = {
        "version": "0.9.1",
        "installer_url": "https://example.com/PostalAutoClip.exe",
        "sha256": "a" * 64,
        "signer_subject": "CN=Postal AutoClip",
        "signer_thumbprint": "AB" * 20,
    }
    row.update(overrides)
    return row


def test_manifest_requires_https_hash_and_signer_identity_on_windows(monkeypatch):
    import app.updater as updater
    monkeypatch.setattr(updater, "_is_windows", lambda: True)
    assert validate_manifest(_manifest())["version"] == "0.9.1"
    with pytest.raises(RuntimeError): validate_manifest(_manifest(installer_url="http://example.com/file.exe"))
    with pytest.raises(RuntimeError): validate_manifest(_manifest(sha256="nope"))
    with pytest.raises(RuntimeError): validate_manifest(_manifest(signer_subject=""))
    with pytest.raises(RuntimeError): validate_manifest(_manifest(signer_thumbprint=""))


def test_remote_manifest_cannot_nominate_a_different_signer(monkeypatch):
    import app.updater as updater
    monkeypatch.setattr(updater, "_is_windows", lambda: True)
    monkeypatch.setattr(updater, "trusted_update_identity", lambda: {
        "status": "Valid", "subject": "CN=Postal AutoClip", "thumbprint": "11" * 20,
    })
    good = validate_manifest(_manifest(signer_thumbprint="11" * 20))
    assert updater._trusted_manifest_identity(good)["thumbprint"] == "11" * 20
    bad = validate_manifest(_manifest(signer_thumbprint="22" * 20))
    with pytest.raises(RuntimeError, match="thumbprint"):
        updater._trusted_manifest_identity(bad)


def test_hash_verification_fails_closed_before_signature(tmp_path: Path):
    path = tmp_path / "installer.exe"; path.write_bytes(b"not the expected installer")
    with pytest.raises(RuntimeError, match="SHA-256"):
        verify_installer(path, "0" * 64, "Postal AutoClip", "AB" * 20)


def test_program_backup_and_restore_do_not_touch_external_data(tmp_path: Path):
    program = tmp_path / "Programs" / "Postal AutoClip"; data = tmp_path / "AppData" / "PostalAutoClip"
    program.mkdir(parents=True); data.mkdir(parents=True)
    (program / "PostalAutoClip.exe").write_text("old-build", encoding="utf-8")
    (data / "creator.db").write_text("creator-history", encoding="utf-8")
    backup = backup_program(program, data / "updates" / "rollback", "0.9.0")
    (program / "PostalAutoClip.exe").write_text("broken-new-build", encoding="utf-8")
    restore_program(backup, program)
    assert (program / "PostalAutoClip.exe").read_text(encoding="utf-8") == "old-build"
    assert (data / "creator.db").read_text(encoding="utf-8") == "creator-history"
