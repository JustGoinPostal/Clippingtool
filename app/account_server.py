from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .analytics import YOUTUBE_ANALYTICS_SCOPES, YOUTUBE_ANALYTICS_TOKEN
from .publishing import YOUTUBE_CLIENT, YOUTUBE_SCOPE, YOUTUBE_TOKEN
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
    }


def _save_youtube_client(content: str) -> dict:
    try:
        payload = json.loads(content)
    except Exception as e:
        raise RuntimeError("That file is not valid Google OAuth JSON.") from e
    if payload.get("web") and not payload.get("installed"):
        raise RuntimeError(
            "That is a Google Web application OAuth file. Postal AutoClip needs an OAuth client created as Desktop app."
        )
    block = payload.get("installed") or {}
    if not block.get("client_id") or not block.get("client_secret"):
        raise RuntimeError("Google Desktop OAuth JSON is missing client_id/client_secret.")
    YOUTUBE_CLIENT.parent.mkdir(parents=True, exist_ok=True)
    YOUTUBE_CLIENT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"ok": True, "path": str(YOUTUBE_CLIENT)}


def _connect_youtube_all() -> None:
    global _youtube_connecting, _youtube_last_error
    with _youtube_lock:
        if _youtube_connecting:
            return
        _youtube_connecting = True
    try:
        if not YOUTUBE_CLIENT.exists():
            raise RuntimeError("Choose your Google OAuth Desktop client JSON first.")
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(str(YOUTUBE_CLIENT), YOUTUBE_ALL_SCOPES)
        creds = flow.run_local_server(port=8765, prompt="consent", access_type="offline", open_browser=True)
        token = creds.to_json()
        YOUTUBE_TOKEN.write_text(token, encoding="utf-8")
        YOUTUBE_ANALYTICS_TOKEN.write_text(token, encoding="utf-8")
        _youtube_last_error = ""
    except Exception as e:
        _youtube_last_error = f"{type(e).__name__}: {e}"
    finally:
        _youtube_connecting = False


def _disconnect_youtube() -> None:
    global _youtube_last_error
    for path in (YOUTUBE_TOKEN, YOUTUBE_ANALYTICS_TOKEN):
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
    _youtube_last_error = ""


PAGE = r'''<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Postal AutoClip Accounts</title><style>
:root{font-family:Segoe UI,Arial,sans-serif;color:#f5f7fb;background:#090c12}*{box-sizing:border-box}body{margin:0}.wrap{max-width:1260px;margin:auto;padding:26px}.top{display:flex;justify-content:space-between;align-items:center;gap:10px}.brand{font-size:28px;font-weight:900}.muted{color:#99a4b5}.card{background:#121720;border:1px solid #293241;border-radius:16px;padding:18px;margin-top:16px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}label{display:block;font-size:12px;color:#aab4c2;margin-top:9px}input,select,button{width:100%;padding:10px;border-radius:9px;border:1px solid #384355;background:#0c1118;color:#fff}input[type=file]{font-size:12px}button{width:auto;cursor:pointer;font-weight:750}button:disabled{opacity:.45;cursor:not-allowed}.primary{background:#eef2ff;color:#0b0e14}.good{color:#86e6a8}.warn{color:#f1cd82}.bad{color:#f29ca5}.pill{display:inline-block;border:1px solid #435066;border-radius:999px;padding:4px 8px;font-size:12px}.secret{font-family:monospace}.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:13px}.code{font-family:Consolas,monospace;background:#090d13;border:1px solid #283241;border-radius:8px;padding:8px;word-break:break-all}.tiny{font-size:12px}.substatus,.setup{margin-top:8px;padding:9px;border-radius:8px;background:#0c1118;border:1px solid #273142}.setup b{color:#e9edf6}.setup div{margin-top:5px}.error{min-height:16px;margin-top:8px}.linkbtn{text-decoration:none;display:inline-block;padding:9px 11px;border-radius:9px;border:1px solid #384355;background:#0c1118;color:#fff;font-size:13px;font-weight:750}@media(max-width:980px){.grid{grid-template-columns:1fr}} </style></head>
<body><div class="wrap"><div class="top"><div><div class="brand">POSTAL AUTOCLIP · ACCOUNTS</div><div class="muted">Connect publishing + analytics accounts. Credentials stay on this PC.</div></div><button onclick="refreshStatus()">Refresh</button></div>
<div class="card"><b>Important first-time setup</b><div class="muted tiny" style="margin-top:7px">You are not doing anything wrong: YouTube, TikTok, and Instagram do not allow a desktop uploader to authenticate with only your normal username/password. Each platform requires a developer app once. The cards below now walk you through exactly what is missing. After that one-time setup, normal use is just Connect / Reconnect.</div></div>
<div class="grid">
<div class="card"><h2>YouTube</h2><div id="ytStatus" class="warn">Loading…</div><div class="substatus tiny"><div>Publishing: <b id="ytPub">—</b></div><div>Analytics: <b id="ytAnalytics">—</b></div></div><div class="setup tiny"><b>One-time Google setup</b><div>1. Create/select a Google Cloud project.</div><div>2. Enable YouTube Data API v3 and YouTube Analytics API.</div><div>3. Configure the OAuth consent screen; while testing, add your Google account as a test user if Google asks.</div><div>4. Create an OAuth Client ID with application type <b>Desktop app</b>.</div><div>5. Download its JSON and choose it below.</div></div><div class="actions"><a class="linkbtn" target="_blank" rel="noopener" href="https://console.cloud.google.com/apis/credentials">Open Google OAuth</a><a class="linkbtn" target="_blank" rel="noopener" href="https://console.cloud.google.com/apis/library/youtube.googleapis.com">Enable YouTube API</a><a class="linkbtn" target="_blank" rel="noopener" href="https://console.cloud.google.com/apis/library/youtubeanalytics.googleapis.com">Enable Analytics API</a></div><label>Google Desktop OAuth client JSON<input id="ytClient" type="file" accept=".json,application/json"></label><div class="tiny muted" style="margin-top:8px">AutoClip saves the client locally and one browser authorization grants upload + read-only analytics access.</div><div id="ytError" class="bad tiny error"></div><div class="actions"><button onclick="saveYoutubeClient()">Save OAuth JSON</button><button class="primary" onclick="connectYoutube()">Connect YouTube</button><button onclick="disconnect('youtube')">Disconnect</button></div></div>
<div class="card"><h2>TikTok</h2><div id="ttStatus" class="warn">Loading…</div><div class="setup tiny"><b>One-time TikTok setup</b><div>1. Create an app in TikTok for Developers.</div><div>2. Add Login Kit and Content Posting.</div><div>3. Request/enable <b>user.info.basic</b>, <b>video.list</b>, and <b>video.publish</b> for the app.</div><div>4. Register the exact Desktop redirect URI shown below.</div><div>5. Copy the Client Key and Client Secret into AutoClip.</div></div><div class="actions"><a class="linkbtn" target="_blank" rel="noopener" href="https://developers.tiktok.com/apps/">Open TikTok Developers</a></div><label>Client Key<input id="ttKey"></label><label>Client Secret<input id="ttSecret" class="secret" type="password" placeholder="Leave blank to keep saved secret"></label><label>Desktop redirect URI</label><div class="code">''' + TIKTOK_REDIRECT + r'''</div><div class="tiny muted" style="margin-top:8px">TikTok Desktop Login uses PKCE. AutoClip stores the resulting token locally and refreshes it when supported.</div><div id="ttError" class="bad tiny error"></div><div class="actions"><button onclick="saveConfig()">Save App Keys</button><button class="primary" onclick="connect('tiktok')">Connect TikTok</button><button onclick="disconnect('tiktok')">Disconnect</button></div></div>
<div class="card"><h2>Instagram</h2><div id="igStatus" class="warn">Loading…</div><div class="setup tiny"><b>One-time Meta setup</b><div>1. Create a Meta developer app.</div><div>2. Configure Facebook Login for Business / Instagram permissions.</div><div>3. Your Instagram must be a Professional Creator/Business account linked to a Facebook Page for this local upload flow.</div><div>4. Register the exact redirect URI shown below.</div><div>5. Copy the Meta App ID and App Secret into AutoClip.</div></div><div class="actions"><a class="linkbtn" target="_blank" rel="noopener" href="https://developers.facebook.com/apps/">Open Meta Developers</a></div><label>Meta App ID<input id="igId"></label><label>Meta App Secret<input id="igSecret" class="secret" type="password" placeholder="Leave blank to keep saved secret"></label><label>Facebook Login redirect URI</label><div class="code">''' + INSTAGRAM_REDIRECT + r'''</div><div class="tiny muted" style="margin-top:8px">Requested permissions: pages_show_list, pages_read_engagement, instagram_basic, instagram_content_publish, instagram_manage_insights.</div><div id="igError" class="bad tiny error"></div><div id="igChoice" style="display:none"><label>Instagram account<select id="igSelect"></select></label><button style="margin-top:8px" onclick="selectIg()">Use Selected Account</button></div><div class="actions"><button onclick="saveConfig()">Save App Keys</button><button class="primary" onclick="connect('instagram')">Connect Instagram</button><button onclick="disconnect('instagram')">Disconnect</button></div></div>
</div>
<div class="card"><b>Security</b><div class="muted tiny" style="margin-top:7px">Developer app secrets and OAuth tokens are saved only under <span class="pill">secrets/</span>. That folder is Git-ignored. AutoClip's local services bind to 127.0.0.1 only. Do not send anyone your Client Secret, App Secret, OAuth JSON, or token files.</div></div>
</div><script>
async function j(u,o){let r=await fetch(u,o);let t=await r.text();if(!r.ok){try{let x=JSON.parse(t);throw Error(x.error||t)}catch(e){if(e.message!==t)throw e;throw Error(t)}}try{return JSON.parse(t)}catch{return t}}
function setErr(id,msg){let x=document.querySelector(id);if(x)x.textContent=msg||''}
async function refreshStatus(){try{let s=await j('/status');let y=s.youtube||{},t=s.tiktok||{},i=s.instagram||{};document.querySelector('#ytStatus').className=y.connected?'good':y.client_secret_present?'warn':'bad';document.querySelector('#ytStatus').textContent=y.connecting?'CONNECTING…':y.connected?'CONNECTED':y.client_secret_present?'APP READY · account not connected':'GOOGLE OAUTH JSON NEEDED';document.querySelector('#ytPub').textContent=y.publishing_connected?'CONNECTED':'NOT CONNECTED';document.querySelector('#ytAnalytics').textContent=y.analytics_connected?'CONNECTED':'NOT CONNECTED';setErr('#ytError',y.last_error||'');document.querySelector('#ttKey').value=t.client_key||'';document.querySelector('#igId').value=i.client_id||'';document.querySelector('#ttStatus').className=t.connected?'good':t.configured?'warn':'bad';document.querySelector('#ttStatus').textContent=t.connected?`CONNECTED · scopes: ${t.scope||'unknown'}`:t.configured?'APP READY · account not connected':'CLIENT KEY + SECRET NEEDED';document.querySelector('#igStatus').className=i.connected?'good':i.configured?'warn':'bad';document.querySelector('#igStatus').textContent=i.connected?`CONNECTED · @${i.username||i.ig_user_id}${i.page_name?' · '+i.page_name:''}`:i.configured?'APP READY · account not connected':'APP ID + SECRET NEEDED';let choices=i.account_choices||[],box=document.querySelector('#igChoice'),sel=document.querySelector('#igSelect');if(choices.length>1){box.style.display='block';sel.innerHTML=choices.map(x=>`<option value="${x.ig_user_id}" ${x.ig_user_id===i.ig_user_id?'selected':''}>@${x.username||x.ig_user_id} · ${x.page_name||'Page'}</option>`).join('')}else box.style.display='none'}catch(e){console.error(e)}}
async function saveYoutubeClient(){try{setErr('#ytError','');let f=document.querySelector('#ytClient').files[0];if(!f)throw Error('Choose the Google Desktop OAuth JSON you downloaded first.');await j('/youtube/client',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({content:await f.text()})});document.querySelector('#ytClient').value='';await refreshStatus();return true}catch(e){setErr('#ytError',e.message);return false}}
async function connectYoutube(){try{setErr('#ytError','');if(document.querySelector('#ytClient').files[0]){let ok=await saveYoutubeClient();if(!ok)return}let x=await j('/youtube/connect',{method:'POST'});alert(x.message||'Google authorization is opening. Finish it in your browser.');setTimeout(refreshStatus,1500)}catch(e){setErr('#ytError',e.message)}}
async function saveConfig(){let body={tiktok:{client_key:document.querySelector('#ttKey').value,client_secret:document.querySelector('#ttSecret').value,redirect_uri:''' + json.dumps(TIKTOK_REDIRECT) + r'''},instagram:{client_id:document.querySelector('#igId').value,client_secret:document.querySelector('#igSecret').value,redirect_uri:''' + json.dumps(INSTAGRAM_REDIRECT) + r'''}};let x=await j('/config',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});document.querySelector('#ttSecret').value='';document.querySelector('#igSecret').value='';await refreshStatus();return x}
function authWindow(platform){let w=window.open('about:blank','postal_'+platform+'_oauth');if(!w)throw Error('Your browser blocked the login window. Allow pop-ups for 127.0.0.1 and click Connect again.');try{w.document.write('<title>Postal AutoClip</title><body style="font-family:Segoe UI;background:#0b0e14;color:white;padding:30px"><h2>Opening '+platform+' login…</h2><p>You can return to the Accounts page after authorization.</p></body>')}catch{}return w}
async function connect(p){let w=null;let errId=p==='tiktok'?'#ttError':'#igError';try{setErr(errId,'');w=authWindow(p);await saveConfig();let x=await j('/'+p+'/auth');w.location.href=x.auth_url;w.focus()}catch(e){if(w)try{w.close()}catch{}setErr(errId,e.message)}}
async function disconnect(p){if(!confirm('Disconnect '+p+' from Postal AutoClip on this PC?'))return;await j('/disconnect',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({platform:p})});refreshStatus()}
async function selectIg(){try{setErr('#igError','');await j('/instagram/select',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({ig_user_id:document.querySelector('#igSelect').value})});refreshStatus()}catch(e){setErr('#igError',e.message)}}
refreshStatus();setInterval(refreshStatus,3000);
</script></body></html>'''

SUCCESS = '''<!doctype html><html><body style="font-family:Segoe UI;background:#0b0e14;color:#fff;padding:35px"><h2>{title}</h2><p>{message}</p><p>You can close this tab and return to Postal AutoClip Accounts.</p><script>setTimeout(()=>window.close(),2500)</script></body></html>'''


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str = "text/html; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status: int = 200) -> None:
        self._send(status, json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8")

    def _body(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except Exception:
            return {}

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        q = parse_qs(parsed.query)
        try:
            if parsed.path == "/":
                return self._send(200, PAGE.encode("utf-8"))
            if parsed.path == "/status":
                status = app_config_status()
                status["youtube"] = _youtube_status()
                return self._json(status)
            if parsed.path == "/tiktok/auth":
                save_app_config({"tiktok": {"redirect_uri": TIKTOK_REDIRECT}})
                return self._json({"auth_url": tiktok_authorization_url()})
            if parsed.path == "/instagram/auth":
                save_app_config({"instagram": {"redirect_uri": INSTAGRAM_REDIRECT}})
                return self._json({"auth_url": instagram_authorization_url()})
            if parsed.path == "/tiktok/callback":
                if q.get("error"):
                    raise RuntimeError(q.get("error_description", q["error"])[0])
                result = finish_tiktok_oauth((q.get("code") or [""])[0], (q.get("state") or [""])[0])
                return self._send(200, SUCCESS.format(title="TikTok connected", message=f"Scopes: {result.get('scope','')}").encode("utf-8"))
            if parsed.path == "/instagram/callback":
                if q.get("error"):
                    raise RuntimeError(q.get("error_description", q["error"])[0])
                result = finish_instagram_oauth((q.get("code") or [""])[0], (q.get("state") or [""])[0])
                label = "@" + str(result.get("username") or "Instagram")
                return self._send(200, SUCCESS.format(title="Instagram connected", message=f"Connected {label}.").encode("utf-8"))
            return self._json({"error": "not found"}, 404)
        except Exception as e:
            return self._send(400, SUCCESS.format(title="Connection failed", message=str(e)).encode("utf-8"))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/youtube/client":
                return self._json(_save_youtube_client(str(self._body().get("content") or "")))
            if parsed.path == "/youtube/connect":
                if not YOUTUBE_CLIENT.exists():
                    return self._json({"error": "Choose and save your Google Desktop OAuth JSON first."}, 400)
                threading.Thread(target=_connect_youtube_all, daemon=True, name="youtube-account-oauth").start()
                return self._json({"started": True, "message": "Google authorization is opening. Approve YouTube publishing and analytics access in your browser."})
            if parsed.path == "/config":
                return self._json(save_app_config(self._body()))
            if parsed.path == "/disconnect":
                body = self._body(); platform = str(body.get("platform") or "")
                if platform == "youtube":
                    _disconnect_youtube()
                else:
                    disconnect_platform(platform)
                return self._json({"ok": True})
            if parsed.path == "/instagram/select":
                body = self._body(); return self._json(select_instagram_account(str(body.get("ig_user_id") or "")))
            return self._json({"error": "not found"}, 404)
        except Exception as e:
            return self._json({"error": f"{type(e).__name__}: {e}"}, 400)


class Server(ThreadingHTTPServer):
    allow_reuse_address = True


def start_account_server() -> None:
    global _started
    with _lock:
        if _started:
            return
        _started = True
    start_token_maintenance()

    def run() -> None:
        try:
            Server((HOST, PORT), Handler).serve_forever(poll_interval=0.5)
        except OSError:
            pass

    threading.Thread(target=run, daemon=True, name="postal-account-manager").start()
