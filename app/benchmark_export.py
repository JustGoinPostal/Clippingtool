from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from . import db


def _load_labels(path: Path) -> list[dict[str,Any]]:
    payload=json.loads(Path(path).read_text(encoding="utf-8"))
    rows=payload.get("labels") if isinstance(payload,dict) else payload
    if not isinstance(rows,list): raise ValueError("labels file must be a list or an object containing labels")
    return [dict(x) for x in rows if isinstance(x,dict)]


def export_job_case(job_id: int, labels: list[dict[str,Any]], *, top_k: int=3, max_predictions: int|None=None) -> dict[str,Any]:
    job=db.q("SELECT id,status,duration FROM jobs WHERE id=?",(int(job_id),),one=True)
    if not job: raise KeyError(f"job {job_id} not found")
    rows=db.q("""SELECT id,start,end,score,event_type,story_archetype,status,title
                 FROM clips WHERE job_id=? AND status!='archived'
                 ORDER BY score DESC,id""",(int(job_id),))
    predictions=[{
        "clip_id":int(x["id"]),
        "start":float(x.get("start") or 0),
        "end":float(x.get("end") or 0),
        "score":float(x.get("score") or 0),
        "event_type":str(x.get("event_type") or ""),
        "story_archetype":str(x.get("story_archetype") or ""),
        "status":str(x.get("status") or ""),
        "title":str(x.get("title") or ""),
    } for x in rows]
    payload={
        "schema_version":1,
        "job_id":int(job_id),
        "job_status":str(job.get("status") or ""),
        "duration":float(job.get("duration") or 0),
        "top_k":max(1,int(top_k)),
        "labels":labels,
        "predictions":predictions,
    }
    if max_predictions is not None: payload["max_predictions"]=max(0,int(max_predictions))
    return payload


def main() -> None:
    parser=argparse.ArgumentParser(description="Export one processed private OSRS VOD into a reproducible benchmark case")
    parser.add_argument("--job-id",type=int,required=True,help="Processed AutoClip job id")
    parser.add_argument("--labels",type=Path,required=True,help="Private label JSON; media is never copied")
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--top-k",type=int,default=3)
    parser.add_argument("--max-predictions",type=int,default=None)
    args=parser.parse_args()
    db.init_db()
    payload=export_job_case(args.job_id,_load_labels(args.labels),top_k=args.top_k,max_predictions=args.max_predictions)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")
    print(f"Exported benchmark case with {len(payload['labels'])} labels and {len(payload['predictions'])} predictions to {args.output}")


if __name__=="__main__":
    main()
