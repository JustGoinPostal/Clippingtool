from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

# Higher is better for these metrics. A current run may fall only this far below
# the accepted baseline before the benchmark gate blocks a tuning change.
HIGHER_IS_BETTER = {
    "recall": 0.02,
    "weighted_recall": 0.015,
    "precision": 0.03,
    "top_k_label_recall": 0.02,
    "mean_boundary_iou": 0.04,
    "event_type_accuracy": 0.03,
}

# Lower is better. The current run may increase only this far over baseline.
LOWER_IS_BETTER = {
    "duplicate_prediction_rate": 0.02,
    "false_positive_rate": 0.03,
}

# These floors are intentionally conservative bootstrap safeguards. Once the real
# golden corpus is large enough, the accepted baseline becomes the stronger gate.
DEFAULT_FLOORS = {
    "weighted_recall": 0.70,
    "precision": 0.45,
    "top_k_label_recall": 0.45,
}
DEFAULT_CEILINGS = {
    "duplicate_prediction_rate": 0.35,
    "false_positive_rate": 0.40,
}


@dataclass(frozen=True)
class GateFailure:
    metric: str
    current: float | None
    baseline: float | None
    rule: str


def _number(payload: dict[str,Any], key: str) -> float | None:
    raw=payload.get(key)
    if raw is None: return None
    try: return float(raw)
    except Exception: return None


def compare_metrics(
    current: dict[str,Any],
    baseline: dict[str,Any] | None = None,
    *,
    floors: dict[str,float] | None = None,
    ceilings: dict[str,float] | None = None,
    higher_tolerance: dict[str,float] | None = None,
    lower_tolerance: dict[str,float] | None = None,
) -> dict[str,Any]:
    """Compare one benchmark result against absolute safety floors and a baseline."""
    baseline=baseline or {}
    floors={**DEFAULT_FLOORS,**(floors or {})}
    ceilings={**DEFAULT_CEILINGS,**(ceilings or {})}
    higher={**HIGHER_IS_BETTER,**(higher_tolerance or {})}
    lower={**LOWER_IS_BETTER,**(lower_tolerance or {})}
    failures:list[GateFailure]=[]

    label_count=int(current.get("label_count") or 0)
    prediction_count=int(current.get("prediction_count") or 0)
    if label_count <= 0:
        failures.append(GateFailure("label_count",float(label_count),None,"benchmark must contain at least one labeled moment"))
    if prediction_count <= 0 and label_count > 0:
        failures.append(GateFailure("prediction_count",float(prediction_count),None,"detector produced no candidate clips"))

    for metric,floor in floors.items():
        value=_number(current,metric)
        if value is None:
            failures.append(GateFailure(metric,None,_number(baseline,metric),f"missing required metric; floor={floor:.4f}"))
        elif value < float(floor):
            failures.append(GateFailure(metric,value,_number(baseline,metric),f"below absolute floor {float(floor):.4f}"))

    for metric,ceiling in ceilings.items():
        value=_number(current,metric)
        if value is None:
            failures.append(GateFailure(metric,None,_number(baseline,metric),f"missing required metric; ceiling={ceiling:.4f}"))
        elif value > float(ceiling):
            failures.append(GateFailure(metric,value,_number(baseline,metric),f"above absolute ceiling {float(ceiling):.4f}"))

    for metric,tolerance in higher.items():
        now=_number(current,metric); old=_number(baseline,metric)
        if now is None or old is None: continue
        if now < old-float(tolerance):
            failures.append(GateFailure(metric,now,old,f"regressed more than {float(tolerance):.4f} from baseline"))

    for metric,tolerance in lower.items():
        now=_number(current,metric); old=_number(baseline,metric)
        if now is None or old is None: continue
        if now > old+float(tolerance):
            failures.append(GateFailure(metric,now,old,f"worsened more than {float(tolerance):.4f} from baseline"))

    return {
        "passed":not failures,
        "label_count":label_count,
        "prediction_count":prediction_count,
        "failures":[asdict(x) for x in failures],
        "current":{k:current.get(k) for k in sorted(set(higher)|set(lower)|set(floors)|set(ceilings))},
        "baseline":{k:baseline.get(k) for k in sorted(set(higher)|set(lower)|set(floors)|set(ceilings))} if baseline else {},
    }


def main() -> None:
    parser=argparse.ArgumentParser(description="Fail a Postal AutoClip tuning change when OSRS benchmark metrics regress")
    parser.add_argument("current",type=Path,help="JSON output from app.benchmark for the candidate build")
    parser.add_argument("--baseline",type=Path,default=None,help="Accepted benchmark JSON from the current production baseline")
    parser.add_argument("--output",type=Path,default=None,help="Optional gate report JSON")
    args=parser.parse_args()
    current=json.loads(args.current.read_text(encoding="utf-8"))
    baseline=json.loads(args.baseline.read_text(encoding="utf-8")) if args.baseline else {}
    report=compare_metrics(current,baseline)
    text=json.dumps(report,indent=2)
    if args.output: args.output.write_text(text+"\n",encoding="utf-8")
    else: print(text)
    raise SystemExit(0 if report["passed"] else 2)


if __name__=="__main__":
    main()
