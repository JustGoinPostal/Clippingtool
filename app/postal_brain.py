from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx

from .config import ROOT

BRAIN_DIR = ROOT / "data" / "postal_brain"
EVENT_LOG = BRAIN_DIR / "events.jsonl"
AI_LOG = BRAIN_DIR / "ai_calls.jsonl"


@dataclass(slots=True)
class BrainEvent:
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = "postal-autoclip"
    priority: str = "normal"
    stream_id: str = ""
    tags: list[str] = field(default_factory=list)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)

    def normalized(self) -> dict[str, Any]:
        priority = self.priority.lower().strip()
        if priority not in {"debug", "normal", "high", "critical"}:
            priority = "normal"
        data = asdict(self)
        data["priority"] = priority
        data["kind"] = str(self.kind or "event")[:120]
        data["source"] = str(self.source or "unknown")[:120]
        data["stream_id"] = str(self.stream_id or "")[:160]
        data["tags"] = [str(tag)[:80] for tag in self.tags[:24]]
        return data


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def emit_event(
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    source: str = "postal-autoclip",
    priority: str = "normal",
    stream_id: str = "",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    event = BrainEvent(
        kind=kind,
        payload=payload or {},
        source=source,
        priority=priority,
        stream_id=stream_id,
        tags=tags or [],
    ).normalized()
    _append_jsonl(EVENT_LOG, event)
    return event


def recent_events(limit: int = 100) -> list[dict[str, Any]]:
    limit = max(1, min(1000, int(limit)))
    if not EVENT_LOG.exists():
        return []
    lines = EVENT_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    rows: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
        except json.JSONDecodeError:
            continue
    return rows


def _extract_output_text(response: dict[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    pieces: list[str] = []
    for item in response.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            if content.get("type") in {"output_text", "text"}:
                text = content.get("text")
                if isinstance(text, str):
                    pieces.append(text)
    return "\n".join(pieces).strip()


def _parse_json_text(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.lower().startswith("json"):
            candidate = candidate[4:].lstrip()
    try:
        value = json.loads(candidate)
        return value if isinstance(value, dict) else {"result": value}
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(candidate[start : end + 1])
                return value if isinstance(value, dict) else {"result": value}
            except json.JSONDecodeError:
                pass
    return {"summary": candidate, "parse_error": True}


class PostalBrain:
    """Small, dependency-light OpenAI Responses API client for Postal Creator OS.

    Secrets are intentionally read only from environment variables. The class is
    safe to instantiate when OpenAI is not configured; local event logging still
    works and callers can degrade to existing heuristics.
    """

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.model = os.getenv("POSTAL_OPENAI_MODEL", "gpt-5").strip() or "gpt-5"
        self.base_url = os.getenv("POSTAL_OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.enabled = os.getenv("POSTAL_OPENAI_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
        self.timeout_seconds = float(os.getenv("POSTAL_OPENAI_TIMEOUT_SECONDS", "90"))
        self.max_live_calls_per_minute = max(1, int(os.getenv("POSTAL_OPENAI_MAX_CALLS_PER_MINUTE", "12")))
        self._call_times: list[float] = []
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.api_key)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "configured": self.configured,
            "model": self.model,
            "base_url": self.base_url,
            "event_log": str(EVENT_LOG),
            "ai_log": str(AI_LOG),
            "max_live_calls_per_minute": self.max_live_calls_per_minute,
        }

    def _rate_limit(self) -> None:
        now = time.time()
        with self._lock:
            self._call_times = [stamp for stamp in self._call_times if now - stamp < 60]
            if len(self._call_times) >= self.max_live_calls_per_minute:
                wait_for = 60 - (now - self._call_times[0])
                if wait_for > 0:
                    time.sleep(min(wait_for, 60))
                now = time.time()
                self._call_times = [stamp for stamp in self._call_times if now - stamp < 60]
            self._call_times.append(time.time())

    def _response(self, *, instructions: str, input_text: str, metadata: dict[str, str] | None = None) -> dict[str, Any]:
        if not self.configured:
            raise RuntimeError("Postal Brain OpenAI access is not configured. Set OPENAI_API_KEY or disable OpenAI explicitly.")
        self._rate_limit()
        started = time.time()
        payload: dict[str, Any] = {
            "model": self.model,
            "instructions": instructions,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": input_text}],
                }
            ],
        }
        if metadata:
            payload["metadata"] = {str(k)[:64]: str(v)[:512] for k, v in metadata.items()}
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    f"{self.base_url}/responses",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            response.raise_for_status()
            data = response.json()
            usage = data.get("usage") if isinstance(data, dict) else None
            _append_jsonl(
                AI_LOG,
                {
                    "created_at": time.time(),
                    "model": self.model,
                    "response_id": data.get("id", "") if isinstance(data, dict) else "",
                    "elapsed_seconds": round(time.time() - started, 3),
                    "usage": usage if isinstance(usage, dict) else {},
                    "ok": True,
                },
            )
            return data
        except Exception as exc:
            _append_jsonl(
                AI_LOG,
                {
                    "created_at": time.time(),
                    "model": self.model,
                    "elapsed_seconds": round(time.time() - started, 3),
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}"[:1000],
                },
            )
            raise

    def ask(self, question: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        question = str(question or "").strip()
        if not question:
            raise ValueError("question is required")
        context_text = json.dumps(context or {}, ensure_ascii=False, indent=2)
        response = self._response(
            instructions=(
                "You are Postal Brain, the reasoning layer for Postal Creator OS. "
                "Be concise, operational, and specific. Prioritize actions that reduce manual creator work. "
                "Never invent platform metrics or claim an action was performed unless the supplied context says it was performed."
            ),
            input_text=f"QUESTION:\n{question}\n\nCONTEXT:\n{context_text}",
            metadata={"postal_purpose": "ask"},
        )
        return {
            "text": _extract_output_text(response),
            "response_id": response.get("id", ""),
            "model": self.model,
            "usage": response.get("usage") or {},
        }

    def analyze_event(self, event: dict[str, Any]) -> dict[str, Any]:
        response = self._response(
            instructions=(
                "You are Postal Brain analyzing one creator-system event. Return JSON only. "
                "Required keys: summary, importance (0-100 integer), notify_now (boolean), "
                "recommended_action (string), content_opportunity (boolean), reason (string). "
                "Only recommend interruption when the event is genuinely actionable, unusually valuable, or a system failure."
            ),
            input_text=json.dumps(event, ensure_ascii=False, indent=2),
            metadata={"postal_purpose": "event_analysis", "event_kind": str(event.get("kind") or "event")[:64]},
        )
        parsed = _parse_json_text(_extract_output_text(response))
        parsed["response_id"] = response.get("id", "")
        parsed["model"] = self.model
        parsed["usage"] = response.get("usage") or {}
        return parsed

    def build_digest(self, events: list[dict[str, Any]], *, label: str = "stream") -> dict[str, Any]:
        response = self._response(
            instructions=(
                "You are Postal Brain producing a creator operations digest. Return JSON only. "
                "Required keys: headline, summary, wins (array), problems (array), best_content_moments (array), "
                "next_actions (array), notify_text (string). Keep next_actions to the highest-value actions only."
            ),
            input_text=json.dumps({"label": label, "events": events[-500:]}, ensure_ascii=False),
            metadata={"postal_purpose": "digest", "digest_label": label[:64]},
        )
        parsed = _parse_json_text(_extract_output_text(response))
        parsed["response_id"] = response.get("id", "")
        parsed["model"] = self.model
        parsed["usage"] = response.get("usage") or {}
        return parsed


brain = PostalBrain()
