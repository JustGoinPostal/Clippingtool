from datetime import datetime
from types import SimpleNamespace

import app.learning as learning
import app.platform_insights as platform_insights
from app.distribution import _scheduled_time


def test_synchronized_crosspost_never_rolls_to_next_date():
    base_dt=datetime.now().astimezone().replace(hour=23,minute=50,second=0,microsecond=0)
    base=base_dt.timestamp()
    scheduled=_scheduled_time(base,40,True)
    assert datetime.fromtimestamp(scheduled).astimezone().date()==base_dt.date()
    assert scheduled==base


def test_independent_schedule_can_roll_dates():
    base_dt=datetime.now().astimezone().replace(hour=23,minute=50,second=0,microsecond=0)
    base=base_dt.timestamp()
    scheduled=_scheduled_time(base,40,False)
    assert scheduled>base


def test_platform_variant_requires_enough_history(monkeypatch):
    monkeypatch.setattr(platform_insights,"load_settings",lambda:SimpleNamespace(platform_variant_min_samples=3))
    monkeypatch.setattr(platform_insights,"variant_stats",lambda platform:{
        "short":{"posts":2,"avg_score":99,"views":100000},
        "medium":{"posts":4,"avg_score":82,"views":50000},
    })
    assert platform_insights.choose_platform_variant("tiktok",["short","medium"],"short")=="medium"


def test_platform_variant_falls_back_without_evidence(monkeypatch):
    monkeypatch.setattr(platform_insights,"load_settings",lambda:SimpleNamespace(platform_variant_min_samples=3))
    monkeypatch.setattr(platform_insights,"variant_stats",lambda platform:{"short":{"posts":1,"avg_score":99,"views":1000}})
    assert platform_insights.choose_platform_variant("youtube",["short","medium"],"medium")=="medium"


def test_platform_fit_uses_platform_audience_signal(monkeypatch):
    profile={k:0.0 for k in learning.FEATURE_KEYS}; profile["keyword"]=4.0
    monkeypatch.setattr(learning,"audience_profile",lambda platform=None:profile)
    monkeypatch.setattr(learning,"load_settings",lambda:SimpleNamespace(analytics_learning_weight=0.35))
    score=learning.platform_fit_score({"keyword":1.0},80,"tiktok")
    assert score>80
    assert score<=100
