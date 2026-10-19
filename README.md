# Postal AutoClip

Local-first automatic stream VOD clipping, vertical editing, safe social distribution, and audience learning for OSRS creators.

## Product status

The current production-hardening branch is intentionally **pre-v1.0**. The product has cross-platform automated tests, finished-media QA, crash-safe publishing protections, RuneLite-assisted OSRS moment detection, and a private golden-VOD benchmark workflow, but creator-ready v1.0 remains blocked on a real held-out OSRS benchmark corpus and a long real-world soak test.

## Main commands

```powershell
postal-autoclip
postal-autoclip-labeler
postal-autoclip-reference report
```

- `postal-autoclip` starts the main local app.
- `postal-autoclip-labeler` starts Golden VOD Lab for private owned/permitted benchmark labeling.
- `postal-autoclip-reference` manages the rights-aware public OSRS reference catalog used for research.

## Public OSRS reference research

Popular public OSRS YouTube videos are useful market references, but public availability is **not** treated as permission to copy or train on the source media.

AutoClip separates reference evidence into three modes:

- `metadata_only`: public URL/video id, title, creator, duration, views/likes, publish time and reported license. No frame/timing/edit annotations are allowed.
- `creative_commons`: structural timing/edit annotations are allowed only when the official YouTube Data API reports `status.license=creativeCommon`.
- `permission`: structural analysis requires explicit permission plus a non-empty local audit reference describing the rights basis.

The app uses the official YouTube Data API for discovery/metadata instead of scraping YouTube pages. Set a separate read-only API key locally:

```powershell
$env:YOUTUBE_DATA_API_KEY="..."
```

Seed known metadata-only references:

```powershell
postal-autoclip-reference seed .\references\osrs_public_metadata_seeds.json
```

Refresh public metadata for known videos:

```powershell
postal-autoclip-reference fetch https://www.youtube.com/watch?v=VIDEO_ID --category pvp
```

Find Creative Commons OSRS references that may legally support deeper structural analysis:

```powershell
postal-autoclip-reference search-cc --query "Old School RuneScape PvP" --category pvp --max-results 20
```

View the aggregate research report:

```powershell
postal-autoclip-reference report
```

The local reference catalog lives at `data/public_reference_catalog.json` and is Git-ignored. Public popularity signals do **not** automatically change detector/editor weights; any tuning change still has to beat the private held-out benchmark.

See `docs/osrs_clip_reference_research.md` for the research policy and methodology.

## Golden VOD Lab

The benchmark labeler runs locally at `127.0.0.1:8792`. It supports owned/permitted VOD playback, keyboard boundary marking, event classification, importance weights, atomic autosave and private corpus export.

Held-out integrity is fail-closed: revealing AutoClip predictions permanently marks that VOD assisted server-side. Reloading, resaving, or client flags cannot make it blind again. Legacy/corrupt drafts with unknown provenance are tuning-only.

Private VOD bytes, transcripts, labels and cases are not committed to the repository.

## Commercial finished-media QA

Before automatic distribution, AutoClip checks the actual encoded MP4 for conditions including:

- video/audio stream presence
- vertical dimensions and aspect ratio
- encoded duration vs intended edit
- A/V timestamp/duration drift
- black/frozen video sections
- silence and mean/peak audio levels
- decoded PCM full-scale saturation
- actual rendered ASS hook/caption pixel bounds
- smart-framing motion limits
- encoded webcam-border/camera presence

Only QA-passing renders can become BEST or enter automatic publishing.

## Development / validation

The commercial gate runs independently on:

- Linux + FFmpeg/ffprobe + full pytest + real encoded-media QA
- Windows + FFmpeg/ffprobe + full pytest + the same media path
- current RuneLite API compile/package

Do not call the product creator-ready merely because CI is green. The v1.0 gate also requires repeatable held-out benchmark evidence and a long real-world soak test without duplicate posts, silent failures, or embarrassing renders.
