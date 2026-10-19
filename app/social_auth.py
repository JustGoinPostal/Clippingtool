from __future__ import annotations

import hashlib
import secrets
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from .config import ROOT, load_settings
from .secure_store import SecureStoreError, read_secure_json, secure_storage_status, write_secure_json

SECRETS = ROOT / "secrets"
CACHE = ROOT / "data" / "cache"
TIKTOK_APP = SECRETS / "tiktok_app.json"
TIKTOK_TOKEN = SECRETS / "tiktok_token.json"
INSTAGRAM_APP = SECRETS / "instagram_app.json"
INSTAGRAM_TOKEN = SECRETS / "instagram_token.json"
# OAuth state contains PKCE/state material too, so keep it in the protected
# credential directory instead of the general media/model cache.
TIKTOK_OAUTH = SECRETS / "tiktok_oauth_pending.json"
INSTAGRAM_OAUTH = SECRETS / "instagram_oauth_pending.json"

TIKTOK_DEFAULT_REDIRECT = "http://127.0.0.1:8790/tiktok/callback"
INSTAGRAM_DEFAULT_REDIRECT = "http://127.0.0.1:8790/instagram/callback"
TIKTOK_SCOPES = ["user.info.basic", "video.list", "video.publish"]
INSTAGRAM_SCOPES = [
    "pages_show_list",
    "pages_read_engagement",
    "instagram_basic",
    "instagram_content_publish",
    "instagram_manage_insights",
]

_maintenance_started = False
_maintenance_lock = threading.Lock()


def _read(path: Path) -> dict[str, Any]:
    try:
        return read_secure_json(path)
    except SecureStoreError:
        return {}


def _write(path: Path, data: dict[str, Any]) -> None:
    write_secure_json(path, data)


def credential_storage_status() -> dict[str, Any]:
    return secure_storage_status()


def app_config_status() -> dict[str, Any]:
    tt = _read(TIKTOK_APP)
    ig = _read(INSTAGRAM_APP)
    tt_token = _read(TIKTOK_TOKEN)
    ig_token = _read(INSTAGRAM_TOKEN)
    return {
        "credential_storage": credential_storage_status(),
        "tiktok": {
            "configured": bool(tt.get("client_key") and tt.get("client_secret")),
            "client_key": str(tt.get("client_key") or ""),
            "redirect_uri": str(tt.get("redirect_uri") or TIKTOK_DEFAULT_REDIRECT),
            "connected": bool(tt_token.get("access_token")),
            "open_id": str(tt_token.get("open_id") or ""),
            "scope": str(tt_token.get("scope") or ""),
            "expires_at": float(tt_token.get("expires_at") or 0),
            "refresh_expires_at": float(tt_token.get("refresh_expires_at") or 0),
        },
        "instagram": {
            "configured": bool(ig.get("client_id") and ig.get("client_secret")),
            "client_id": str(ig.get("client_id") or ""),
            "redirect_uri": str(ig.get("redirect_uri") or INSTAGRAM_DEFAULT_REDIRECT),
            "connected": bool(ig_token.get("access_token") and (ig_token.get("ig_user_id") or ig_token.get("instagram_user_id"))),
            "ig_user_id": str(ig_token.get("ig_user_id") or ig_token.get("instagram_user_id") or ""),
            "username": str(ig_token.get("username") or ""),
            "page_name": str(ig_token.get("page_name") or ""),
            "account_choices": instagram_account_choices(),
        },
    }


def save_app_config(payload: dict[str, Any]) -> dict[str, Any]:
    SECRETS.mkdir(parents=True, exist_ok=True)
    if isinstance(payload.get("tiktok"), dict):
        old = _read(TIKTOK_APP)
        incoming = payload["tiktok"]
        client_key = str(incoming.get("client_key") or old.get("client_key") or "").strip()
        client_secret = str(incoming.get("client_secret") or old.get("client_secret") or "").strip()
        redirect_uri = str(incoming.get("redirect_uri") or old.get("redirect_uri") or TIKTOK_DEFAULT_REDIRECT).strip()
        _write(TIKTOK_APP, {"client_key": client_key, "client_secret": client_secret, "redirect_uri": redirect_uri})
    if isinstance(payload.get("instagram"), dict):
        old = _read(INSTAGRAM_APP)
        incoming = payload["instagram"]
        client_id = str(incoming.get("client_id") or old.get("client_id") or "").strip()
        client_secret = str(incoming.get("client_secret") or old.get("client_secret") or "").strip()
        redirect_uri = str(incoming.get("redirect_uri") or old.get("redirect_uri") or INSTAGRAM_DEFAULT_REDIRECT).strip()
        _write(INSTAGRAM_APP, {"client_id": client_id, "client_secret": client_secret, "redirect_uri": redirect_uri})
    return app_config_status()


def _pkce_verifier() -> str:
    return secrets.token_urlsafe(64)


def tiktok_authorization_url() -> str:
    cfg = _read(TIKTOK_APP)
    key = str(cfg.get("client_key") or "").strip()
    if not key or not str(cfg.get("client_secret") or "").strip():
        raise RuntimeError("TikTok developer app is not configured. Add Client Key and Client Secret in Accounts first.")
    redirect = str(cfg.get("redirect_uri") or TIKTOK_DEFAULT_REDIRECT)
    state = secrets.token_urlsafe(32)
    verifier = _pkce_verifier()
    challenge = hashlib.sha256(verifier.encode("utf-8")).hexdigest()
    _write(TIKTOK_OAUTH, {"state": state, "code_verifier": verifier, "redirect_uri": redirect, "created_at": time.time()})
    params = {
        "client_key": key,
        "scope": ",".join(TIKTOK_SCOPES),
        "response_type": "code",
        "redirect_uri": redirect,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return "https://www.tiktok.com/v2/auth/authorize/?" + urlencode(params)


def finish_tiktok_oauth(code: str, state: str) -> dict[str, Any]:
    pending = _read(TIKTOK_OAUTH)
    if not pending or not secrets.compare_digest(str(pending.get("state") or ""), str(state or "")):
        raise RuntimeError("TikTok OAuth state did not match. Start Connect TikTok again.")
    if time.time() - float(pending.get("created_at") or 0) > 600:
        raise RuntimeError("TikTok OAuth attempt expired. Start Connect TikTok again.")
    cfg = _read(TIKTOK_APP)
    form = {
        "client_key": str(cfg.get("client_key") or ""),
        "client_secret": str(cfg.get("client_secret") or ""),
        "code": str(code),
        "grant_type": "authorization_code",
        "redirect_uri": str(pending.get("redirect_uri") or TIKTOK_DEFAULT_REDIRECT),
        "code_verifier": str(pending.get("code_verifier") or ""),
    }
    with httpx.Client(timeout=30) as client:
        r = client.post("https://open.tiktokapis.com/v2/oauth/token/", data=form,
                        headers={"Content-Type": "application/x-www-form-urlencoded"})
        r.raise_for_status()
        data = r.json()
    if data.get("error"):
        raise RuntimeError(f"TikTok token exchange failed: {data.get('error_description') or data.get('error')}")
    now = time.time()
    data["expires_at"] = now + float(data.get("expires_in") or 0)
    data["refresh_expires_at"] = now + float(data.get("refresh_expires_in") or 0)
    data["connected_at"] = now
    _write(TIKTOK_TOKEN, data)
    TIKTOK_OAUTH.unlink(missing_ok=True)
    return {"ok": True, "open_id": data.get("open_id", ""), "scope": data.get("scope", "")}


def refresh_tiktok_token(force: bool = False) -> dict[str, Any]:
    token = _read(TIKTOK_TOKEN)
    if not token.get("refresh_token"):
        return token
    now = time.time()
    if not force and float(token.get("expires_at") or 0) > now + 1800:
        return token
    cfg = _read(TIKTOK_APP)
    if not cfg.get("client_key") or not cfg.get("client_secret"):
        return token
    form = {
        "client_key": str(cfg["client_key"]),
        "client_secret": str(cfg["client_secret"]),
        "grant_type": "refresh_token",
        "refresh_token": str(token["refresh_token"]),
    }
    with httpx.Client(timeout=30) as client:
        r = client.post("https://open.tiktokapis.com/v2/oauth/token/", data=form,
                        headers={"Content-Type": "application/x-www-form-urlencoded"})
        r.raise_for_status()
        data = r.json()
    if data.get("error"):
        raise RuntimeError(f"TikTok refresh failed: {data.get('error_description') or data.get('error')}")
    data.setdefault("open_id", token.get("open_id", ""))
    data.setdefault("scope", token.get("scope", ""))
    data["expires_at"] = now + float(data.get("expires_in") or 0)
    data["refresh_expires_at"] = now + float(data.get("refresh_expires_in") or 0)
    data["connected_at"] = float(token.get("connected_at") or now)
    _write(TIKTOK_TOKEN, data)
    return data


def instagram_authorization_url() -> str:
    cfg = _read(INSTAGRAM_APP)
    client_id = str(cfg.get("client_id") or "").strip()
    if not client_id or not str(cfg.get("client_secret") or "").strip():
        raise RuntimeError("Meta/Instagram developer app is not configured. Add App ID and App Secret in Accounts first.")
    redirect = str(cfg.get("redirect_uri") or INSTAGRAM_DEFAULT_REDIRECT)
    state = secrets.token_urlsafe(32)
    _write(INSTAGRAM_OAUTH, {"state": state, "redirect_uri": redirect, "created_at": time.time()})
    version = str(load_settings().instagram_graph_version or "v26.0").strip("/")
    params = {
        "client_id": client_id,
        "redirect_uri": redirect,
        "state": state,
        "response_type": "code",
        "scope": ",".join(INSTAGRAM_SCOPES),
    }
    return f"https://www.facebook.com/{version}/dialog/oauth?" + urlencode(params)


def _instagram_pages(user_token: str) -> list[dict[str, Any]]:
    version = str(load_settings().instagram_graph_version or "v26.0").strip("/")
    url = f"https://graph.facebook.com/{version}/me/accounts"
    with httpx.Client(timeout=30) as client:
        r = client.get(url, params={
            "fields": "id,name,access_token,tasks,instagram_business_account{id,username}",
            "access_token": user_token,
            "limit": 100,
        })
        r.raise_for_status()
        rows = (r.json() or {}).get("data") or []
    return [x for x in rows if isinstance(x, dict) and isinstance(x.get("instagram_business_account"), dict)]


def finish_instagram_oauth(code: str, state: str) -> dict[str, Any]:
    pending = _read(INSTAGRAM_OAUTH)
    if not pending or not secrets.compare_digest(str(pending.get("state") or ""), str(state or "")):
        raise RuntimeError("Instagram OAuth state did not match. Start Connect Instagram again.")
    if time.time() - float(pending.get("created_at") or 0) > 900:
        raise RuntimeError("Instagram OAuth attempt expired. Start Connect Instagram again.")
    cfg = _read(INSTAGRAM_APP)
    version = str(load_settings().instagram_graph_version or "v26.0").strip("/")
    redirect = str(pending.get("redirect_uri") or INSTAGRAM_DEFAULT_REDIRECT)
    with httpx.Client(timeout=30) as client:
        short = client.get(f"https://graph.facebook.com/{version}/oauth/access_token", params={
            "client_id": str(cfg.get("client_id") or ""),
            "client_secret": str(cfg.get("client_secret") or ""),
            "redirect_uri": redirect,
            "code": str(code),
        })
        short.raise_for_status()
        short_data = short.json() or {}
        user_token = str(short_data.get("access_token") or "")
        if not user_token:
            raise RuntimeError(f"Meta did not return an access token: {short_data}")
        long_r = client.get(f"https://graph.facebook.com/{version}/oauth/access_token", params={
            "grant_type": "fb_exchange_token",
            "client_id": str(cfg.get("client_id") or ""),
            "client_secret": str(cfg.get("client_secret") or ""),
            "fb_exchange_token": user_token,
        })
        if long_r.is_success and (long_r.json() or {}).get("access_token"):
            long_data = long_r.json() or {}
            user_token = str(long_data.get("access_token") or user_token)
            expires_in = float(long_data.get("expires_in") or 0)
        else:
            expires_in = float(short_data.get("expires_in") or 0)
    pages = _instagram_pages(user_token)
    if not pages:
        raise RuntimeError("No linked Professional Instagram account was found. Link a Creator/Business Instagram account to a Facebook Page, then reconnect.")
    choices = []
    for page in pages:
        ig = page.get("instagram_business_account") or {}
        choices.append({
            "page_id": str(page.get("id") or ""),
            "page_name": str(page.get("name") or ""),
            "page_access_token": str(page.get("access_token") or ""),
            "ig_user_id": str(ig.get("id") or ""),
            "username": str(ig.get("username") or ""),
        })
    first = choices[0]
    stored = {
        "access_token": first["page_access_token"],
        "ig_user_id": first["ig_user_id"],
        "instagram_user_id": first["ig_user_id"],
        "username": first["username"],
        "page_id": first["page_id"],
        "page_name": first["page_name"],
        "user_access_token": user_token,
        "user_token_expires_at": time.time() + expires_in if expires_in else 0,
        "available_accounts": choices,
        "login_type": "facebook_business",
        "connected_at": time.time(),
    }
    _write(INSTAGRAM_TOKEN, stored)
    INSTAGRAM_OAUTH.unlink(missing_ok=True)
    return {"ok": True, "username": first["username"], "page_name": first["page_name"], "choices": len(choices)}


def instagram_account_choices() -> list[dict[str, str]]:
    data = _read(INSTAGRAM_TOKEN)
    out = []
    for row in data.get("available_accounts") or []:
        if not isinstance(row, dict):
            continue
        out.append({
            "ig_user_id": str(row.get("ig_user_id") or ""),
            "username": str(row.get("username") or ""),
            "page_id": str(row.get("page_id") or ""),
            "page_name": str(row.get("page_name") or ""),
        })
    return out


def select_instagram_account(ig_user_id: str) -> dict[str, Any]:
    data = _read(INSTAGRAM_TOKEN)
    choices = data.get("available_accounts") or []
    selected = next((x for x in choices if isinstance(x, dict) and str(x.get("ig_user_id") or "") == str(ig_user_id)), None)
    if not selected:
        raise RuntimeError("Instagram account choice was not found. Reconnect Instagram.")
    data.update({
        "access_token": str(selected.get("page_access_token") or ""),
        "ig_user_id": str(selected.get("ig_user_id") or ""),
        "instagram_user_id": str(selected.get("ig_user_id") or ""),
        "username": str(selected.get("username") or ""),
        "page_id": str(selected.get("page_id") or ""),
        "page_name": str(selected.get("page_name") or ""),
    })
    _write(INSTAGRAM_TOKEN, data)
    return {"ok": True, "ig_user_id": data["ig_user_id"], "username": data.get("username", ""), "page_name": data.get("page_name", "")}


def disconnect_platform(platform: str) -> None:
    target = TIKTOK_TOKEN if platform == "tiktok" else INSTAGRAM_TOKEN if platform == "instagram" else None
    if target is None:
        raise RuntimeError("Unknown platform")
    target.unlink(missing_ok=True)


def start_token_maintenance() -> None:
    global _maintenance_started
    with _maintenance_lock:
        if _maintenance_started:
            return
        _maintenance_started = True

    def loop() -> None:
        while True:
            try:
                refresh_tiktok_token()
            except Exception:
                pass
            time.sleep(600)

    threading.Thread(target=loop, daemon=True, name="postal-token-maintenance").start()
