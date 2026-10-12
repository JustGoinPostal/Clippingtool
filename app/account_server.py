from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

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
_started = False
_lock = threading.Lock()

PAGE = r'''<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Postal AutoClip Accounts</title><style>
:root{font-family:Segoe UI,Arial,sans-serif;color:#f5f7fb;background:#090c12}*{box-sizing:border-box}body{margin:0}.wrap{max-width:980px;margin:auto;padding:26px}.top{display:flex;justify-content:space-between;align-items:center;gap:10px}.brand{font-size:28px;font-weight:900}.muted{color:#99a4b5}.card{background:#121720;border:1px solid #293241;border-radius:16px;padding:18px;margin-top:16px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}label{display:block;font-size:12px;color:#aab4c2;margin-top:9px}input,select,button{width:100%;padding:10px;border-radius:9px;border:1px solid #384355;background:#0c1118;color:#fff}button{width:auto;cursor:pointer;font-weight:750}.primary{background:#eef2ff;color:#0b0e14}.good{color:#86e6a8}.warn{color:#f1cd82}.bad{color:#f29ca5}.pill{display:inline-block;border:1px solid #435066;border-radius:999px;padding:4px 8px;font-size:12px}.secret{font-family:monospace}.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:13px}.code{font-family:Consolas,monospace;background:#090d13;border:1px solid #283241;border-radius:8px;padding:8px;word-break:break-all}.tiny{font-size:12px}@media(max-width:760px){.grid{grid-template-columns:1fr}}</style></head>
<body><div class="wrap"><div class="top"><div><div class="brand">POSTAL AUTOCLIP · ACCOUNTS</div><div class="muted">Browser authorization. Tokens and app secrets stay on this PC.</div></div><button onclick="refreshStatus()">Refresh</button></div>
<div class="card"><b>How this works</b><div class="muted tiny" style="margin-top:7px">Create your TikTok Developer app and Meta app once. Paste each app's ID/key and secret below. After that, use the Connect buttons. You should not need to hand-edit token JSON files again.</div></div>
<div class="grid">
<div class="card"><h2>TikTok</h2><div id="ttStatus" class="warn">Loading…</div><label>Client Key<input id="ttKey"></label><label>Client Secret<input id="ttSecret" class="secret" type="password" placeholder="Leave blank to keep saved secret"></label><label>Register this Desktop redirect URI in TikTok Login Kit</label><div class="code">''' + TIKTOK_REDIRECT + r'''</div><div class="tiny muted" style="margin-top:8px">Requested scopes: user.info.basic, video.list, video.publish. TikTok Desktop Login uses PKCE and AutoClip refreshes the access token silently.</div><div class="actions"><button onclick="saveConfig()">Save App Keys</button><button class="primary" onclick="connect('tiktok')">Connect TikTok</button><button onclick="disconnect('tiktok')">Disconnect</button></div></div>
<div class="card"><h2>Instagram</h2><div id="igStatus" class="warn">Loading…</div><label>Meta App ID<input id="igId"></label><label>Meta App Secret<input id="igSecret" class="secret" type="password" placeholder="Leave blank to keep saved secret"></label><label>Register this Facebook Login for Business redirect URI</label><div class="code">''' + INSTAGRAM_REDIRECT + r'''</div><div class="tiny muted" style="margin-top:8px">Use a Professional Instagram account linked to a Facebook Page. This keeps AutoClip's direct local resumable Reel upload instead of requiring a public video host.</div><div id="igChoice" style="display:none"><label>Instagram account<select id="igSelect"></select></label><button style="margin-top:8px" onclick="selectIg()">Use Selected Account</button></div><div class="actions"><button onclick="saveConfig()">Save App Keys</button><button class="primary" onclick="connect('instagram')">Connect Instagram</button><button onclick="disconnect('instagram')">Disconnect</button></div></div>
</div>
<div class="card"><b>Security</b><div class="muted tiny" style="margin-top:7px">Developer app secrets and OAuth tokens are saved only under <span class="pill">secrets/</span>. That folder is Git-ignored. AutoClip's local services bind to 127.0.0.1 only.</div></div>
</div><script>
async function j(u,o){let r=await fetch(u,o);let t=await r.text();if(!r.ok)throw Error(t);try{return JSON.parse(t)}catch{return t}}
async function refreshStatus(){try{let s=await j('/status');let t=s.tiktok||{},i=s.instagram||{};document.querySelector('#ttKey').value=t.client_key||'';document.querySelector('#igId').value=i.client_id||'';document.querySelector('#ttStatus').className=t.connected?'good':t.configured?'warn':'bad';document.querySelector('#ttStatus').textContent=t.connected?`CONNECTED · scopes: ${t.scope||'unknown'}`:t.configured?'APP READY · account not connected':'APP KEYS NEEDED';document.querySelector('#igStatus').className=i.connected?'good':i.configured?'warn':'bad';document.querySelector('#igStatus').textContent=i.connected?`CONNECTED · @${i.username||i.ig_user_id}${i.page_name?' · '+i.page_name:''}`:i.configured?'APP READY · account not connected':'APP KEYS NEEDED';let choices=i.account_choices||[],box=document.querySelector('#igChoice'),sel=document.querySelector('#igSelect');if(choices.length>1){box.style.display='block';sel.innerHTML=choices.map(x=>`<option value="${x.ig_user_id}" ${x.ig_user_id===i.ig_user_id?'selected':''}>@${x.username||x.ig_user_id} · ${x.page_name||'Page'}</option>`).join('')}else box.style.display='none'}catch(e){alert(e)}}
async function saveConfig(){let body={tiktok:{client_key:document.querySelector('#ttKey').value,client_secret:document.querySelector('#ttSecret').value,redirect_uri:''' + json.dumps(TIKTOK_REDIRECT) + r'''},instagram:{client_id:document.querySelector('#igId').value,client_secret:document.querySelector('#igSecret').value,redirect_uri:''' + json.dumps(INSTAGRAM_REDIRECT) + r'''}};await j('/config',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});document.querySelector('#ttSecret').value='';document.querySelector('#igSecret').value='';await refreshStatus()}
async function connect(p){try{await saveConfig();let x=await j('/'+p+'/auth');window.open(x.auth_url,'_blank','noopener');}catch(e){alert(e)}}
async function disconnect(p){if(!confirm('Disconnect '+p+' from Postal AutoClip on this PC?'))return;await j('/disconnect',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({platform:p})});refreshStatus()}
async function selectIg(){await j('/instagram/select',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({ig_user_id:document.querySelector('#igSelect').value})});refreshStatus()}
refreshStatus();setInterval(refreshStatus,5000);
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
                return self._json(app_config_status())
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
            if parsed.path == "/config":
                return self._json(save_app_config(self._body()))
            if parsed.path == "/disconnect":
                body = self._body(); disconnect_platform(str(body.get("platform") or ""))
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
            # Another AutoClip process may already own the account-manager port.
            pass

    threading.Thread(target=run, daemon=True, name="postal-account-manager").start()
