from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from . import db
from .benchmark_export import export_job_case
from .browser_preview import ensure_browser_preview
from .config import ROOT

LABEL_DIR=ROOT/"data"/"benchmark_labels"
PREVIEW_DIR=ROOT/"data"/"cache"/"benchmark_preview"
PRIVATE_DIR=ROOT/"benchmarks"/"private"
EXAMPLE_MANIFEST=ROOT/"benchmarks"/"corpus.example.json"
MANIFEST_PATH=PRIVATE_DIR/"corpus.json"
PAGE=ROOT/"app"/"static"/"benchmark.html"

EVENT_TYPES=(
    "pvp_kill","pvp_escape","player_death","raid_reward","raid_complete","boss_kill",
    "pet_drop","collection_log","rare_drop","combat_achievement","skill_milestone",
    "personal_best","quest_complete","reaction","other",
)

app=FastAPI(title="Postal AutoClip Golden VOD Labeler",version="1.0")


def _safe_slug(value: str) -> str:
    value=re.sub(r"[^a-zA-Z0-9._-]+","_",str(value or "").strip()).strip("._-")
    if not value: raise ValueError("session id is required")
    return value[:96]


def _label_path(job_id: int) -> Path:
    return LABEL_DIR/f"job_{int(job_id)}.labels.json"


def _job(job_id: int) -> dict[str,Any]:
    row=db.q("SELECT id,source_path,status,duration,created_at,updated_at FROM jobs WHERE id=?",(int(job_id),),one=True)
    if not row: raise KeyError(job_id)
    return row


def _clean_label(row: dict[str,Any], index: int) -> dict[str,Any]:
    start=float(row.get("start",0) or 0); end=float(row.get("end",0) or 0)
    if start<0 or end<=start: raise ValueError(f"label {index+1} has an invalid time window")
    event=str(row.get("event_type") or "other").strip().lower()
    if event not in EVENT_TYPES: raise ValueError(f"label {index+1} has unknown event_type {event!r}")
    weight=float(row.get("weight",1.0) or 1.0)
    if weight<0.1 or weight>5.0: raise ValueError(f"label {index+1} weight must be between 0.1 and 5.0")
    label_id=_safe_slug(str(row.get("id") or f"{event}_{index+1:03d}"))
    out={"id":label_id,"start":round(start,3),"end":round(end,3),"event_type":event,"weight":round(weight,3)}
    note=str(row.get("note") or "").strip()
    if note: out["note"]=note[:500]
    return out


def load_label_state(job_id: int) -> dict[str,Any]:
    path=_label_path(job_id)
    if not path.exists(): return {"schema_version":1,"job_id":int(job_id),"assisted":False,"labels":[]}
    try:
        payload=json.loads(path.read_text(encoding="utf-8"))
        # Provenance did not exist in legacy drafts. Unknown provenance is never
        # allowed to silently become blind held-out truth in a commercial gate.
        if isinstance(payload,list):
            return {"schema_version":1,"job_id":int(job_id),"assisted":True,"labels":[dict(x) for x in payload if isinstance(x,dict)]}
        if not isinstance(payload,dict): raise ValueError
        rows=[dict(x) for x in (payload.get("labels") or []) if isinstance(x,dict)]
        assisted=bool(payload["assisted"]) if "assisted" in payload else True
        return {
            "schema_version":int(payload.get("schema_version",1) or 1),"job_id":int(job_id),
            "assisted":assisted,"labels":rows,
        }
    except Exception:
        # A corrupt existing provenance file must be rebuilt as tuning data, not
        # accidentally upgraded to blind held-out data after a later save.
        return {"schema_version":1,"job_id":int(job_id),"assisted":True,"labels":[]}


def _write_label_state(job_id: int, labels: list[dict[str,Any]], assisted: bool) -> None:
    LABEL_DIR.mkdir(parents=True,exist_ok=True)
    path=_label_path(job_id); tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps({
        "schema_version":1,"job_id":int(job_id),"assisted":bool(assisted),"labels":labels,
    },indent=2)+"\n",encoding="utf-8")
    tmp.replace(path)


def load_labels(job_id: int) -> list[dict[str,Any]]:
    return list(load_label_state(job_id)["labels"])


def save_labels(job_id: int, rows: list[dict[str,Any]]) -> list[dict[str,Any]]:
    _job(job_id)
    labels=[_clean_label(dict(row),i) for i,row in enumerate(rows)]
    ids=[x["id"] for x in labels]
    if len(ids)!=len(set(ids)): raise ValueError("label ids must be unique within a VOD")
    assisted=bool(load_label_state(job_id).get("assisted",False))
    _write_label_state(job_id,labels,assisted)
    return labels


def mark_assisted(job_id: int) -> dict[str,Any]:
    _job(job_id)
    state=load_label_state(job_id)
    if not bool(state.get("assisted",False)):
        _write_label_state(job_id,list(state.get("labels") or []),True)
        state=load_label_state(job_id)
    return state


def _default_manifest() -> dict[str,Any]:
    requirements={
        "min_total_labels":60,"min_heldout_labels":24,"min_heldout_sessions":2,
        "required_event_types":[
            "pvp_kill","pvp_escape","player_death","raid_reward","boss_kill","pet_drop",
            "collection_log","combat_achievement","skill_milestone",
        ],
    }
    if EXAMPLE_MANIFEST.exists():
        try:
            payload=json.loads(EXAMPLE_MANIFEST.read_text(encoding="utf-8"))
            if isinstance(payload.get("release_requirements"),dict): requirements=payload["release_requirements"]
        except Exception: pass
    return {"schema_version":1,"sessions":[],"release_requirements":requirements}


def _load_manifest() -> dict[str,Any]:
    if not MANIFEST_PATH.exists(): return _default_manifest()
    try:
        payload=json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if not isinstance(payload,dict): raise ValueError
        payload.setdefault("schema_version",1); payload.setdefault("sessions",[])
        payload.setdefault("release_requirements",_default_manifest()["release_requirements"])
        return payload
    except Exception as e:
        raise RuntimeError(f"private corpus manifest is invalid: {e}") from e


def export_session(job_id: int, session_id: str, split: str, *, top_k: int=3, max_predictions: int|None=None) -> dict[str,Any]:
    job=_job(job_id); state=load_label_state(job_id); labels=list(state.get("labels") or [])
    if not labels: raise ValueError("label this VOD before exporting it")
    assisted=bool(state.get("assisted",False))
    slug=_safe_slug(session_id)
    split=str(split or "").strip().lower()
    if split not in {"tuning","heldout"}: raise ValueError("split must be tuning or heldout")
    if split=="heldout" and assisted:
        raise ValueError("held-out export blocked: AutoClip predictions were revealed for this VOD, so its labels are permanently marked assisted")

    PRIVATE_DIR.mkdir(parents=True,exist_ok=True)
    labels_name=f"{slug}.labels.json"; case_name=f"{slug}.case.json"
    labels_path=PRIVATE_DIR/labels_name; case_path=PRIVATE_DIR/case_name
    labeling_mode="assisted" if assisted else "blind"
    labels_path.write_text(json.dumps({
        "schema_version":1,"job_id":int(job_id),"labeling_mode":labeling_mode,"labels":labels,
    },indent=2)+"\n",encoding="utf-8")
    case=export_job_case(int(job_id),labels,top_k=max(1,int(top_k)),max_predictions=max_predictions)
    case["session_id"]=slug; case["labeling_mode"]=labeling_mode
    case_path.write_text(json.dumps(case,indent=2)+"\n",encoding="utf-8")

    manifest=_load_manifest(); sessions=list(manifest.get("sessions") or [])
    entry={"id":slug,"split":split,"case":case_name,"labeling_mode":labeling_mode}
    replaced=False
    for i,row in enumerate(sessions):
        if isinstance(row,dict) and str(row.get("id") or "")==slug:
            sessions[i]=entry; replaced=True; break
    if not replaced: sessions.append(entry)
    manifest["sessions"]=sessions
    tmp=MANIFEST_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8"); tmp.replace(MANIFEST_PATH)
    return {
        "ok":True,"job_id":int(job_id),"session_id":slug,"split":split,"blind_labeled":not assisted,
        "labeling_mode":labeling_mode,"label_count":len(labels),"prediction_count":len(case.get("predictions") or []),
        "labels_path":str(labels_path),"case_path":str(case_path),"manifest_path":str(MANIFEST_PATH),
        "source_filename":Path(str(job.get("source_path") or "")).name,
    }


@app.on_event("startup")
def startup():
    db.init_db(); LABEL_DIR.mkdir(parents=True,exist_ok=True); PRIVATE_DIR.mkdir(parents=True,exist_ok=True); PREVIEW_DIR.mkdir(parents=True,exist_ok=True)


@app.get("/",response_class=HTMLResponse)
def home():
    if not PAGE.exists(): raise HTTPException(500,"benchmark labeler page is missing")
    return PAGE.read_text(encoding="utf-8")


@app.get("/api/jobs")
def jobs():
    rows=db.q("SELECT id,source_path,status,duration,created_at,updated_at FROM jobs ORDER BY id DESC LIMIT 250")
    return [{
        "id":int(x["id"]),"filename":Path(str(x.get("source_path") or "")).name,
        "status":str(x.get("status") or ""),"duration":float(x.get("duration") or 0),
        "created_at":x.get("created_at"),"label_count":len(load_labels(int(x["id"]))),
        "assisted":bool(load_label_state(int(x["id"])).get("assisted",False)),
    } for x in rows]


@app.get("/api/jobs/{job_id}")
def job_detail(job_id: int, reveal_predictions: bool=False):
    try: job=_job(job_id)
    except KeyError: raise HTTPException(404,"Job not found")
    state=mark_assisted(job_id) if reveal_predictions else load_label_state(job_id)
    clips=[]
    if reveal_predictions:
        clips=db.q("""SELECT id,start,end,score,event_type,story_archetype,status,title,reason
                      FROM clips WHERE job_id=? AND status!='archived' ORDER BY score DESC,id LIMIT 150""",(int(job_id),))
    return {
        "id":int(job["id"]),"filename":Path(str(job.get("source_path") or "")).name,
        "status":job.get("status"),"duration":float(job.get("duration") or 0),
        "labels":list(state.get("labels") or []),"assisted":bool(state.get("assisted",False)),
        "predictions":clips,"predictions_revealed":bool(reveal_predictions),"event_types":list(EVENT_TYPES),
    }


@app.put("/api/jobs/{job_id}/labels")
def labels_put(job_id: int, payload: dict=Body(...)):
    rows=payload.get("labels") if isinstance(payload.get("labels"),list) else []
    try: labels=save_labels(job_id,rows)
    except KeyError: raise HTTPException(404,"Job not found")
    except ValueError as e: raise HTTPException(400,str(e))
    state=load_label_state(job_id)
    return {"ok":True,"job_id":int(job_id),"labels":labels,"count":len(labels),"assisted":bool(state.get("assisted",False))}


@app.post("/api/jobs/{job_id}/export")
def export(job_id: int, payload: dict=Body(...)):
    try:
        return export_session(
            job_id,str(payload.get("session_id") or ""),str(payload.get("split") or ""),
            top_k=int(payload.get("top_k",3) or 3),
            max_predictions=int(payload["max_predictions"]) if payload.get("max_predictions") is not None else None,
        )
    except KeyError: raise HTTPException(404,"Job not found")
    except (ValueError,RuntimeError) as e: raise HTTPException(400,str(e))


@app.get("/source/{job_id}")
def source(job_id: int):
    try: row=_job(job_id)
    except KeyError: raise HTTPException(404,"Job not found")
    path=Path(str(row.get("source_path") or ""))
    if not path.exists(): raise HTTPException(404,"Source recording is missing")
    try:
        playable,mode=ensure_browser_preview(path,PREVIEW_DIR)
    except Exception as e:
        raise HTTPException(500,f"Could not create browser preview: {type(e).__name__}: {e}")
    return FileResponse(
        playable,media_type="video/mp4",
        headers={"Cache-Control":"private, max-age=3600","X-Postal-Preview-Mode":mode},
    )


def run():
    import uvicorn
    uvicorn.run("app.benchmark_labeler:app",host="127.0.0.1",port=8792,reload=False)


if __name__=="__main__":
    run()
