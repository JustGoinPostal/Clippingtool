# Changelog

## 0.7.0

- Added Instagram Reels publishing through Meta's local resumable upload flow.
- Added Instagram container status polling and delayed `media_publish` until processing finishes.
- Added configurable Meta Graph API version, defaulting to `v26.0`.
- Added local Instagram credential loading from environment variables or `secrets/instagram_token.json`.
- Added automatic cover-frame selection based on OSRS event type.
- Added generated JPEG cover previews for rendered variants.
- TikTok automatically receives the selected `video_cover_timestamp_ms`.
- Instagram automatically receives the selected `thumb_offset`.
- YouTube can automatically upload the selected frame as a custom thumbnail.
- Added weekly distribution planner for approved/favorite clips.
- Planner automatically uses each clip's BEST render.
- Added duplicate guards against recently queued/published clips.
- Added transcript/title/hook similarity filtering to avoid repetitive posts.
- Added event-type diversity so a weekly plan does not repeatedly schedule the same kind of OSRS moment when alternatives exist.
- Added staggered platform offsets so cross-posts do not all fire at the same minute.
- Added weekly plan preview and one-click Queue This Week workflow in the dashboard.
- Added Instagram account readiness state to the publishing dashboard.
- Added generated cover previews to the render editor.
- Generated cover files are ignored by Git.

## 0.6.0

- Added local publishing queue and scheduler.
- Added YouTube Shorts uploads through the official YouTube Data API and OAuth `youtube.upload` scope.
- Added a local YouTube connection flow using a Desktop OAuth client JSON stored under `secrets/`.
- Added TikTok Direct Post FILE_UPLOAD integration using the official Content Posting API.
- Added TikTok creator-info lookup so the dashboard uses the creator's current allowed privacy options.
- Added TikTok asynchronous post-status polling through `/v2/post/publish/status/fetch/`.
- Added queue states for queued, publishing, submitted, published, and failed posts.
- Added automatic retry up to three attempts for upload failures.
- Added Queue BEST workflow so the highest-scoring render can be scheduled without manually locating the file.
- Added publish metadata fields for title, caption, hashtags, privacy, and schedule time.
- Added published platform ID/URL tracking.
- Added retry/remove controls in the dashboard.
- Added `secrets/` and token files to `.gitignore`; OAuth credentials are never committed.
- Publishing remains opt-in: rendering a clip never posts it automatically.

## 0.5.0

- Added automatic deterministic opening hooks for every candidate clip.
- Added hook editing and one-click hook regeneration in the dashboard.
- Added timed hook overlays to the rendered Short.
- Added event-aware dynamic payoff zoom pulses for OSRS focus renders.
- Added local post-render quality scoring for hook, pacing, length fit, payoff, context, dead air, and focus.
- Added separate quality scores for Short (22s), Medium (38s), and Long (58s) versions.
- Added automatic best-variant selection; the highest-scoring render becomes the clip's primary output.
- Added BEST badges and quality breakdowns in the browser editor.
- Editing timing or hook text now invalidates stale render records.
- All v0.5 scoring and hook generation remain local/free with no cloud API requirement.

## 0.4.0

- Added browser-based source-VOD clip editor.
- Added editable candidate start/end boundaries.
- Added source-video scrubbing and range preview from the dashboard.
- Added Short (22s), Medium (38s), and Long (58s) render variants.
- Added Render All workflow and per-variant render tracking.
- Added OSRS-aware `osrs_focus` vertical layout.
- Added combat, chat/reward, right-side UI, and center focus modes.
- Added conservative dead-air trimming for speech/reaction/chat clips.
- Gameplay-heavy PvP/drop/raid clips stay continuous by default.
- Upgraded ASS captions with tighter groups, word timing, emphasis scaling, and pop animation.
- Added v0.4 render/editor configuration values.
- Added v0.4 render-logic smoke tests.
- Facecam remains completely optional/not required.

## 0.3.0

- Added optional localhost RuneLite companion bridge.
- Added game-event database/API and batch endpoint.
- Added OBS recording-time alignment for RuneLite event timestamps.
- Added exact OSRS event scoring for loot, PK loot, collection log, deaths, big hits and raid/reward events.
- Added RuneLite loot-value weighting and event summarization.
- Added exact-event clustering/limits for long sessions.
- Added center-screen, gold/reward and red/damage visual signals.
- Added exact RuneLite event as a preference-learning feature.
- Added dashboard bridge status/recent event panel.
- Added bridge test script.
- User-facing candidate scores now cap at 100.
- Facecam remains completely optional/not required.

## 0.2.0

- Added camera-free visual pre-scan.
- Added chatbox, inventory/UI and purple/reward signals.
- Added smart clip boundaries, de-duplication and event diversity.
- Added Keep/Great/Reject preference learning.
- Added highlight timeline and optional local Ollama second pass.
