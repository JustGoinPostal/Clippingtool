from pathlib import Path

import pytest

from app import public_reference
from app.youtube_reference_api import parse_iso8601_duration, _selected_video_metadata


def test_parse_youtube_video_id_supports_watch_shorts_and_youtu_be():
    vid="abcdefghijk"
    assert public_reference.parse_youtube_video_id(vid)==vid
    assert public_reference.parse_youtube_video_id(f"https://www.youtube.com/watch?v={vid}&t=20")==vid
    assert public_reference.parse_youtube_video_id(f"https://youtube.com/shorts/{vid}")==vid
    assert public_reference.parse_youtube_video_id(f"https://youtu.be/{vid}?si=test")==vid
    with pytest.raises(ValueError):
        public_reference.parse_youtube_video_id("https://example.com/not-youtube")


def test_standard_license_metadata_cannot_carry_structural_annotations():
    with pytest.raises(ValueError, match="timing/edit annotations"):
        public_reference.normalize_reference({
            "video_id":"abcdefghijk",
            "source_mode":"metadata_only",
            "license":"youtube",
            "category":"pvp",
            "structural":{"hook_time":1.0,"payoff_time":10.0},
        })


def test_creative_commons_and_permission_can_carry_structural_annotations():
    cc=public_reference.normalize_reference({
        "video_id":"abcdefghijk",
        "source_mode":"creative_commons",
        "license":"creativeCommon",
        "category":"raid",
        "duration_seconds":30,
        "structural":{"hook_time":0.8,"payoff_time":21,"reaction_end":27,"uses_zoom":True},
    })
    assert cc["structural"]["payoff_time"]==21.0
    with pytest.raises(ValueError, match="permission_confirmed"):
        public_reference.normalize_reference({
            "video_id":"bcdefghijkl","source_mode":"permission","license":"youtube","category":"pvp"
        })
    with pytest.raises(ValueError, match="rights_basis"):
        public_reference.normalize_reference({
            "video_id":"bcdefghijkl","source_mode":"permission","permission_confirmed":True,
            "license":"youtube","category":"pvp"
        })
    permitted=public_reference.normalize_reference({
        "video_id":"bcdefghijkl","source_mode":"permission","permission_confirmed":True,
        "rights_basis":"Creator email dated 2026-10-19", "license":"youtube","category":"pvp",
        "duration_seconds":20,"structural":{"hook_time":0.5,"payoff_time":13},
    })
    assert permitted["source_mode"]=="permission"
    assert permitted["rights_basis"].startswith("Creator email")


def test_catalog_is_atomic_and_unique(tmp_path: Path):
    path=tmp_path/"catalog.json"
    first=public_reference.upsert_reference({
        "video_id":"abcdefghijk","source_mode":"metadata_only","license":"youtube","category":"guide",
        "creator":"Creator","title":"A useful title","view_count":1000,
    },path)
    assert first["video_id"]=="abcdefghijk"
    updated=public_reference.upsert_reference({
        "video_id":"abcdefghijk","source_mode":"metadata_only","license":"youtube","category":"guide",
        "creator":"Creator","title":"Updated title","view_count":2000,
    },path)
    assert updated["view_count"]==2000
    rows=public_reference.load_catalog(path)
    assert len(rows)==1
    assert rows[0]["title"]=="Updated title"
    assert not path.with_suffix(".tmp").exists()


def test_summary_separates_metadata_from_permitted_structural_evidence():
    rows=[
        {
            "video_id":"abcdefghijk","source_mode":"metadata_only","license":"youtube","category":"pvp",
            "title":"PK title","duration_seconds":20,"view_count":1000,"like_count":100,
        },
        {
            "video_id":"bcdefghijkl","source_mode":"creative_commons","license":"creativeCommon","category":"raid",
            "title":"Raid title","duration_seconds":40,"view_count":3000,"like_count":300,
            "structural":{"hook_time":1,"payoff_time":30,"reaction_end":36},
        },
    ]
    report=public_reference.summarize_references(rows)
    assert report["reference_count"]==2
    assert report["metadata_only_count"]==1
    assert report["structural_reference_count"]==1
    assert report["metadata"]["median_duration_seconds"]==30.0
    assert report["structural"]["median_hook_seconds"]==1.0
    assert report["structural"]["median_payoff_ratio"]==0.75
    assert report["structural"]["median_reaction_tail_seconds"]==6.0


def test_youtube_api_selection_keeps_only_public_fields_and_license():
    item={
        "id":"abcdefghijk",
        "snippet":{
            "channelTitle":"Creator","title":"Title","publishedAt":"2026-01-01T00:00:00Z",
            "description":"THIS MUST NOT BE STORED","tags":["also","not","stored"],
        },
        "statistics":{"viewCount":"1234","likeCount":"56","commentCount":"99"},
        "contentDetails":{"duration":"PT1M2.5S"},
        "status":{"license":"creativeCommon","embeddable":True},
    }
    row=_selected_video_metadata(item,category="pvm",source_mode="creative_commons")
    assert row["duration_seconds"]==62.5
    assert row["license"]=="creativeCommon"
    assert row["source_mode"]=="creative_commons"
    assert "description" not in row
    assert "tags" not in row
    assert "commentCount" not in row


def test_iso8601_duration_parser():
    assert parse_iso8601_duration("PT1M2S")==62.0
    assert parse_iso8601_duration("PT2H3M4.5S")==7384.5
    assert parse_iso8601_duration("bad")==0.0
