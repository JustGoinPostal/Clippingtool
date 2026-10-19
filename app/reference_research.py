from __future__ import annotations

import argparse
import json
from pathlib import Path

from .public_reference import CATALOG_PATH, load_catalog, save_catalog, summarize_references, upsert_reference
from .youtube_reference_api import fetch_video_metadata, search_creative_commons_osrs


def _load_seed(path: Path) -> list[dict]:
    payload=json.loads(path.read_text(encoding="utf-8"))
    rows=payload.get("references") if isinstance(payload,dict) else payload
    return [dict(x) for x in (rows or []) if isinstance(x,dict)]


def import_seed(path: Path, *, catalog: Path=CATALOG_PATH) -> int:
    count=0
    for row in _load_seed(path):
        upsert_reference(row,catalog); count+=1
    return count


def main(argv: list[str] | None=None) -> int:
    parser=argparse.ArgumentParser(description="Postal AutoClip public OSRS reference research")
    parser.add_argument("--catalog",type=Path,default=CATALOG_PATH)
    sub=parser.add_subparsers(dest="cmd",required=True)

    seed=sub.add_parser("seed",help="Import metadata-only seed references")
    seed.add_argument("path",type=Path)

    fetch=sub.add_parser("fetch",help="Fetch official YouTube public metadata for one or more video URLs/IDs")
    fetch.add_argument("videos",nargs="+")
    fetch.add_argument("--category",default="other")

    cc=sub.add_parser("search-cc",help="Search official YouTube API for Creative Commons OSRS references")
    cc.add_argument("--query",default="Old School RuneScape")
    cc.add_argument("--category",default="other")
    cc.add_argument("--max-results",type=int,default=10)

    sub.add_parser("report",help="Print aggregate metadata/structural reference statistics")

    args=parser.parse_args(argv)
    catalog: Path=args.catalog
    if args.cmd=="seed":
        n=import_seed(args.path,catalog=catalog)
        print(json.dumps({"imported":n,"catalog":str(catalog)},indent=2))
        return 0
    if args.cmd=="fetch":
        rows=fetch_video_metadata(args.videos,category=args.category)
        for row in rows: upsert_reference(row,catalog)
        print(json.dumps({"imported":len(rows),"references":rows},indent=2))
        return 0
    if args.cmd=="search-cc":
        rows=search_creative_commons_osrs(args.query,max_results=args.max_results,category=args.category)
        for row in rows: upsert_reference(row,catalog)
        print(json.dumps({"imported":len(rows),"references":rows},indent=2))
        return 0
    if args.cmd=="report":
        print(json.dumps(summarize_references(load_catalog(catalog)),indent=2))
        return 0
    return 2


if __name__=="__main__":
    raise SystemExit(main())
