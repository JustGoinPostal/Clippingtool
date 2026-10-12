# Postal AutoClip v0.7

Postal AutoClip is a clean-room, local-first automatic VOD clipper and social distribution tool tuned for OSRS and RuneLite. It watches OBS recordings, transcribes locally, detects important moments, learns from Keep/Great/Reject decisions, renders multiple 9:16 versions, picks the best one, generates a cover frame, and can schedule/publish approved clips to YouTube, TikTok, and Instagram Reels.

No facecam is required.

## v0.7 highlights

- Instagram Reels publishing through Meta's resumable local-file upload flow.
- Automatic Instagram processing-status polling before `media_publish`.
- Automatic cover-frame selection for each rendered clip.
- TikTok uses the selected cover timestamp.
- Instagram uses the selected `thumb_offset`.
- YouTube can upload the extracted cover frame as a custom thumbnail.
- Weekly distribution planner for Keep/Great clips.
- Planner always prefers the clip's BEST rendered variant.
- Duplicate guard against already queued/published clips.
- Similarity guard using title + hook + transcript text.
- Event diversity so a week is less likely to become five nearly identical PvP/drop clips when alternatives exist.
- Platform staggering so YouTube/TikTok/Instagram cross-posts do not all fire at the same minute.
- Weekly preview before anything is queued.
- One-click **Queue This Week** after reviewing the plan.
- Generated cover previews in the browser editor.

## Full pipeline

`OBS recording + optional RuneLite events -> audio/video/Whisper analysis -> candidate scoring -> preference learning -> hook -> editor -> 22s/38s/58s renders -> quality scoring -> BEST render -> cover frame -> weekly planner -> YouTube/TikTok/Instagram queue`

## Install on Windows

1. Install Python 3.11 or 3.12.
2. Clone or download this repository.
3. Open PowerShell in the project folder.
4. Run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
.\launch.ps1
```

Dashboard:

```text
http://127.0.0.1:8787
```

The installer installs project dependencies and attempts to install FFmpeg through `winget` if it is missing.

## Normal workflow

1. Point `watch_folder` in `config.json` at your OBS recordings.
2. Finish a stream or manually analyze a recording.
3. Review detected candidates.
4. Use **Keep**, **Great**, or **Reject** to teach the local preference model.
5. Edit timing/hook text if needed.
6. Click **Render All**.
7. Postal AutoClip creates 22s, 38s, and 58s versions and marks one **BEST**.
8. Approve several clips.
9. Open the **Weekly distribution planner**.
10. Select YouTube / TikTok / Instagram, preview the week, then click **Queue This Week**.
11. Postal AutoClip publishes due jobs while it is running.

## Automatic cover selection

Every render gets an event-aware cover timestamp. Combat moments bias toward the likely KO/payoff area; raid/drop moments bias slightly later toward the reward reveal; reactions bias earlier.

The dashboard generates a JPEG preview on demand at:

```text
data/covers/
```

Those files are generated locally and ignored by Git.

With `youtube_set_thumbnail=true`, Postal AutoClip attempts to upload that JPEG with YouTube's thumbnail API after the video upload. A thumbnail failure does not fail the video upload itself.

## Weekly planner

Defaults:

```json
{
  "duplicate_window_days": 30,
  "duplicate_similarity_threshold": 0.62,
  "distribution_slots": ["12:00", "18:30"],
  "platform_offsets_minutes": {
    "youtube": 0,
    "tiktok": 20,
    "instagram": 40
  }
}
```

The planner only uses clips marked **Keep** or **Great** that already have a rendered version. It prefers favorites, render quality score, and candidate score.

It filters:

- the exact same clip if it was recently queued/published on a selected platform;
- highly similar title/hook/transcript combinations;
- duplicate-like clips inside the new plan itself;
- repeated event types when a different eligible event is available.

The same approved clip may still be cross-posted to multiple selected platforms; the duplicate guard is platform-aware.

## YouTube setup

Postal AutoClip uses Google's OAuth flow and `youtube.upload` scope.

1. Create/select a Google Cloud project.
2. Enable **YouTube Data API v3**.
3. Configure the OAuth consent screen.
4. Create an OAuth client of type **Desktop app**.
5. Download the client JSON.
6. Save it as:

```text
secrets/youtube_client_secret.json
```

7. Start Postal AutoClip.
8. Click **Connect YouTube**.
9. Complete authorization in the browser.

The refresh token is stored locally at:

```text
secrets/youtube_token.json
```

Both files are ignored by Git.

## TikTok setup

TikTok posting requires a TikTok for Developers app with Content Posting API access and a user token authorized for `video.publish`.

Either set:

```powershell
$env:POSTAL_TIKTOK_ACCESS_TOKEN="your-access-token"
```

or create:

```text
secrets/tiktok_token.json
```

with:

```json
{
  "access_token": "your-access-token"
}
```

Postal AutoClip queries creator info before posting so it can use the account's currently permitted privacy values. Local MP4s use TikTok `FILE_UPLOAD`, then the queue remains `submitted` until TikTok reports completion.

## Instagram Reels setup

v0.7 can upload the local rendered MP4 directly to Meta using the Instagram Reels resumable upload flow; a public CDN URL is not required for this mode.

Create:

```text
secrets/instagram_token.json
```

with:

```json
{
  "access_token": "your-meta-access-token",
  "ig_user_id": "your-instagram-user-id"
}
```

You can alternatively set:

```powershell
$env:POSTAL_INSTAGRAM_ACCESS_TOKEN="your-meta-access-token"
$env:POSTAL_INSTAGRAM_USER_ID="your-instagram-user-id"
```

The Instagram account/app must be eligible for Instagram content publishing and have the required Meta permissions/account relationship. v0.7 defaults to Graph API `v26.0`:

```json
"instagram_graph_version": "v26.0"
```

The upload lifecycle is:

`create REELS container with upload_type=resumable -> upload local MP4 to rupload.facebook.com -> poll status_code -> media_publish -> fetch permalink`

Instagram jobs therefore use the same `submitted` state as TikTok while platform-side processing is incomplete.

## Publishing queue states

- `queued` — waiting for scheduled time;
- `publishing` — local upload/API call is running;
- `submitted` — platform accepted the upload but is still processing it;
- `published` — platform completed publication;
- `failed` — publication failed after retries or platform processing returned an error.

Queued jobs survive restarts because queue state lives in SQLite.

Rendering alone never posts anything. Posts enter the publisher only after you explicitly queue them or commit a weekly plan.

## Editing and rendering

The browser editor supports:

- source-VOD scrubbing;
- exact start/end adjustment;
- hook editing/regeneration;
- 22s / 38s / 58s renders;
- quality score comparison;
- BEST variant selection;
- generated cover preview.

The default OSRS layout keeps the full RuneLite frame visible while adding a second focus area for combat, reward/chat, UI, or general gameplay.

## RuneLite companion

The optional companion source lives under:

```text
runelite-companion/
```

It can send exact timestamps for loot, PK/player loot, collection-log messages, deaths, big hits, and selected game messages to:

```text
http://127.0.0.1:8787/api/game-events
```

The clipper still works without the companion by using audio, transcript, and video analysis.

## Optional Ollama second pass

Set an installed local model in `config.json`:

```json
"ollama_model": "your-local-model-name"
```

This is optional. Core clipping, editing, scoring, covers, scheduling, and distribution do not require a paid AI API.

## Local data

Rendered videos:

```text
data/output/
```

Cover frames:

```text
data/covers/
```

SQLite queue/state:

```text
data/postal_autoclip.db
```

Credentials:

```text
secrets/
```

`config.json`, tokens, databases, VOD data, renders, and generated cover images are ignored by Git.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

GitHub Actions also installs the project, compiles Python, and runs pytest on pushes to `main`.

## Known limitations

- Scheduled jobs run only while Postal AutoClip is running; overdue queued jobs remain stored until the next launch.
- YouTube, TikTok, and Instagram each require your own developer/account authorization.
- TikTok public Direct Post remains subject to TikTok app review/audit rules.
- Instagram eligibility and publishing permissions are controlled by Meta.
- The weekly planner optimizes variety using local heuristics; it does not predict actual social-platform performance.
- YouTube custom-thumbnail availability can depend on channel/account eligibility; thumbnail failure is non-fatal.
- Cover selection is event-aware timing, not full frame-by-frame object recognition.

## Privacy

VODs, transcripts, game-event metadata, ranking feedback, edits, renders, generated covers, schedule data, and credentials stay on your PC by default. The dashboard and RuneLite bridge bind to `127.0.0.1`. Only media/metadata that you explicitly queue is sent to the selected platform.
