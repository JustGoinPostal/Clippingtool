from __future__ import annotations

import base64
import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path
from typing import Any

_FORMAT = "postal-dpapi-v1"
_DESCRIPTION = "Postal AutoClip local credential"
_ENTROPY = b"PostalAutoClip/DPAPI/v1"
_CRYPTPROTECT_UI_FORBIDDEN = 0x1


class SecureStoreError(RuntimeError):
    pass


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _input_blob(data: bytes) -> tuple[_DATA_BLOB, Any]:
    if not data:
        data = b"\x00"
    buf = ctypes.create_string_buffer(data, len(data))
    blob = _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    return blob, buf


def _dpapi_protect(data: bytes) -> bytes:
    if os.name != "nt":
        raise SecureStoreError("Windows DPAPI is only available on Windows")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB), wintypes.LPCWSTR, ctypes.POINTER(_DATA_BLOB),
        wintypes.LPVOID, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(_DATA_BLOB),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL

    src, src_buf = _input_blob(data)
    entropy, entropy_buf = _input_blob(_ENTROPY)
    out = _DATA_BLOB()
    ok = crypt32.CryptProtectData(
        ctypes.byref(src), _DESCRIPTION, ctypes.byref(entropy), None, None,
        _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out),
    )
    _ = (src_buf, entropy_buf)
    if not ok:
        raise SecureStoreError(f"CryptProtectData failed: {ctypes.WinError(ctypes.get_last_error())}")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        if out.pbData:
            kernel32.LocalFree(ctypes.cast(out.pbData, wintypes.HLOCAL))


def _dpapi_unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        raise SecureStoreError("This credential is protected by Windows DPAPI and can only be opened by the Windows user that saved it")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB), ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(_DATA_BLOB),
        wintypes.LPVOID, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(_DATA_BLOB),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL

    src, src_buf = _input_blob(data)
    entropy, entropy_buf = _input_blob(_ENTROPY)
    out = _DATA_BLOB()
    description = wintypes.LPWSTR()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(src), ctypes.byref(description), ctypes.byref(entropy), None, None,
        _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out),
    )
    _ = (src_buf, entropy_buf)
    if not ok:
        raise SecureStoreError(
            "Windows could not decrypt this Postal AutoClip credential. It may belong to a different Windows user/machine or be corrupted."
        )
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        if description:
            kernel32.LocalFree(ctypes.cast(description, wintypes.HLOCAL))
        if out.pbData:
            kernel32.LocalFree(ctypes.cast(out.pbData, wintypes.HLOCAL))


def _atomic_write(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except Exception:
        pass
    tmp.replace(path)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def write_secure_json(path: Path, data: dict[str, Any]) -> None:
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if os.name == "nt":
        protected = _dpapi_protect(payload)
        envelope = {
            "__postal_secure__": _FORMAT,
            "scope": "current_windows_user",
            "blob": base64.b64encode(protected).decode("ascii"),
        }
        _atomic_write(Path(path), json.dumps(envelope, indent=2))
    else:
        # Non-Windows is supported for development/CI only. Restrict permissions,
        # but do not falsely claim DPAPI protection where Windows is unavailable.
        _atomic_write(Path(path), json.dumps(data, indent=2))


def read_secure_json(path: Path, *, migrate_legacy: bool = True) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SecureStoreError(f"Credential file is not valid JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise SecureStoreError(f"Credential file must contain a JSON object: {path}")

    if raw.get("__postal_secure__") == _FORMAT:
        blob_text = str(raw.get("blob") or "")
        if not blob_text:
            raise SecureStoreError(f"Encrypted credential is missing its protected payload: {path}")
        try:
            plaintext = _dpapi_unprotect(base64.b64decode(blob_text, validate=True))
            decoded = json.loads(plaintext.decode("utf-8"))
        except SecureStoreError:
            raise
        except Exception as exc:
            raise SecureStoreError(f"Encrypted credential could not be decoded: {path}") from exc
        if not isinstance(decoded, dict):
            raise SecureStoreError(f"Decrypted credential must contain a JSON object: {path}")
        return decoded

    # Backward-compatible migration from the old plaintext credential files.
    if os.name == "nt" and migrate_legacy:
        write_secure_json(path, raw)
    return raw


def secure_storage_status() -> dict[str, Any]:
    return {
        "platform": os.name,
        "method": "windows-dpapi-current-user" if os.name == "nt" else "restricted-file-development-fallback",
        "encrypted_at_rest": os.name == "nt",
        "portable": False if os.name == "nt" else True,
    }


def dpapi_roundtrip_self_test() -> bool:
    if os.name != "nt":
        return True
    sample = b"postal-autoclip-dpapi-self-test"
    return _dpapi_unprotect(_dpapi_protect(sample)) == sample
