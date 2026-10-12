from __future__ import annotations
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from app.config import load_settings
from app.osrs_events import map_events_to_recording
from app.scoring import make_candidates
from app.metadata import make_metadata

s=load_settings()
tx={"segments":[
    {"start":24.0,"end":27.0,"text":"okay opening the chest now"},
    {"start":30.2,"end":33.5,"text":"no way bro twisted bow let's go"},
    {"start":34.0,"end":38.0,"text":"that is actually insane"},
]}
energy=[(float(t), -40.0 if t<29 or t>35 else -18.0) for t in range(0,90,2)]
video=[]
for t in range(0,90,2):
    row={"time":float(t),"visual_change":.02,"chat_change":.01,"ui_change":.01,"center_change":.01,"purple_ratio":.002,"gold_ratio":.002,"red_ratio":.001}
    if 28<=t<=32:
        row.update({"visual_change":.12,"chat_change":.09,"ui_change":.07,"center_change":.11,"purple_ratio":.06,"gold_ratio":.035})
    video.append(row)
raw=[{"event_time":1030.0,"event_type":"loot","confidence":1.0,"payload":{"source":"Chambers of Xeric","total_value":1500000000,"items":[{"id":20997,"name":"Twisted bow","quantity":1,"unique":True}]}}]
events=map_events_to_recording(raw,1000.0,90.0)
cs=make_candidates(tx,energy,90.0,s,video=video,learned={},game_events=events)
assert cs and cs[0]["event_type"] == "raid_reward", cs[:1]
assert cs[0]["score"] == 100.0, cs[0]["score"]
title,desc,tags=make_metadata(cs[0])
assert title and "#OSRSRaids" in tags and "#OSRSDrops" in tags
print("Postal AutoClip v0.3 smoke test: PASS")
print(cs[0]["event_type"], cs[0]["score"], title)
