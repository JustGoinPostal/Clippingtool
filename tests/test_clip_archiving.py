from app import api


def test_clip_list_excludes_archived(monkeypatch):
    seen = {}

    def fake_q(sql, args=(), one=False):
        seen["sql"] = sql
        seen["args"] = args
        return []

    monkeypatch.setattr(api.db, "q", fake_q)
    assert api.clips() == []
    assert "clips.status!='archived'" in seen["sql"]


def test_archive_single_clip_keeps_related_data(monkeypatch):
    calls = []

    def fake_q(sql, args=(), one=False):
        return {"id": 7, "status": "favorite"} if one else []

    def fake_exec(sql, args=()):
        calls.append((sql, args))
        return 0

    monkeypatch.setattr(api.db, "q", fake_q)
    monkeypatch.setattr(api.db, "exec_sql", fake_exec)

    result = api.archive_clip(7)
    assert result == {"ok": True, "clip_id": 7, "previous_status": "favorite"}
    assert calls == [("UPDATE clips SET status='archived' WHERE id=?", (7,))]


def test_archive_all_clips(monkeypatch):
    calls = []

    def fake_q(sql, args=(), one=False):
        return {"n": 12} if one else []

    def fake_exec(sql, args=()):
        calls.append((sql, args))
        return 0

    monkeypatch.setattr(api.db, "q", fake_q)
    monkeypatch.setattr(api.db, "exec_sql", fake_exec)

    result = api.archive_all_clips()
    assert result == {"ok": True, "archived": 12}
    assert calls == [("UPDATE clips SET status='archived' WHERE status!='archived'", ())]
