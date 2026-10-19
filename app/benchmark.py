from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MomentLabel:
    id: str
    start: float
    end: float
    event_type: str = ""
    weight: float = 1.0

    @property
    def midpoint(self) -> float:
        return (self.start + self.end) / 2.0


@dataclass(frozen=True)
class Prediction:
    index: int
    start: float
    end: float
    score: float
    event_type: str = ""


def _window(row: dict[str, Any], default_radius: float = 3.0) -> tuple[float, float]:
    if row.get("start") is not None and row.get("end") is not None:
        start = float(row["start"])
        end = float(row["end"])
    elif row.get("time") is not None:
        radius = max(0.05, float(row.get("tolerance_seconds", default_radius)))
        t = float(row["time"])
        start, end = t - radius, t + radius
    else:
        raise ValueError("Benchmark rows need start/end or time")
    if end <= start:
        raise ValueError(f"Invalid benchmark window: {start} -> {end}")
    return start, end


def normalize_labels(rows: list[dict[str, Any]]) -> list[MomentLabel]:
    out: list[MomentLabel] = []
    for i, row in enumerate(rows):
        start, end = _window(row)
        out.append(MomentLabel(
            id=str(row.get("id") or f"moment_{i + 1}"),
            start=start,
            end=end,
            event_type=str(row.get("event_type") or "").strip().lower(),
            weight=max(0.0, float(row.get("weight", row.get("importance", 1.0)) or 1.0)),
        ))
    return out


def normalize_predictions(rows: list[dict[str, Any]]) -> list[Prediction]:
    out: list[Prediction] = []
    for i, row in enumerate(rows):
        start, end = _window(row)
        out.append(Prediction(
            index=i,
            start=start,
            end=end,
            score=float(row.get("score", 0.0) or 0.0),
            event_type=str(row.get("event_type") or "").strip().lower(),
        ))
    return sorted(out, key=lambda p: (-p.score, p.index))


def _intersection(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def _iou(label: MomentLabel, prediction: Prediction) -> float:
    inter = _intersection(label.start, label.end, prediction.start, prediction.end)
    union = max(label.end, prediction.end) - min(label.start, prediction.start)
    return inter / union if union > 0 else 0.0


def _label_coverage(label: MomentLabel, prediction: Prediction) -> float:
    inter = _intersection(label.start, label.end, prediction.start, prediction.end)
    return inter / max(0.001, label.end - label.start)


def _captures(label: MomentLabel, prediction: Prediction, min_label_coverage: float) -> bool:
    # A clip can successfully find a brief exact event even when the final clip is
    # intentionally much longer than the annotated event window. Boundary quality is
    # scored separately so recall is not confused with edit tightness.
    midpoint_inside = prediction.start <= label.midpoint <= prediction.end
    return midpoint_inside or _label_coverage(label, prediction) >= min_label_coverage


def evaluate_predictions(
    labels: list[dict[str, Any]] | list[MomentLabel],
    predictions: list[dict[str, Any]] | list[Prediction],
    *,
    top_k: int = 3,
    max_predictions: int | None = None,
    min_label_coverage: float = 0.50,
) -> dict[str, Any]:
    normalized_labels = labels if labels and isinstance(labels[0], MomentLabel) else normalize_labels(labels)  # type: ignore[index]
    normalized_predictions = predictions if predictions and isinstance(predictions[0], Prediction) else normalize_predictions(predictions)  # type: ignore[index]
    normalized_labels = list(normalized_labels)  # type: ignore[arg-type]
    normalized_predictions = list(normalized_predictions)  # type: ignore[arg-type]
    if max_predictions is not None:
        normalized_predictions = normalized_predictions[:max(0, int(max_predictions))]

    matched_labels: set[int] = set()
    matched_predictions: set[int] = set()
    pairs: list[dict[str, Any]] = []

    # Greedy in score order reflects what a creator actually sees first. A prediction
    # is assigned to only one truth label; overlapping extra clips become duplicates.
    for rank, pred in enumerate(normalized_predictions, start=1):
        candidates = []
        for li, label in enumerate(normalized_labels):
            if li in matched_labels or not _captures(label, pred, min_label_coverage):
                continue
            coverage = _label_coverage(label, pred)
            iou = _iou(label, pred)
            midpoint_distance = abs(((pred.start + pred.end) / 2.0) - label.midpoint)
            candidates.append((coverage, iou, -midpoint_distance, li, label))
        if not candidates:
            continue
        _, iou, _, li, label = max(candidates)
        matched_labels.add(li)
        matched_predictions.add(pred.index)
        pairs.append({
            "label_id": label.id,
            "prediction_index": pred.index,
            "rank": rank,
            "score": pred.score,
            "label_coverage": round(_label_coverage(label, pred), 4),
            "boundary_iou": round(iou, 4),
            "start_error_seconds": round(abs(pred.start - label.start), 3),
            "end_error_seconds": round(abs(pred.end - label.end), 3),
            "event_type_correct": bool(label.event_type and pred.event_type and label.event_type == pred.event_type),
            "label_event_type": label.event_type,
            "predicted_event_type": pred.event_type,
        })

    total_labels = len(normalized_labels)
    total_predictions = len(normalized_predictions)
    weight_total = sum(x.weight for x in normalized_labels)
    matched_weight = sum(normalized_labels[i].weight for i in matched_labels)
    top_k_labels: set[int] = set()
    for pred in normalized_predictions[:max(0, int(top_k))]:
        for li, label in enumerate(normalized_labels):
            if _captures(label, pred, min_label_coverage):
                top_k_labels.add(li)

    duplicate_predictions = 0
    for pred in normalized_predictions:
        captures = sum(1 for label in normalized_labels if _captures(label, pred, min_label_coverage))
        if pred.index not in matched_predictions and captures:
            duplicate_predictions += 1

    boundary_ious = [float(p["boundary_iou"]) for p in pairs]
    typed_pairs = [p for p in pairs if p["label_event_type"] and p["predicted_event_type"]]
    false_positive_count = max(0, total_predictions - len(matched_predictions) - duplicate_predictions)

    missed = [label.id for i, label in enumerate(normalized_labels) if i not in matched_labels]
    unmatched = [p.index for p in normalized_predictions if p.index not in matched_predictions]

    return {
        "label_count": total_labels,
        "prediction_count": total_predictions,
        "matched_labels": len(matched_labels),
        "matched_predictions": len(matched_predictions),
        "recall": round(len(matched_labels) / total_labels, 4) if total_labels else 1.0,
        "weighted_recall": round(matched_weight / weight_total, 4) if weight_total else 1.0,
        "precision": round(len(matched_predictions) / total_predictions, 4) if total_predictions else (1.0 if not total_labels else 0.0),
        "top_k": int(top_k),
        "top_k_label_recall": round(len(top_k_labels) / total_labels, 4) if total_labels else 1.0,
        "duplicate_prediction_rate": round(duplicate_predictions / total_predictions, 4) if total_predictions else 0.0,
        "false_positive_rate": round(false_positive_count / total_predictions, 4) if total_predictions else 0.0,
        "mean_boundary_iou": round(sum(boundary_ious) / len(boundary_ious), 4) if boundary_ious else 0.0,
        "event_type_accuracy": round(sum(1 for p in typed_pairs if p["event_type_correct"]) / len(typed_pairs), 4) if typed_pairs else None,
        "missed_label_ids": missed,
        "unmatched_prediction_indexes": unmatched,
        "matches": pairs,
    }


def evaluate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return evaluate_predictions(
        payload.get("labels") or [],
        payload.get("predictions") or payload.get("clips") or [],
        top_k=int(payload.get("top_k", 3) or 3),
        max_predictions=payload.get("max_predictions"),
        min_label_coverage=float(payload.get("min_label_coverage", 0.50) or 0.50),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Postal AutoClip predictions against labeled OSRS moments")
    parser.add_argument("input", type=Path, help="JSON containing labels and predictions/clips")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON result path")
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    result = evaluate_payload(payload)
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
