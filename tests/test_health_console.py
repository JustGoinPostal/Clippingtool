from pathlib import Path


def test_health_console_surfaces_trust_states_and_safe_recovery():
    text=Path("app/static/health.html").read_text(encoding="utf-8")
    assert "/api/game-events/recent" in text
    assert "/api/publishing/status" in text
    assert "/api/jobs" in text
    assert "/api/clips" in text
    assert "QA PASS" not in text  # status is populated from real render data, not hard-coded success
    assert "Re-render + QA" in text
    assert "confirm_duplicate_risk" in text
    assert "Retry Anyway" in text
    assert "RuneLite companion" in text
    assert "Publishing attention" in text
