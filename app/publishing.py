from __future__ import annotations

import json
import math
import mimetypes
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

import httpx

from .config import ROOT, load_settings
from . import db
from .covers import ensure_cover, select_cover_ms
from .secure_store import SecureStoreError, read_secure_json, write_secure_json

YOUTUBE_SCOPE=["https://www.googleapis.com/auth/youtube.upload"]
SECRETS=ROOT/"secrets"
YOUTUBE_CLIENT=SECRETS/"youtube_client_secret.json"
YOUTUBE_TOKEN=SECRETS/"youtube_token.json"
TIKTOK_TOKEN=SECRETS/"tiktok_token.json"
INSTAGRAM_TOKEN=SECRETS/"instagram_token.json"
_worker_started=False
_worker_lock=threading.Lock()
Checkpoint = Callable[[str, dict[str, Any]], None]


class SubmissionUncertain(RuntimeError):
    """The platform may have accepted a post, so automatic replay could duplicate it."""


def _json_load(path: Path) -> dict[str,Any]:
    try: return read_secure_json(path)
    except SecureStoreError: return {}


def _caption_with_hashtags(post: dict[str,Any],limit:int) -> str:
    caption=str(post.get("caption") or post.get("title") or "").strip()
    tags=str(post.get("hashtags") or "").strip()
    text=(caption+("\n\n"+tags if tags else "")).strip()
    return text[:limit]


def _retry_delay(attempts: int) -> float:
    s=load_settings()
    base=max(5,int(s.publish_retry_base_seconds))
    cap=max(base,int(s.publish_retry_max_seconds))
    return float(min(cap,base*(2**max(0,int(attempts)-1))))

# -------------------- YouTube --------------------
def youtube_connection_status() -> dict[str,Any]:
    return {"client_secret_present":YOUTUBE_CLIENT.exists(),"token_present":YOUTUBE_TOKEN.exists(),
            "ready":YOUTUBE_CLIENT.exists() and YOUTUBE_TOKEN.exists(),"client_secret_path":str(YOUTUBE_CLIENT)}


def connect_youtube() -> dict[str,Any]:
    SECRETS.mkdir(parents=True,exist_ok=True)
    client=_json_load(YOUTUBE_CLIENT)
    if not client:
        raise RuntimeError(f"Missing {YOUTUBE_CLIENT}. Create a Google OAuth Desktop app, download the client JSON, and save it in Accounts.")
    try: from google_auth_oauthlib.flow import InstalledAppFlow
    except Exception as e: raise RuntimeError("Google OAuth libraries are not installed. Reinstall Postal AutoClip.") from e
    flow=InstalledAppFlow.from_client_config(client,YOUTUBE_SCOPE)
    creds=flow.run_local_server(port=8765,prompt="consent",access_type="offline",open_browser=True)
    write_secure_json(YOUTUBE_TOKEN,json.loads(creds.to_json()))
    return {"ok":True,"token_path":str(YOUTUBE_TOKEN)}


def _youtube_service():
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except Exception as e: raise RuntimeError("Google YouTube client libraries are not installed. Reinstall Postal AutoClip.") from e
    token=_json_load(YOUTUBE_TOKEN)
    if not token: raise RuntimeError("YouTube is not connected. Use Connect YouTube in Accounts first.")
    creds=Credentials.from_authorized_user_info(token,YOUTUBE_SCOPE)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request()); write_secure_json(YOUTUBE_TOKEN,json.loads(creds.to_json()))
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
    response=None; started=False
    try:
        while response is None:
            started=True
            _,response=request.next_chunk(num_retries=max(0,int(load_settings().youtube_resumable_retries)))
    except Exception as e:
        if started:
            raise SubmissionUncertain(
                "YouTube upload was interrupted after the resumable request started. "
                "AutoClip will not blindly retry because that could create a duplicate."
            ) from e
        raise
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
    data={}
    try:
        from .social_auth import refresh_tiktok_token
        data=refresh_tiktok_token()
    except Exception:
        data=_json_load(TIKTOK_TOKEN)
    return str(data.get("access_token") or "").strip()


def tiktok_connection_status() -> dict[str,Any]:
    token=_tiktok_access_token()
    return {"token_present":bool(token),"ready":bool(token),"token_path":str(TIKTOK_TOKEN)}


def tiktok_creator_info() -> dict[str,Any]:
    token=_tiktok_access_token()
    if not token:
        raise RuntimeError("TikTok access token missing. Set POSTAL_TIKTOK_ACCESS_TOKEN or connect TikTok in Accounts.")
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
    """Match TikTok's documented floor-count rule and merge trailing bytes into the final chunk."""
    size=max(0,int(size))
    if size <= 0: raise ValueError("TikTok upload is empty")
    target=10_000_000
    if size < target:
        return size,1
    count=max(1,size//target)
    return target,int(count)


def _tiktok_uploaded_last_byte(response:Any)->int|None:
    """Parse TikTok's recorded upload progress from Content-Range."""
    try:
        raw=str(response.headers.get("Content-Range") or response.headers.get("content-range") or "").strip()
        if not raw: return None
        value=raw.lower().replace("bytes","").strip().split("/",1)[0].strip()
        if "-" not in value: return None
        return int(value.rsplit("-",1)[1].strip())
    except Exception:
        return None


def _tiktok_put_chunk(client:httpx.Client,upload_url:str,mime:str,blob:bytes,first:int,size:int)->None:
    """Upload one deterministic byte range and retry only transient failures."""
    last=first+len(blob)-1
    retries=max(1,min(6,int(load_settings().publish_max_attempts)))
    retryable_status={408,409,425,429}
    last_error:BaseException|None=None
    for attempt in range(retries):
        response=None
        try:
            response=client.put(upload_url,headers={"Content-Type":mime,"Content-Length":str(len(blob)),
                "Content-Range":f"bytes {first}-{last}/{size}"},content=blob)
            status=int(response.status_code)
            if status < 400: return
            if status==416:
                uploaded_last=_tiktok_uploaded_last_byte(response)
                if uploaded_last is not None and uploaded_last>=last: return
                response.raise_for_status()
            if status not in retryable_status and status < 500: response.raise_for_status()
            try: response.raise_for_status()
            except httpx.HTTPStatusError as e: last_error=e
        except httpx.TransportError as e:
            last_error=e
        if attempt+1>=retries:
            if last_error is not None: raise last_error
            if response is not None: response.raise_for_status()
            raise RuntimeError("TikTok chunk upload failed without a response")
        delay=min(8.0,0.75*(2**attempt))
        if response is not None:
            try:
                retry_after=float(response.headers.get("Retry-After") or 0)
                if retry_after>0: delay=min(30.0,retry_after)
            except Exception: pass
        time.sleep(delay)


def publish_tiktok(path: Path,post: dict[str,Any],checkpoint:Checkpoint|None=None) -> dict[str,Any]:
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
        if checkpoint:
            try: checkpoint(str(publish_id),{"creator":creator,"publish_id":publish_id,"phase":"initialized"})
            except Exception as e:
                raise SubmissionUncertain("TikTok created a publish task but AutoClip could not save its checkpoint.") from e
        mime=mimetypes.guess_type(path.name)[0] or "video/mp4"
        with path.open("rb") as fh:
            first=0
            for index in range(total_chunks):
                remaining=size-first
                wanted=remaining if index==total_chunks-1 else min(chunk_size,remaining)
                blob=fh.read(wanted)
                if len(blob)!=wanted: raise IOError(f"TikTok upload read {len(blob)} bytes, expected {wanted}")
                _tiktok_put_chunk(client,str(upload_url),mime,blob,first,size)
                first += len(blob)
            if first != size: raise IOError(f"TikTok upload ended at {first} bytes, expected {size}")
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


def publish_instagram(path: Path,post: dict[str,Any],checkpoint:Checkpoint|None=None) -> dict[str,Any]:
    token,user_id=_instagram_credentials()
    if not token or not user_id: raise RuntimeError("Instagram is not connected. Reconnect Instagram in Accounts.")
    if not path.exists(): raise FileNotFoundError(path)
    s=load_settings(); caption=_caption_with_hashtags(post,2200)
    form={"media_type":"REELS","upload_type":"resumable","caption":caption,
          "share_to_feed":"true" if s.instagram_share_to_feed else "false",
          "thumb_offset":str(int(post.get("thumb_offset") or post.get("cover_ms") or 0))}
    timeout=httpx.Timeout(60,write=600,read=60,connect=30)
    with httpx.Client(timeout=timeout) as client:
        init=client.post(_graph_url(f"{user_id}/media"),headers={"Authorization":f"Bearer {token}"},data=form)
        init.raise_for_status(); data=init.json(); container_id=str(data.get("id") or ""); upload_uri=str(data.get("uri") or "")
        if not container_id or not upload_uri: raise RuntimeError(f"Instagram did not return a container id/upload uri: {data}")
        if checkpoint:
            try: checkpoint(container_id,{"container_id":container_id,"phase":"initialized"})
            except Exception as e: raise SubmissionUncertain("Instagram created a media container but AutoClip could not save its checkpoint.") from e
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
        except Exception: pass

    def checkpoint(platform_post_id:str,raw:dict[str,Any]):
        db.update_publish_job(int(row["id"]),status="submitted",platform_post_id=platform_post_id,
            result_json=json.dumps(raw,default=str)[:20000],error="")

    if row["platform"]=="youtube": return publish_youtube(path,post)
    if row["platform"]=="tiktok": return publish_tiktok(path,post,checkpoint=checkpoint)
    if row["platform"]=="instagram": return publish_instagram(path,post,checkpoint=checkpoint)
    raise RuntimeError(f"Unknown platform: {row['platform']}")


def recover_interrupted_posts() -> int:
    now=time.time(); stale=max(60,int(load_settings().publish_stale_seconds)); changed=0
    rows=db.q("SELECT * FROM publish_queue WHERE status='publishing'")
    for row in rows:
        last=float(row.get("last_attempt_at") or 0)
        if last and now-last < stale: continue
        if str(row.get("platform_post_id") or ""):
            db.update_publish_job(int(row["id"]),status="submitted",error="Recovered platform checkpoint after restart.")
        else:
            db.update_publish_job(int(row["id"]),status="needs_review",
                error="AutoClip restarted during an upload before a platform checkpoint was saved. Review before retrying to avoid a duplicate.")
        changed+=1
    return changed


def process_due_posts(limit:int=5):
    now=time.time(); s=load_settings()
    rows=db.q("""SELECT * FROM publish_queue
                  WHERE status='queued' AND scheduled_for<=? AND (next_attempt_at<=0 OR next_attempt_at<=?)
                  ORDER BY scheduled_for,id LIMIT ?""",(now,now,int(limit)))
    for row in rows:
        job_id=int(row["id"]); attempts=int(row.get("attempts") or 0)+1
        try:
            db.update_publish_job(job_id,status="publishing",attempts=attempts,error="",last_attempt_at=time.time())
        except Exception as e:
            current=db.q("SELECT * FROM publish_queue WHERE id=?",(job_id,),one=True) or {}
            if str(current.get("status") or "") != "needs_review":
                try: db.update_publish_job(job_id,status="needs_review",next_attempt_at=0,error=f"Preflight blocked before platform call: {type(e).__name__}: {e}")
                except Exception: pass
            continue
        try:
            result=_publish_one(row); asynchronous=bool(result.get("async"))
            db.update_publish_job(job_id,status="submitted" if asynchronous else "published",
                platform_post_id=result.get("platform_post_id",""),platform_url=result.get("url",""),
                published_at=0 if asynchronous else time.time(),next_attempt_at=0,
                result_json=json.dumps(result.get("raw") or {},default=str)[:20000],error="")
        except SubmissionUncertain as e:
            current=db.q("SELECT * FROM publish_queue WHERE id=?",(job_id,),one=True) or {}
            if str(current.get("platform_post_id") or ""):
                db.update_publish_job(job_id,status="submitted",next_attempt_at=0,error=str(e))
            else:
                db.update_publish_job(job_id,status="needs_review",next_attempt_at=0,error=str(e))
        except Exception as e:
            current=db.q("SELECT * FROM publish_queue WHERE id=?",(job_id,),one=True) or {}
            if str(current.get("platform_post_id") or ""):
                db.update_publish_job(job_id,status="submitted",next_attempt_at=0,error=f"Upload interrupted after platform checkpoint: {type(e).__name__}: {e}")
                continue
            if attempts>=max(1,int(s.publish_max_attempts)):
                db.update_publish_job(job_id,status="failed",next_attempt_at=0,error=f"{type(e).__name__}: {e}")
            else:
                retry_at=time.time()+_retry_delay(attempts)
                db.update_publish_job(job_id,status="queued",next_attempt_at=retry_at,error=f"Attempt {attempts} failed; retry scheduled: {type(e).__name__}: {e}")


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
    recover_interrupted_posts()
    def loop():
        while True:
            try: process_due_posts(); poll_submitted_tiktok(); poll_submitted_instagram()
            except Exception: pass
            time.sleep(max(5,int(load_settings().publish_poll_seconds)))
    threading.Thread(target=loop,daemon=True,name="postal-publish-worker").start()
