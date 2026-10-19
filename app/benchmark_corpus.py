from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .benchmark import evaluate_payload
from .benchmark_gate import compare_metrics

_ALLOWED_SPLITS={"tuning","heldout"}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _aggregate(results: list[dict[str,Any]]) -> dict[str,Any]:
    keys=(
        "label_count","prediction_count","matched_labels","matched_predictions",
        "top_k_matched_labels","duplicate_predictions","false_positive_count",
        "typed_match_count","event_type_correct_count","boundary_match_count",
    )
    totals={k:sum(int(r.get(k) or 0) for r in results) for k in keys}
    weight_total=sum(float(r.get("weight_total") or 0) for r in results)
    matched_weight=sum(float(r.get("matched_weight") or 0) for r in results)
    iou_sum=sum(float(r.get("boundary_iou_sum") or 0) for r in results)
    labels=totals["label_count"]; predictions=totals["prediction_count"]
    typed=totals["typed_match_count"]; boundary=totals["boundary_match_count"]
    return {
        **totals,
        "weight_total":round(weight_total,6),
        "matched_weight":round(matched_weight,6),
        "boundary_iou_sum":round(iou_sum,6),
        "recall":round(totals["matched_labels"]/labels,4) if labels else 1.0,
        "weighted_recall":round(matched_weight/weight_total,4) if weight_total else 1.0,
        "precision":round(totals["matched_predictions"]/predictions,4) if predictions else (1.0 if not labels else 0.0),
        "top_k_label_recall":round(totals["top_k_matched_labels"]/labels,4) if labels else 1.0,
        "duplicate_prediction_rate":round(totals["duplicate_predictions"]/predictions,4) if predictions else 0.0,
        "false_positive_rate":round(totals["false_positive_count"]/predictions,4) if predictions else 0.0,
        "mean_boundary_iou":round(iou_sum/boundary,4) if boundary else 0.0,
        "event_type_accuracy":round(totals["event_type_correct_count"]/typed,4) if typed else None,
    }


def _case_labels(payload: dict[str,Any]) -> list[dict[str,Any]]:
    rows=payload.get("labels") or []
    if not isinstance(rows,list): raise ValueError("case labels must be a list")
    return [x for x in rows if isinstance(x,dict)]


def evaluate_manifest(manifest_path: Path, baseline: dict[str,Any] | None=None) -> dict[str,Any]:
    manifest_path=Path(manifest_path)
    manifest=_read_json(manifest_path)
    sessions=manifest.get("sessions") or []
    if not isinstance(sessions,list) or not sessions:
        raise ValueError("corpus manifest needs a non-empty sessions list")

    ids=set(); evaluated=[]; event_counts=Counter(); label_counts_by_split=Counter(); session_counts=Counter()
    for index,row in enumerate(sessions):
        if not isinstance(row,dict): raise ValueError(f"session {index+1} must be an object")
        sid=str(row.get("id") or f"session_{index+1}").strip()
        if not sid or sid in ids: raise ValueError(f"duplicate/empty session id: {sid!r}")
        ids.add(sid)
        split=str(row.get("split") or "heldout").strip().lower()
        if split not in _ALLOWED_SPLITS: raise ValueError(f"session {sid} has invalid split {split!r}")
        rel=str(row.get("case") or row.get("path") or "").strip()
        if not rel: raise ValueError(f"session {sid} is missing case path")
        case_path=(manifest_path.parent/rel).resolve()
        if not case_path.exists(): raise FileNotFoundError(case_path)
        payload=_read_json(case_path)
        if not isinstance(payload,dict): raise ValueError(f"session {sid} case must be a JSON object")
        if row.get("top_k") is not None: payload["top_k"]=int(row["top_k"])
        if row.get("max_predictions") is not None: payload["max_predictions"]=int(row["max_predictions"])
        result=evaluate_payload(payload)
        labels=_case_labels(payload)
        for label in labels:
            event=str(label.get("event_type") or "untyped").strip().lower() or "untyped"
            event_counts[event]+=1
        label_counts_by_split[split]+=len(labels); session_counts[split]+=1
        evaluated.append({
            "id":sid,"split":split,"case":rel,
            "metrics":result,
        })

    split_payload={}
    for split in sorted(_ALLOWED_SPLITS):
        rows=[x["metrics"] for x in evaluated if x["split"]==split]
        split_payload[split]={"session_count":len(rows),"metrics":_aggregate(rows) if rows else _aggregate([])}
    overall=_aggregate([x["metrics"] for x in evaluated])

    requirements=manifest.get("release_requirements") if isinstance(manifest.get("release_requirements"),dict) else {}
    min_total=int(requirements.get("min_total_labels",30) or 0)
    min_heldout=int(requirements.get("min_heldout_labels",10) or 0)
    min_heldout_sessions=int(requirements.get("min_heldout_sessions",2) or 0)
    required_types=[str(x).strip().lower() for x in (requirements.get("required_event_types") or []) if str(x).strip()]
    coverage_failures=[]
    if overall["label_count"] < min_total:
        coverage_failures.append(f"corpus has {overall['label_count']} labels; release requirement is {min_total}")
    heldout_labels=int(split_payload["heldout"]["metrics"]["label_count"])
    if heldout_labels < min_heldout:
        coverage_failures.append(f"held-out split has {heldout_labels} labels; release requirement is {min_heldout}")
    if int(split_payload["heldout"]["session_count"]) < min_heldout_sessions:
        coverage_failures.append(f"held-out split has {split_payload['heldout']['session_count']} sessions; release requirement is {min_heldout_sessions}")
    missing=[x for x in required_types if event_counts.get(x,0)<=0]
    if missing: coverage_failures.append("required event types missing from corpus: "+", ".join(missing))

    gate=None
    if baseline:
        base_metrics=baseline
        if isinstance(baseline.get("splits"),dict):
            base_metrics=((baseline.get("splits") or {}).get("heldout") or {}).get("metrics") or {}
        gate=compare_metrics(split_payload["heldout"]["metrics"],base_metrics)

    return {
        "schema_version":1,
        "manifest":manifest_path.name,
        "session_count":len(evaluated),
        "event_type_counts":dict(sorted(event_counts.items())),
        "overall":overall,
        "splits":split_payload,
        "coverage_failures":coverage_failures,
        "regression_gate":gate,
        "release_gate_passed":not coverage_failures and (gate is None or bool(gate.get("passed"))),
        "sessions":evaluated,
    }


def main() -> None:
    parser=argparse.ArgumentParser(description="Evaluate the private Postal AutoClip OSRS golden-VOD corpus")
    parser.add_argument("manifest",type=Path)
    parser.add_argument("--baseline",type=Path,default=None,help="Accepted corpus report or held-out metrics JSON")
    parser.add_argument("--output",type=Path,default=None)
    parser.add_argument("--fail-gate",action="store_true",help="Exit non-zero when corpus coverage/regression gate fails")
    args=parser.parse_args()
    baseline=_read_json(args.baseline) if args.baseline else None
    report=evaluate_manifest(args.manifest,baseline=baseline)
    text=json.dumps(report,indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(text+"\n",encoding="utf-8")
    else:
        print(text)
    if args.fail_gate and not report["release_gate_passed"]:
        raise SystemExit(2)


if __name__=="__main__":
    main()
