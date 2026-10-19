import threading
import time

import pytest

from app import pipeline


def test_same_clip_rejects_overlapping_render(monkeypatch):
    clip_id=987654
    with pipeline._render_lock_guard:
        pipeline._render_locks.pop(clip_id,None)

    entered=threading.Event()
    release=threading.Event()
    result=[]

    def fake_render(cid,variant=None,finalize_status=True):
        entered.set()
        assert release.wait(3)
        return {"clip_id":cid,"variant":variant}

    monkeypatch.setattr(pipeline,"_render_clip_id_unlocked",fake_render)

    def first():
        result.append(pipeline.render_clip_id(clip_id,"short"))

    thread=threading.Thread(target=first)
    thread.start()
    assert entered.wait(2)

    with pytest.raises(pipeline.RenderBusyError,match="already rendering"):
        pipeline.render_clip_id(clip_id,"medium")

    release.set()
    thread.join(3)
    assert not thread.is_alive()
    assert result==[{"clip_id":clip_id,"variant":"short"}]


def test_render_lock_is_per_clip(monkeypatch):
    calls=[]

    def fake_render(cid,variant=None,finalize_status=True):
        calls.append((cid,variant))
        time.sleep(0.02)
        return {"clip_id":cid}

    monkeypatch.setattr(pipeline,"_render_clip_id_unlocked",fake_render)
    with pipeline._render_lock_guard:
        pipeline._render_locks.pop(111,None)
        pipeline._render_locks.pop(222,None)

    a=threading.Thread(target=pipeline.render_clip_id,args=(111,"short"))
    b=threading.Thread(target=pipeline.render_clip_id,args=(222,"short"))
    a.start(); b.start(); a.join(2); b.join(2)

    assert sorted(calls)==[(111,"short"),(222,"short")]
