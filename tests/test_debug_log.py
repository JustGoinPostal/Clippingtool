from app.debug_log import _redact, debug_filename


def test_debug_redacts_sensitive_values():
    value = {
        "runelite_bridge_token": "postal-local",
        "client_secret": "secret-value",
        "password": "hunter2",
        "safe_setting": "keep-me",
        "nested": {"access_token": "oauth-token", "model": "small"},
    }
    clean = _redact(value)
    assert clean["runelite_bridge_token"] == "<redacted>"
    assert clean["client_secret"] == "<redacted>"
    assert clean["password"] == "<redacted>"
    assert clean["safe_setting"] == "keep-me"
    assert clean["nested"]["access_token"] == "<redacted>"
    assert clean["nested"]["model"] == "small"


def test_debug_filename_is_plain_text():
    assert debug_filename(42).startswith("PostalAutoClip-Debug-job-42-")
    assert debug_filename(42).endswith(".txt")
