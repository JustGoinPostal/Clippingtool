from pathlib import Path


def test_dashboard_surfaces_uncertain_publish_state():
    html = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")
    assert "REVIEW REQUIRED" in html
    assert "confirm_duplicate_risk" in html
    assert "Retry Anyway" in html
    assert "AutoClip stopped here to prevent a possible duplicate" in html
