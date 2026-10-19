from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .analytics import YOUTUBE_ANALYTICS_SCOPES, YOUTUBE_ANALYTICS_TOKEN
from .publishing import YOUTUBE_CLIENT, YOUTUBE_SCOPE, YOUTUBE_TOKEN
from .secure_store import SecureStoreError, read_secure_json, secure_storage_status, write_secure_json
from .social_auth import (
    app_config_status,
    disconnect_platform,
    finish_instagram_oauth,
    finish_tiktok_oauth,
    instagram_authorization_url,
    save_app_config,
    select_instagram_account,
    start_token_maintenance,
    tiktok_authorization_url,
)

HOST = "127.0.0.1"
PORT = 8790
TIKTOK_REDIRECT = f"http://{HOST}:{PORT}/tiktok/callback"
INSTAGRAM_REDIRECT = f"http://{HOST}:{PORT}/instagram/callback"
YOUTUBE_ALL_SCOPES = list(dict.fromkeys([*YOUTUBE_SCOPE, *YOUTUBE_ANALYTICS_SCOPES]))
_started = False
_lock = threading.Lock()
_youtube_lock = threading.Lock()
_youtube_connecting = False
_youtube_last_error = ""


def _youtube_status() -> dict:
    return {
        "client_secret_present": YOUTUBE_CLIENT.exists(),
        "publishing_connected": YOUTUBE_TOKEN.exists(),
        "analytics_connected": YOUTUBE_ANALYTICS_TOKEN.exists(),
        "connected": YOUTUBE_TOKEN.exists() and YOUTUBE_ANALYTICS_TOKEN.exists(),
        "connecting": _youtube_connecting,
        "last_error": _youtube_last_error,
        "credential_storage": secure_storage_status(),
    }


def _save_youtube_client(content: str) -> dict:
    try:
        payload = json.loads(content)
    except Exception as e:
        raise RuntimeError("That file is not valid Google OAuth JSON.") from e
    if payload.get("web") and not payload.get("installed"):
        raise RuntimeError("That is a Google Web OAuth file. Postal AutoClip needs an OAuth client created as Desktop app.")
    block = payload.get("installed") or {}
    if not block.get("client_id") or not block.get("client_secret"):
        raise RuntimeError("Google Desktop OAuth JSON is missing client_id/client_secret.")
    write_secure_json(YOUTUBE_CLIENT, payload)
    return {"ok": True, "path": str(YOUTUBE_CLIENT), "encrypted": secure_storage_status()["encrypted_at_rest"]}


def _connect_youtube_all() -> None:
    global _youtube_connecting, _youtube_last_error
    with _youtube_lock:
        if _youtube_connecting:
            return
        _youtube_connecting = True
    try:
        client = read_secure_json(YOUTUBE_CLIENT)
        if not client:
            raise RuntimeError("Choose your Google OAuth Desktop client JSON first.")
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_config(client, YOUTUBE_ALL_SCOPES)
        creds = flow.run_local_server(port=8765, prompt="consent", access_type="offline", open_browser=True)
        token = json.loads(creds.to_json())
        write_secure_json(YOUTUBE_TOKEN, token)
        write_secure_json(YOUTUBE_ANALYTICS_TOKEN, token)
        _youtube_last_error = ""
    except Exception as e:
        _youtube_last_error = f"{type(e).__name__}: {e}"
    finally:
        _youtube_connecting = False


def _disconnect_youtube() -> None:
    global _youtube_last_error
    for path in (YOUTUBE_TOKEN, YOUTUBE_ANALYTICS_TOKEN):
        path.unlink(missing_ok=True)
    _youtube_last_error = ""


PAGE = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Postal AutoClip Accounts</title>
<style>:root{font-family:Segoe UI,Arial,sans-serif;color:#f5f7fb;background:#090c12}*{box-sizing:border-box}body{margin:0}.wrap{max-width:1250px;margin:auto;padding:26px}.top{display:flex;justify-content:space-between;gap:12px;align-items:center}.brand{font-size:28px;font-weight:900}.muted{color:#99a4b5}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.card{background:#121720;border:1px solid #293241;border-radius:16px;padding:18px;margin-top:16px}.good{color:#86e6a8}.warn{color:#f1cd82}.bad{color:#f29ca5}.tiny{font-size:12px}label{display:block;font-size:12px;color:#aab4c2;margin-top:10px}input,select,button{width:100%;padding:10px;border-radius:9px;border:1px solid #384355;background:#0c1118;color:#fff}button{width:auto;cursor:pointer;font-weight:750}.primary{background:#eef2ff;color:#0b0e14}.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.code{font-family:Consolas,monospace;background:#090d13;border:1px solid #283241;border-radius:8px;padding:8px;word-break:break-all}.secure{border-color:#356d49}@media(max-width:980px){.grid{grid-template-columns:1fr}}</style></head>
<body><div class="wrap"><div class="top"><div><div class="brand">POSTAL AUTOCLIP · ACCOUNTS</div><div class="muted">Connect accounts after you have already opened and explored the product.</div></div><button onclick="refreshStatus()">Refresh</button></div>
<div class="card secure"><b>Local credential protection</b><div id="security" class="muted tiny" style="margin-top:7px">Checking…</div></div>
<div class="grid">
<div class="card"><h2>YouTube</h2><div id="ytStatus" class="warn">Loading…</div><label>Google Desktop OAuth client JSON<input id="ytClient" type="file" accept=".json,application/json"></label><div class="actions"><button onclick="saveYoutubeClient()">Save OAuth JSON</button><button class="primary" onclick="connectYoutube()">Connect YouTube</button><button onclick="disconnect('youtube')">Disconnect</button></div><div id="ytError" class="bad tiny"></div></div>
<div class="card"><h2>TikTok</h2><div id="ttStatus" class="warn">Loading…</div><label>Client Key<input id="ttKey"></label><label>Client Secret<input id="ttSecret" type="password" placeholder="Leave blank to keep saved secret"></label><label>Redirect URI</label><div class="code">''' + TIKTOK_REDIRECT + r'''</div><div class="actions"><button onclick="saveConfig()">Save App Keys</button><button class="primary" onclick="connect('tiktok')">Connect TikTok</button><button onclick="disconnect('tiktok')">Disconnect</button></div><div id="ttError" class="bad tiny"></div></div>
<div class="card"><h2>Instagram</h2><div id="igStatus" class="warn">Loading…</div><label>Meta App ID<input id="igId"></label><label>Meta App Secret<input id="igSecret" type="password" placeholder="Leave blank to keep saved secret"></label><label>Redirect URI</label><div class="code">''' + INSTAGRAM_REDIRECT + r'''</div><div id="igChoice" style="display:none"><label>Instagram account<select id="igSelect"></select></label><button style="margin-top:8px" onclick="selectIg()">Use Selected Account</button></div><div class="actions"><button onclick="saveConfig()">Save App Keys</button><button class="primary" onclick="connect('instagram')">Connect Instagram</button><button onclick="disconnect('instagram')">Disconnect</button></div><div id="igError" class="bad tiny"></div></div>
</div></div>
<script>
async function j(u,o){let r=await fetch(u,o);let t=await r.text();if(!r.ok){try{let x=JSON.parse(t);throw Error(x.error||t)}catch(e){throw Error(t)}}try{return JSON.parse(t)}catch{return t}}
function err(id,msg){document.querySelector(id).textContent=msg||''}
async function refreshStatus(){try{let s=await j('/status'),y=s.youtube||{},t=s.tiktok||{},i=s.instagram||{},sec=y.credential_storage||s.credential_storage||{};document.querySelector('#security').textContent=sec.encrypted_at_rest?'Windows DPAPI: secrets and OAuth tokens are encrypted to your current Windows user and machine.':'Development fallback active; production Windows installs use DPAPI.';document.querySelector('#ytStatus').textContent=y.connecting?'CONNECTING…':y.connected?'CONNECTED':y.client_secret_present?'APP READY · account not connected':'OAUTH JSON NEEDED';document.querySelector('#ytStatus').className=y.connected?'good':y.client_secret_present?'warn':'bad';err('#ytError',y.last_error||'');document.querySelector('#ttKey').value=t.client_key||'';document.querySelector('#ttStatus').textContent=t.connected?'CONNECTED':t.configured?'APP READY · account not connected':'CLIENT KEY + SECRET NEEDED';document.querySelector('#ttStatus').className=t.connected?'good':t.configured?'warn':'bad';document.querySelector('#igId').value=i.client_id||'';document.querySelector('#igStatus').textContent=i.connected?`CONNECTED · @${i.username||i.ig_user_id}`:i.configured?'APP READY · account not connected':'APP ID + SECRET NEEDED';document.querySelector('#igStatus').className=i.connected?'good':i.configured?'warn':'bad';let c=i.account_choices||[],box=document.querySelector('#igChoice'),sel=document.querySelector('#igSelect');if(c.length>1){box.style.display='block';sel.innerHTML=c.map(x=>`<option value="${x.ig_user_id}" ${x.ig_user_id===i.ig_user_id?'selected':''}>@${x.username||x.ig_user_id} · ${x.page_name||'Page'}</option>`).join('')}else box.style.display='none'}catch(e){console.error(e)}}
async function saveYoutubeClient(){try{err('#ytError','');let f=document.querySelector('#ytClient').files[0];if(!f)throw Error('Choose your Google Desktop OAuth JSON first.');await j('/youtube/client',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({content:await f.text()})});document.querySelector('#ytClient').value='';await refreshStatus();return true}catch(e){err('#ytError',e.message);return false}}
async function connectYoutube(){try{if(document.querySelector('#ytClient').files[0]&&!await saveYoutubeClient())return;let x=await j('/youtube/connect',{method:'POST'});alert(x.message||'Google authorization is opening.');setTimeout(refreshStatus,1200)}catch(e){err('#ytError',e.message)}}
async function saveConfig(){let body={tiktok:{client_key:document.querySelector('#ttKey').value,client_secret:document.querySelector('#ttSecret').value,redirect_uri:''' + json.dumps(TIKTOK_REDIRECT) + r'''},instagram:{client_id:document.querySelector('#igId').value,client_secret:document.querySelector('#igSecret').value,redirect_uri:''' + json.dumps(INSTAGRAM_REDIRECT) + r'''}};let x=await j('/config',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});document.querySelector('#ttSecret').value='';document.querySelector('#igSecret').value='';await refreshStatus();return x}
function authWindow(p){let w=window.open('about:blank','postal_'+p+'_oauth');if(!w)throw Error('Allow pop-ups for 127.0.0.1 and try again.');return w}
async function connect(p){let w=null,id=p==='tiktok'?'#ttError':'#igError';try{err(id,'');w=authWindow(p);await saveConfig();let x=await j('/'+p+'/auth');w.location.href=x.auth_url;w.focus()}catch(e){if(w)try{w.close()}catch{}err(id,e.message)}}
async function disconnect(p){if(!confirm('Disconnect '+p+' on this PC?'))return;await j('/disconnect',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({platform:p})});refreshStatus()}
async function selectIg(){try{await j('/instagram/select',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({ig_user_id:document.querySelector('#igSelect').value})});refreshStatus()}catch(e){err('#igError',e.message)}}
refreshStatus();setInterval(refreshStatus,3000);
</script></body></html>'''

SUCCESS = '''<!doctype html><html><body style="font-family:Segoe UI;background:#0b0e14;color:#fff;padding:35px"><h2>{title}</h2><p>{message}</p><p>You can close this tab and return to Postal AutoClip Accounts.</p><script>setTimeout(()=>window.close(),2500)</script></body></html>'''


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str = "text/html; charset=utf-8") -> None:
        self.send_response(status); self.send_header("Content-Type", content_type); self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def _json(self, obj, status: int = 200) -> None:
        self._send(status, json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8")

    def _body(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except Exception:
            return {}

    def do_GET(self) -> None:
        parsed = urlparse(self.path); q = parse_qs(parsed.query)
        try:
            if parsed.path == "/": return self._send(200, PAGE.encode("utf-8"))
            if parsed.path == "/status":
                status = app_config_status(); status["youtube"] = _youtube_status(); status["credential_storage"] = secure_storage_status(); return self._json(status)
            if parsed.path == "/tiktok/auth":
                save_app_config({"tiktok": {"redirect_uri": TIKTOK_REDIRECT}}); return self._json({"auth_url": tiktok_authorization_url()})
            if parsed.path == "/instagram/auth":
                save_app_config({"instagram": {"redirect_uri": INSTAGRAM_REDIRECT}}); return self._json({"auth_url": instagram_authorization_url()})
            if parsed.path == "/tiktok/callback":
                if q.get("error"): raise RuntimeError(q.get("error_description", q["error"])[0])
                result = finish_tiktok_oauth((q.get("code") or [""])[0], (q.get("state") or [""])[0]); return self._send(200, SUCCESS.format(title="TikTok connected", message=f"Scopes: {result.get('scope','')}").encode("utf-8"))
            if parsed.path == "/instagram/callback":
                if q.get("error"): raise RuntimeError(q.get("error_description", q["error"])[0])
                result = finish_instagram_oauth((q.get("code") or [""])[0], (q.get("state") or [""])[0]); return self._send(200, SUCCESS.format(title="Instagram connected", message=f"Connected @{result.get('username') or 'Instagram'}.").encode("utf-8"))
            return self._json({"error": "not found"}, 404)
        except Exception as e:
            return self._send(400, SUCCESS.format(title="Connection failed", message=str(e)).encode("utf-8"))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/youtube/client": return self._json(_save_youtube_client(str(self._body().get("content") or "")))
            if parsed.path == "/youtube/connect":
                if not YOUTUBE_CLIENT.exists(): return self._json({"error": "Choose and save your Google Desktop OAuth JSON first."}, 400)
                threading.Thread(target=_connect_youtube_all, daemon=True, name="youtube-account-oauth").start(); return self._json({"started": True, "message": "Google authorization is opening. Approve YouTube publishing and analytics access in your browser."})
            if parsed.path == "/config": return self._json(save_app_config(self._body()))
            if parsed.path == "/disconnect":
                platform = str(self._body().get("platform") or "")
                if platform == "youtube": _disconnect_youtube()
                else: disconnect_platform(platform)
                return self._json({"ok": True})
            if parsed.path == "/instagram/select": return self._json(select_instagram_account(str(self._body().get("ig_user_id") or "")))
            return self._json({"error": "not found"}, 404)
        except (SecureStoreError, Exception) as e:
            return self._json({"error": f"{type(e).__name__}: {e}"}, 400)


class Server(ThreadingHTTPServer):
    allow_reuse_address = True


def start_account_server() -> None:
    global _started
    with _lock:
        if _started: return
        _started = True
    start_token_maintenance()
    def run() -> None:
        try: Server((HOST, PORT), Handler).serve_forever(poll_interval=0.5)
        except OSError: pass
    threading.Thread(target=run, daemon=True, name="postal-account-manager").start()
