from __future__ import annotations

import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import load_settings

BASE = "http://127.0.0.1:8787"
OLD_TEST_TIME = 946684800.0  # 2000-01-01 UTC; cannot overlap modern OBS recordings.


def _json(url: str, method: str = "GET", payload: dict | None = None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(
        BASE + url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=4) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    settings = load_settings()
    print("Postal AutoClip RuneLite bridge self-test")
    print("========================================")

    try:
        status = _json("/api/status")
    except (HTTPError, URLError, TimeoutError) as exc:
        print(f"FAIL: AutoClip is not reachable at {BASE}: {exc}")
        return 2

    print(f"AutoClip v{status.get('version', '?')} reachable")
    if not settings.runelite_bridge_enabled:
        print("FAIL: runelite_bridge_enabled is false in config.json")
        return 3

    marker = f"postal-selftest-{int(time.time())}"
    events = [
        {
            "event_time": OLD_TEST_TIME,
            "event_type": "self_test_big_hit",
            "confidence": 0.01,
            "payload": {"marker": marker, "amount": 42, "attributed_to_local": True},
        },
        {
            "event_time": OLD_TEST_TIME + 1,
            "event_type": "self_test_big_hit_taken",
            "confidence": 0.01,
            "payload": {"marker": marker, "amount": 51, "target_local": True},
        },
        {
            "event_time": OLD_TEST_TIME + 2,
            "event_type": "self_test_pvp_kill",
            "confidence": 0.01,
            "payload": {"marker": marker, "name": "SelfTestOpponent", "attributed_to_local": True},
        },
        {
            "event_time": OLD_TEST_TIME + 3,
            "event_type": "self_test_loot",
            "confidence": 0.01,
            "payload": {
                "marker": marker,
                "source": "Self Test",
                "total_value": 123456,
                "items": [{"id": 4151, "name": "Abyssal whip", "quantity": 1}],
            },
        },
    ]

    try:
        result = _json(
            "/api/game-events/batch",
            method="POST",
            payload={"token": settings.runelite_bridge_token, "events": events},
        )
    except HTTPError as exc:
        text = exc.read().decode("utf-8", "replace")
        print(f"FAIL: bridge rejected the test: HTTP {exc.code} {text}")
        return 4
    except (URLError, TimeoutError) as exc:
        print(f"FAIL: could not send bridge events: {exc}")
        return 5

    if int(result.get("count", 0)) != len(events):
        print(f"FAIL: expected {len(events)} stored events, got {result}")
        return 6

    recent = _json("/api/game-events/recent?limit=250")
    matched = []
    for row in recent:
        try:
            payload = json.loads(row.get("payload_json") or "{}")
        except Exception:
            payload = {}
        if payload.get("marker") == marker:
            matched.append(row)

    if len(matched) != len(events):
        print(f"FAIL: wrote {len(events)} events but only read back {len(matched)}")
        return 7

    print(f"PASS: API accepted and read back all {len(events)} synthetic events")
    print("PASS: test timestamps are fixed to 2000-01-01, so they cannot affect modern clip scoring")
    print("Next: launch the RuneLite companion and verify a live bridge_heartbeat in /static/runelite.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
