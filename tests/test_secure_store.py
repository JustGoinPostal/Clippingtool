from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.secure_store import read_secure_json, secure_storage_status, write_secure_json


def test_secure_store_roundtrip(tmp_path: Path):
    path = tmp_path / "token.json"
    payload = {"access_token": "super-secret-token", "refresh_token": "refresh-secret"}
    write_secure_json(path, payload)
    assert read_secure_json(path) == payload
    status = secure_storage_status()
    assert "method" in status


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI behavior")
def test_windows_dpapi_file_does_not_contain_plaintext(tmp_path: Path):
    path = tmp_path / "token.json"
    write_secure_json(path, {"access_token": "secret-that-must-not-be-plaintext"})
    raw = path.read_text(encoding="utf-8")
    assert "secret-that-must-not-be-plaintext" not in raw
    envelope = json.loads(raw)
    assert envelope["__postal_secure__"] == "postal-dpapi-v1"
    assert envelope["scope"] == "current_windows_user"
    assert read_secure_json(path)["access_token"] == "secret-that-must-not-be-plaintext"


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI migration")
def test_windows_plaintext_credential_is_migrated_on_read(tmp_path: Path):
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({"client_secret": "old-plaintext-secret"}), encoding="utf-8")
    assert read_secure_json(path)["client_secret"] == "old-plaintext-secret"
    raw = path.read_text(encoding="utf-8")
    assert "old-plaintext-secret" not in raw
    assert json.loads(raw)["__postal_secure__"] == "postal-dpapi-v1"
