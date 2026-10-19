# Postal AutoClip v0.8

Postal AutoClip is a clean-room, local-first OSRS/RuneLite stream clipping and social-distribution tool. It can watch OBS recordings, detect moments, learn from Keep/Great/Reject decisions, render multiple vertical versions, pick the BEST edit, generate covers, cross-post the same strong clip to YouTube Shorts, TikTok and Instagram Reels, and now learn from real audience performance.

No facecam is required.

## v0.8 strategy

The default marketing model is now **one strong moment -> all selected platforms**. Cross-posting the same original clip is not treated as duplication. The duplicate guard is platform-aware, so a clip already posted to YouTube can still be scheduled to TikTok and Instagram.

Platform-specific packaging can still differ: title/caption, hashtags, privacy, cover treatment and schedule. The underlying clean master clip stays the same.

## v0.8 highlights

- Audience analytics collectors for YouTube, TikTok and Instagram.
- YouTube metrics can include views, engaged views, likes, comments, shares, average view duration, average view percentage and subscribers gained.
- TikTok owned-video metrics use `video.list` and include views, likes, comments and shares when a public post ID is available.
- Instagram Reel insights are requested defensively one metric at a time so one unsupported/deprecated metric does not break the whole collector.
- Local analytics history stored in SQLite.
- Cross-platform performance score from views, weighted engagement and retention where available.
- Once there is enough history, performance is partly normalized against your own results on that platform.
- Audience-performance signals blend into future clip ranking instead of replacing your explicit Keep/Great/Reject preferences.
- Analytics do not influence ranking until a post is old enough and has enough views.
- Automatic background analytics refresh while Postal AutoClip is running.
- New local analytics dashboard at `http://127.0.0.1:8787/static/analytics.html`.
- Manual analytics refresh and YouTube-analytics OAuth helper scripts.
- Distribution API now defaults to YouTube + TikTok + Instagram when platforms are not explicitly supplied.

## Full pipeline

`OBS + optional RuneLite events -> audio/video/Whisper analysis -> candidate scoring -> taste + audience learning -> hook/editor -> 22s/38s/58s renders -> BEST render -> cover -> cross-platform weekly plan -> YouTube/TikTok/Instagram -> analytics -> better future ranking`

## Install

Use Python 3.11 or 3.12 on Windows.

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
.\launch.ps1
```

Main dashboard:

`http://127.0.0.1:8787`

Analytics dashboard:

`http://127.0.0.1:8787/static/analytics.html`

## YouTube publishing and analytics

Publishing still uses your local Google Desktop OAuth client at:

`secrets/youtube_client_secret.json`

Connect normal YouTube publishing from the main dashboard. v0.8 uses a separate read-only analytics token so analytics permissions do not need to be mixed into the upload token.

Run once:

```powershell
.\connect_analytics.ps1
```

This requests read-only YouTube/YouTube Analytics permissions and stores the resulting local token under `secrets/`.

To pull metrics immediately:

```powershell
.\refresh_analytics.ps1
```

## TikTok analytics

The TikTok access token used for analytics needs the `video.list` scope in addition to the scopes required for publishing. Postal AutoClip queries owned videos for view, like, comment and share counts.

For posts created through the Content Posting API, TikTok may initially give Postal AutoClip a `publish_id`. v0.8 reads the public post ID from TikTok's publish-status result when it is available. If no safely matchable public post ID exists, the collector records a note instead of guessing which TikTok belongs to the clip.

## Instagram analytics

Postal AutoClip reuses the Instagram credential setup from v0.7 (`secrets/instagram_token.json`). It reads Reel insights using the configured Graph API version. Because Meta changes which metrics are valid by media type/version, v0.8 requests metrics independently and keeps whatever the connected account currently supports.

## Audience-learning guardrails

Default settings:

```json
{
  "analytics_enabled": true,
  "analytics_refresh_hours": 6.0,
  "analytics_history_days": 90,
  "analytics_collection_min_age_hours": 6.0,
  "analytics_learning_enabled": true,
  "analytics_learning_weight": 0.35,
  "analytics_learning_min_age_hours": 24.0,
  "analytics_learning_min_views": 100
}
```

A newly published clip can be measured after the collection minimum, but it does not train future ranking until it is at least 24 hours old and has at least 100 views by default. Audience learning is bounded so one viral outlier cannot completely override your explicit feedback.

## Cross-platform distribution

Recommended default workflow:

1. Stream normally.
2. Let AutoClip detect candidates.
3. Mark the genuinely good moments Keep/Great.
4. Render All and let it choose BEST.
5. Preview the weekly plan.
6. Cross-post the same approved moment to YouTube, TikTok and Instagram.
7. Let each platform use native packaging/cover metadata.
8. Let v0.8 collect results and gradually improve ranking.

This means five strong weekly moments can become fifteen native distribution posts without requiring fifteen different videos.

## Existing capabilities

- Camera-free OSRS visual/audio/transcript detection.
- Optional RuneLite exact-event bridge.
- Rare-drop, PvP, raid, big-hit and reaction-oriented ranking.
- Local Whisper transcription.
- Optional local Ollama second pass.
- Editable timing and hooks.
- Animated captions and OSRS-aware reframing.
- 22s / 38s / 58s variants and automatic BEST selection.
- Automatic cover-frame extraction.
- YouTube Shorts publishing.
- TikTok Content Posting API support.
- Instagram Reels resumable publishing.
- Local scheduling and retry queue.
- Weekly cross-platform distribution planner.
- Platform-aware duplicate/repetition protection.

## Golden VOD Lab

The production-hardening branch includes a private benchmark labeler:

```powershell
postal-autoclip-labeler
```

It runs locally at `127.0.0.1:8792` and supports owned/permitted VOD playback, keyboard boundary marking, event classification, importance weights, atomic autosave, and private corpus export.

Held-out integrity is fail-closed: revealing AutoClip predictions permanently marks that VOD assisted server-side. Reloading, resaving, or client flags cannot make it blind again. Legacy/corrupt drafts with unknown provenance are tuning-only.

Private VOD bytes, transcripts, labels and benchmark cases are not committed to the repository.

## Public OSRS reference research

Popular public OSRS videos can help answer market questions such as which event types, durations, titles and packaging styles attract attention, but public availability is **not** treated as permission to copy or train on source media.

AutoClip separates reference evidence into three modes:

- `metadata_only`: public URL/video id, creator, title, duration, publish time, public views/likes, embeddable status and reported license. No timing/edit annotations are allowed.
- `creative_commons`: structural timing/edit annotations are allowed only when the official YouTube Data API reports `status.license=creativeCommon`.
- `permission`: structural analysis requires explicit permission plus a non-empty local audit reference describing the rights basis.

The research client uses the official YouTube Data API instead of scraping YouTube pages. Configure a separate local read-only API key:

```powershell
$env:YOUTUBE_DATA_API_KEY="..."
```

Seed known metadata-only references:

```powershell
postal-autoclip-reference seed .\references\osrs_public_metadata_seeds.json
```

Refresh metadata for known references:

```powershell
postal-autoclip-reference fetch https://www.youtube.com/watch?v=VIDEO_ID --category pvp
```

Search specifically for Creative Commons OSRS references:

```powershell
postal-autoclip-reference search-cc --query "Old School RuneScape PvP" --category pvp --max-results 20
```

View aggregate research metrics:

```powershell
postal-autoclip-reference report
```

The local catalog is `data/public_reference_catalog.json` and is Git-ignored. Popularity/reference data does **not** automatically change detector/editor weights; tuning changes still have to beat the private held-out benchmark.

See `docs/osrs_clip_reference_research.md` for the research policy and methodology.

## Commercial finished-media QA

The production-hardening branch inspects the actual encoded MP4 before automatic distribution, including checks for video/audio stream presence, vertical dimensions/aspect, encoded duration, A/V timing, black/frozen sections, silence, mean/peak audio level, decoded PCM full-scale saturation, rendered ASS hook/caption pixel bounds, smart-framing motion, and encoded webcam presence.

Only QA-passing renders can become BEST or enter automatic publishing.

## Privacy

Source VODs, transcripts, game events, clip feedback, renders, analytics history and OAuth/access tokens stay local by default. Credential files under `secrets/` are Git-ignored. Only media/metadata you explicitly queue is sent to the selected social platform.

The public-reference catalog is local and Git-ignored. Checked-in starter references contain public metadata only, not copied video, audio, transcripts, captions or frames.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

GitHub Actions on the production-hardening branch validate Linux + FFmpeg, Windows + FFmpeg, and the current RuneLite API/package path. Green CI is necessary but not sufficient for creator-ready v1.0; the release gate also requires a real held-out OSRS corpus and a long real-world soak test.
