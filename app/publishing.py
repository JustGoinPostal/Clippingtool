from __future__ import annotations

import json
import math
import mimetypes
import os
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from .config import ROOT, load_settings
from . import db
from .covers import ensure_cover, select_cover_ms

YOUTUBE_SCOPE=["https://www.googleapis.com/auth/youtube.upload"]
SECRETS=ROOT/"secrets"
YOUTUBE_CLIENT=SECRETS/"youtube_client_secret.json"
YOUTUBE_TOKEN=SECRETS/"youtube_token.json"
TIKTOK_TOKEN=SECRETS/"tiktok_token.json"
INSTAGRAM_TOKEN=SECRETS/"instagram_token.json"
_worker_started=False
_worker_lock=threading.Lock()


def _json_load(path: Path) -> dict[str,Any]:
    if not path.exists(): return {}
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return {}


def _caption_with_hashtags(post: dict[str,Any],limit:int) -> str:
    caption=str(post.get("caption") or post.get("title") or "").strip()
    tags=str(post.get("hashtags") or "").strip()
    text=(caption+("\n\n"+tags if tags else "")).strip()
    return text[:limit]

# -------------------- YouTube --------------------
def youtube_connection_status() -> dict[str,Any]:
    return {"client_secret_present":YOUTUBE_CLIENT.exists(),"token_present":YOUTUBE_TOKEN.exists(),
            "ready":YOUTUBE_CLIENT.exists() and YOUTUBE_TOKEN.exists(),"client_secret_path":str(YOUTUBE_CLIENT)}


def connect_youtube() -> dict[str,Any]:
    SECRETS.mkdir(parents=True,exist_ok=True)
    if not YOUTUBE_CLIENT.exists():
        raise RuntimeError(f"Missing {YOUTUBE_CLIENT}. Create a Google OAuth Desktop app, download the client JSON, and save it there.")
    try: from google_auth_oauthlib.flow import InstalledAppFlow
    except Exception as e: raise RuntimeError("Google OAuth libraries are not installed. Re-run install.ps1.") from e
    flow=InstalledAppFlow.from_client_secrets_file(str(YOUTUBE_CLIENT),YOUTUBE_SCOPE)
    creds=flow.run_local_server(port=8765,prompt="consent",access_type="offline",open_browser=True)
    YOUTUBE_TOKEN.write_text(creds.to_json(),encoding="utf-8")
    return {"ok":True,"token_path":str(YOUTUBE_TOKEN)}


def _youtube_service():
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except Exception as e: raise RuntimeError("Google YouTube client libraries are not installed. Re-run install.ps1.") from e
    if not YOUTUBE_TOKEN.exists(): raise RuntimeError("YouTube is not connected. Use Connect YouTube in the dashboard first.")
    creds=Credentials.from_authorized_user_file(str(YOUTUBE_TOKEN),YOUTUBE_SCOPE)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request()); YOUTUBE_TOKEN.write_text(creds.to_json(),encoding="utf-8")
    if not creds.valid: raise RuntimeError("YouTube authorization is invalid. Reconnect YouTube.")
    return build("youtube","v3",credentials=creds,cache_discovery=False)


def publish_youtube(path: Path,post: dict[str,Any]) -> dict[str,Any]:
    from googleapiclient.http import MediaFileUpload
    if not path.exists(): raise FileNotFoundError(path)
    service=_youtube_service(); title=(post.get("title") or path.stem)[:100]
    description=_caption_with_hashtags(post,5000)
    tags=[x.lstrip("#") for x in (post.get("hashtags") or "").split() if x.startswith("#")][:25]
    privacy=str(post.get("privacy") or "private").lower()
    if privacy not in {"private","public","unlisted"}: privacy="private"
    body={"snippet":{"title":title,"description":description,"categoryId":"20","tags":tags},
          "status":{"privacyStatus":privacy,"selfDeclaredMadeForKids":False}}
    media=MediaFileUpload(str(path),mimetype="video/mp4",chunksize=-1,resumable=True)
    request=service.videos().insert(part="snippet,status",body=body,media_body=media)
    response=None
    while response is None: _,response=request.next_chunk()
    video_id=response.get("id"); raw={"upload":response}
    cover_path=post.get("_cover_path")
    if video_id and cover_path and load_settings().youtube_set_thumbnail:
        try:
            thumb=MediaFileUpload(str(cover_path),mimetype="image/jpeg",resumable=False)
            raw["thumbnail"]=service.thumbnails().set(videoId=video_id,media_body=thumb).execute()
        except Exception as e:
            raw["thumbnail_warning"]=f"{type(e).__name__}: {e}"
    return {"platform_post_id":video_id or "","url":f"https://www.youtube.com/watch?v={video_id}" if video_id else "","raw":raw}

# -------------------- TikTok --------------------
def _tiktok_access_token() -> str:
    env=os.getenv("POSTAL_TIKTOK_ACCESS_TOKEN","").strip()
    if env: return env
    return str(_json_load(TIKTOK_TOKEN).get("access_token") or "").strip()


def tiktok_connection_status() -> dict[str,Any]:
    token=_tiktok_access_token()
    return {"token_present":bool(token),"ready":bool(token),"token_path":str(TIKTOK_TOKEN)}


def tiktok_creator_info() -> dict[str,Any]:
    token=_tiktok_access_token()
    if not token:
        raise RuntimeError("TikTok access token missing. Set POSTAL_TIKTOK_ACCESS_TOKEN or save {\"access_token\":\"...\"} in secrets/tiktok_token.json.")
    with httpx.Client(timeout=30) as client:
        r=client.post("https://open.tiktokapis.com/v2/post/publish/creator_info/query/",
            headers={"Authorization":f"Bearer {token}","Content-Type":"application/json; charset=UTF-8"},json={})
        r.raise_for_status(); data=r.json()
    err=data.get("error") or {}
    if err.get("code") not in {None,"ok"}: raise RuntimeError(f"TikTok creator-info error: {err.get('code')}: {err.get('message')}")
    return data.get("data") or {}


def tiktok_publish_status(publish_id: str) -> dict[str,Any]:
    token=_tiktok_access_token()
    if not token: raise RuntimeError("TikTok is not connected.")
    with httpx.Client(timeout=30) as client:
        r=client.post("https://open.tiktokapis.com/v2/post/publish/status/fetch/",
            headers={"Authorization":f"Bearer {token}","Content-Type":"application/json; charset=UTF-8"},json={"publish_id":publish_id})
        r.raise_for_status(); payload=r.json()
    err=payload.get("error") or {}
    if err.get("code") not in {None,"ok"}: raise RuntimeError(f"TikTok status error: {err.get('code')}: {err.get('message')}")
    return payload.get("data") or {}


def _tiktok_chunk_plan(size:int)->tuple[int,int]:
    chunk=10*1024*1024; count=max(1,math.ceil(size/chunk))
    if count==1: chunk=size
    return chunk,count


def publish_tiktok(path: Path,post: dict[str,Any]) -> dict[str,Any]:
    token=_tiktok_access_token()
    if not token: raise RuntimeError("TikTok is not connected.")
    if not path.exists(): raise FileNotFoundError(path)
    creator=tiktok_creator_info(); allowed=creator.get("privacy_level_options") or []
    privacy=str(post.get("privacy") or "SELF_ONLY")
    if privacy not in allowed: raise RuntimeError(f"TikTok privacy {privacy!r} is not allowed for this creator. Allowed: {allowed}")
    size=path.stat().st_size; chunk_size,total_chunks=_tiktok_chunk_plan(size)
    caption=_caption_with_hashtags(post,2200)
    init_body={"post_info":{"title":caption,"privacy_level":privacy,"disable_duet":bool(post.get("disable_duet",False)),
        "disable_comment":bool(post.get("disable_comment",False)),"disable_stitch":bool(post.get("disable_stitch",False)),
        "video_cover_timestamp_ms":int(post.get("cover_ms") or 1000),"brand_content_toggle":False,"brand_organic_toggle":False},
        "source_info":{"source":"FILE_UPLOAD","video_size":size,"chunk_size":chunk_size,"total_chunk_count":total_chunks}}
    headers={"Authorization":f"Bearer {token}","Content-Type":"application/json; charset=UTF-8"}
    with httpx.Client(timeout=60) as client:
        init=client.post("https://open.tiktokapis.com/v2/post/publish/video/init/",headers=headers,json=init_body)
        init.raise_for_status(); payload=init.json(); err=payload.get("error") or {}
        if err.get("code") not in {None,"ok"}: raise RuntimeError(f"TikTok publish-init error: {err.get('code')}: {err.get('message')}")
        info=payload.get("data") or {}; upload_url=info.get("upload_url"); publish_id=info.get("publish_id")
        if not upload_url or not publish_id: raise RuntimeError("TikTok did not return upload_url/publish_id")
        mime=mimetypes.guess_type(path.name)[0] or "video/mp4"
        with path.open("rb") as fh:
            first=0
            while first<size:
                blob=fh.read(min(chunk_size,size-first)); last=first+len(blob)-1
                up=client.put(upload_url,headers={"Content-Type":mime,"Content-Length":str(len(blob)),
                    "Content-Range":f"bytes {first}-{last}/{size}"},content=blob)
                up.raise_for_status(); first=last+1
    return {"platform_post_id":publish_id,"url":"","raw":{"creator":creator,"publish_id":publish_id},"async":True}

# -------------------- Instagram Reels --------------------
def _instagram_credentials() -> tuple[str,str]:
    token=os.getenv("POSTAL_INSTAGRAM_ACCESS_TOKEN","").strip()
    user_id=os.getenv("POSTAL_INSTAGRAM_USER_ID","").strip()
    data=_json_load(INSTAGRAM_TOKEN)
    token=token or str(data.get("access_token") or "").strip()
    user_id=user_id or str(data.get("ig_user_id") or data.get("instagram_user_id") or "").strip()
    return token,user_id


def instagram_connection_status() -> dict[str,Any]:
    token,user_id=_instagram_credentials()
    return {"token_present":bool(token),"ig_user_id_present":bool(user_id),"ready":bool(token and user_id),
            "token_path":str(INSTAGRAM_TOKEN),"graph_version":load_settings().instagram_graph_version}


def _graph_url(path: str) -> str:
    version=str(load_settings().instagram_graph_version or "v26.0").strip("/")
    return f"https://graph.facebook.com/{version}/{path.lstrip('/')}"


def publish_instagram(path: Path,post: dict[str,Any]) -> dict[str,Any]:
    token,user_id=_instagram_credentials()
    if not token or not user_id:
        raise RuntimeError("Instagram is not connected. Add access_token and ig_user_id to secrets/instagram_token.json.")
    if not path.exists(): raise FileNotFoundError(path)
    s=load_settings(); caption=_caption_with_hashtags(post,2200)
    form={"media_type":"REELS","upload_type":"resumable","caption":caption,
          "share_to_feed":"true" if s.instagram_share_to_feed else "false",
          "thumb_offset":str(int(post.get("thumb_offset") or post.get("cover_ms") or 0))}
    timeout=httpx.Timeout(60,write=600,read=60,connect=30)
    with httpx.Client(timeout=timeout) as client:
        init=client.post(_graph_url(f"{user_id}/media"),headers={"Authorization":f"Bearer {token}"},data=form)
        init.raise_for_status(); data=init.json(); container_id=str(data.get("id") or ""); upload_uri=str(data.get("uri") or "")
        if not container_id or not upload_uri:
            raise RuntimeError(f"Instagram did not return a container id/upload uri: {data}")
        size=path.stat().st_size
        with path.open("rb") as fh:
            stream=iter(lambda:fh.read(1024*1024),b"")
            up=client.post(upload_uri,headers={"Authorization":f"OAuth {token}","offset":"0","file_size":str(size),
                "Content-Type":"application/octet-stream","Content-Length":str(size)},content=stream)
            up.raise_for_status(); upload_result=up.json() if up.content else {"success":True}
    return {"platform_post_id":container_id,"url":"","raw":{"container_id":container_id,"upload":upload_result},"async":True}


def instagram_container_status(container_id: str) -> dict[str,Any]:
    token,_=_instagram_credentials()
    if not token: raise RuntimeError("Instagram is not connected.")
    with httpx.Client(timeout=30) as client:
        r=client.get(_graph_url(container_id),headers={"Authorization":f"Bearer {token}"},params={"fields":"status_code,status"})
        r.raise_for_status(); return r.json()


def instagram_publish_container(container_id: str) -> dict[str,Any]:
    token,user_id=_instagram_credentials()
    if not token or not user_id: raise RuntimeError("Instagram is not connected.")
    with httpx.Client(timeout=30) as client:
        r=client.post(_graph_url(f"{user_id}/media_publish"),headers={"Authorization":f"Bearer {token}"},data={"creation_id":container_id})
        r.raise_for_status(); payload=r.json(); media_id=str(payload.get("id") or "")
        permalink=""
        if media_id:
            meta=client.get(_graph_url(media_id),headers={"Authorization":f"Bearer {token}"},params={"fields":"permalink"})
            if meta.is_success: permalink=str((meta.json() or {}).get("permalink") or "")
    return {"media_id":media_id,"permalink":permalink,"raw":payload}

# -------------------- shared queue --------------------
def platform_status() -> dict[str,Any]:
    return {"youtube":youtube_connection_status(),"tiktok":tiktok_connection_status(),"instagram":instagram_connection_status()}


def queue_post(render_id:int,platform:str,scheduled_for:float,title:str="",caption:str="",hashtags:str="",privacy:str="private",options:dict[str,Any]|None=None)->int:
    render=db.q("SELECT renders.*,clips.id AS clip_id FROM renders JOIN clips ON clips.id=renders.clip_id WHERE renders.id=?",(render_id,),one=True)
    if not render: raise KeyError(render_id)
    return db.add_publish_job(int(render["clip_id"]),render_id,platform,float(scheduled_for),title,caption,hashtags,privacy,options or {})


def _publish_one(row: dict[str,Any]):
    render=db.q("SELECT * FROM renders WHERE id=?",(row["render_id"],),one=True)
    clip=db.q("SELECT * FROM clips WHERE id=?",(row["clip_id"],),one=True) or {}
    if not render: raise RuntimeError("Render no longer exists")
    path=Path(render["output_path"]); options={}
    try: options=json.loads(row.get("options_json") or "{}")
    except Exception: pass
    post=dict(row); post.update(options)
    if "cover_ms" not in post:
        post["cover_ms"]=select_cover_ms(clip,render); post["thumb_offset"]=post["cover_ms"]
    if load_settings().auto_cover_enabled:
        try:
            cover,_=ensure_cover(render,clip); post["_cover_path"]=str(cover)
        except Exception:
            pass
    if row["platform"]=="youtube": return publish_youtube(path,post)
    if row["platform"]=="tiktok": return publish_tiktok(path,post)
    if row["platform"]=="instagram": return publish_instagram(path,post)
    raise RuntimeError(f"Unknown platform: {row['platform']}")


def process_due_posts(limit:int=5):
    rows=db.q("SELECT * FROM publish_queue WHERE status='queued' AND scheduled_for<=? ORDER BY scheduled_for,id LIMIT ?",(time.time(),int(limit)))
    for row in rows:
        job_id=int(row["id"]); attempts=int(row.get("attempts") or 0)+1
        db.update_publish_job(job_id,status="publishing",attempts=attempts,error="")
        try:
            result=_publish_one(row); asynchronous=bool(result.get("async"))
            db.update_publish_job(job_id,status="submitted" if asynchronous else "published",
                platform_post_id=result.get("platform_post_id",""),platform_url=result.get("url",""),
                published_at=0 if asynchronous else time.time(),result_json=json.dumps(result.get("raw") or {},default=str)[:20000])
        except Exception as e:
            db.update_publish_job(job_id,status="failed" if attempts>=3 else "queued",error=f"{type(e).__name__}: {e}")


def poll_submitted_tiktok(limit:int=10):
    rows=db.q("SELECT * FROM publish_queue WHERE platform='tiktok' AND status='submitted' ORDER BY updated_at LIMIT ?",(int(limit),))
    for row in rows:
        try:
            data=tiktok_publish_status(str(row.get("platform_post_id") or "")); state=str(data.get("status") or "")
            raw=json.dumps(data,default=str)[:20000]
            if state=="PUBLISH_COMPLETE":
                db.update_publish_job(int(row["id"]),status="published",published_at=time.time(),result_json=raw,error="")
            elif state=="FAILED":
                db.update_publish_job(int(row["id"]),status="failed",result_json=raw,error=str(data.get("fail_reason") or "TikTok publish failed"))
            else: db.update_publish_job(int(row["id"]),result_json=raw)
        except Exception as e:
            db.update_publish_job(int(row["id"]),error=f"Status check: {type(e).__name__}: {e}")


def poll_submitted_instagram(limit:int=10):
    rows=db.q("SELECT * FROM publish_queue WHERE platform='instagram' AND status='submitted' ORDER BY updated_at LIMIT ?",(int(limit),))
    for row in rows:
        try:
            container_id=str(row.get("platform_post_id") or "")
            data=instagram_container_status(container_id); state=str(data.get("status_code") or "").upper()
            if state=="FINISHED":
                result=instagram_publish_container(container_id)
                db.update_publish_job(int(row["id"]),status="published",platform_post_id=result.get("media_id") or container_id,
                    platform_url=result.get("permalink") or "",published_at=time.time(),error="",
                    result_json=json.dumps({"container":data,"publish":result.get("raw")},default=str)[:20000])
            elif state in {"ERROR","EXPIRED"}:
                db.update_publish_job(int(row["id"]),status="failed",error=str(data.get("status") or f"Instagram {state}"),
                    result_json=json.dumps(data,default=str)[:20000])
            else: db.update_publish_job(int(row["id"]),result_json=json.dumps(data,default=str)[:20000])
        except Exception as e:
            db.update_publish_job(int(row["id"]),error=f"Status check: {type(e).__name__}: {e}")


def start_publish_worker():
    global _worker_started
    with _worker_lock:
        if _worker_started:return
        _worker_started=True
    def loop():
        while True:
            try:
                process_due_posts(); poll_submitted_tiktok(); poll_submitted_instagram()
            except Exception: pass
            time.sleep(max(5,int(load_settings().publish_poll_seconds)))
    threading.Thread(target=loop,daemon=True,name="postal-publish-worker").start()
