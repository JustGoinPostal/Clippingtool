# Postal AutoClip v0.6

Postal AutoClip is a clean-room, local-first automatic VOD clipper for long gaming streams, tuned for OSRS and RuneLite. It watches OBS recordings, transcribes locally, detects important moments, learns from Keep/Great/Reject decisions, edits 9:16 Shorts, scores multiple versions, picks the best version, and can now queue/schedule publishing.

No facecam is required.

## v0.6 highlights

- Local publishing queue and scheduler.
- **Queue BEST** sends the highest-scoring rendered variant to the publishing queue.
- YouTube Shorts upload through the official YouTube Data API.
- Local Google OAuth flow using the `youtube.upload` scope.
- TikTok Direct Post through the official Content Posting API using local `FILE_UPLOAD`.
- TikTok creator-info lookup before posting so current allowed privacy options are used.
- TikTok publish-status polling after upload.
- Queue states: `queued`, `publishing`, `submitted`, `published`, `failed`.
- Up to three automatic upload attempts for transient failures.
- Scheduled publishing while Postal AutoClip is running.
- Published YouTube URL / platform ID tracking.
- Credentials are stored under local `secrets/` and are Git-ignored.
- Instagram Reels is shown as prepared/not-enabled rather than pretending local direct file upload is available.
- Nothing posts merely because it was rendered. You explicitly queue a post first.

## Full pipeline

`OBS recording + optional RuneLite events -> audio/video/Whisper analysis -> candidate scoring -> preference ranking -> hook -> browser edit -> 22s/38s/58s renders -> local quality scoring -> BEST version -> publishing queue -> YouTube/TikTok`

## Install on Windows

1. Install Python 3.11 or 3.12.
2. Clone/download this repository.
3. Open PowerShell in the project folder.
4. Run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
.\launch.ps1
```

Dashboard:

`http://127.0.0.1:8787`

The installer installs project dependencies and attempts to install FFmpeg through `winget` if needed.

## Normal workflow

1. Set `watch_folder` in `config.json` to your OBS recording folder.
2. Finish a stream or manually analyze a recording.
3. Review detected candidates.
4. Keep/Great/Reject clips to teach the local preference model.
5. Edit timing/hook if needed.
6. Click **Render All**.
7. Postal AutoClip makes 22s, 38s and 58s versions and marks one **BEST**.
8. Click **Queue BEST**.
9. Choose YouTube or TikTok, privacy and schedule time.
10. Postal AutoClip publishes the job when it becomes due while the app is running.

## YouTube setup

Postal AutoClip uses Google's official OAuth flow and the narrow `youtube.upload` scope.

1. Create/select a Google Cloud project.
2. Enable the **YouTube Data API v3**.
3. Configure the OAuth consent screen.
4. Create an OAuth client of type **Desktop app**.
5. Download the client JSON.
6. Save it as:

```text
secrets/youtube_client_secret.json
```

7. Start Postal AutoClip.
8. Click **Connect YouTube** in the Publishing accounts panel.
9. Complete Google's authorization window.

The refresh token is stored locally at:

```text
secrets/youtube_token.json
```

Both files are ignored by Git.

YouTube privacy choices in the dashboard are `private`, `unlisted`, and `public`.

## TikTok setup

TikTok Direct Post requires a TikTok for Developers app with the Content Posting API and authorization for `video.publish`.

After obtaining a user access token, either set:

```powershell
$env:POSTAL_TIKTOK_ACCESS_TOKEN="your-access-token"
```

or create this local file:

```text
secrets/tiktok_token.json
```

with:

```json
{
  "access_token": "your-access-token"
}
```

Do **not** commit TikTok credentials. `secrets/` is Git-ignored.

Before a TikTok post is queued, Postal AutoClip can call TikTok creator-info to obtain the creator's currently allowed privacy options. The dashboard uses those options rather than inventing privacy values.

For local rendered files, Postal AutoClip uses TikTok `FILE_UPLOAD`. After the upload, the queue changes to `submitted` and the worker polls TikTok's publish-status endpoint until it reports `PUBLISH_COMPLETE` or `FAILED`.

Important TikTok limitation: unaudited Direct Post clients are restricted by TikTok and generally cannot publish publicly until the app completes TikTok's audit/review process.

## Instagram Reels

v0.6 intentionally does **not** fake Instagram direct local-file publishing. The dashboard marks Instagram as prepared/not enabled because the supported Meta publishing workflow requires additional app/account setup and a video URL that Meta can fetch.

A hosted-media adapter can be added in a later release.

## Publishing configuration

Defaults in `config.json`:

```json
{
  "publishing_enabled": true,
  "publish_poll_seconds": 20,
  "youtube_default_privacy": "private",
  "tiktok_default_privacy": "SELF_ONLY"
}
```

If the app is closed when a job becomes due, the job stays in the SQLite queue. When Postal AutoClip starts again, due jobs can run normally.

## Publishing safety / control

Rendering does not publish anything automatically.

A post enters the publisher only after you click **Queue BEST** (or use the local publishing API). You can remove queued jobs before they begin, and failed jobs can be retried.

Editing a clip's timing or hook invalidates its unpublished queued jobs and old render records so a stale edit is not accidentally posted.

## Existing v0.5 editing features

- Automatic event-aware opening hooks.
- Editable/regeneratable hook text.
- Dynamic OSRS payoff zoom pulse.
- OSRS-aware focus for combat, reward/chat, UI, or center gameplay.
- Animated word-synced captions.
- Conservative dead-air trimming.
- 22s / 38s / 58s render variants.
- Local quality scores and automatic BEST selection.

## RuneLite companion

The optional companion source is in:

`runelite-companion/`

Default event endpoint:

`http://127.0.0.1:8787/api/game-events`

The companion can supply exact timestamps for loot, PK/player loot, collection-log messages, deaths, big hits and selected game messages. The clipping system still works without it using video/audio/transcript analysis.

## Optional Ollama second pass

Set an installed local model in `config.json`:

```json
"ollama_model": "your-local-model-name"
```

This is optional. Core clipping, hook generation, editing, scoring and scheduling do not require a paid AI API.

## Output and local data

Rendered files:

`data/output/`

SQLite state/queue:

`data/postal_autoclip.db`

Local credentials:

`secrets/`

The repository `.gitignore` excludes `config.json`, databases, rendered VOD data and all files under `secrets/`.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

GitHub Actions also runs installation, Python compilation and pytest on pushes to `main`.

## Known limitations

- Scheduled publishing only runs while Postal AutoClip is running; due jobs remain queued while it is offline.
- YouTube requires your own Google OAuth client configuration.
- TikTok requires your own approved developer app, user authorization and access token.
- TikTok public Direct Post is subject to TikTok's app audit and platform rules.
- TikTok processing is asynchronous; `submitted` is intentionally different from `published`.
- Instagram direct publishing is not enabled in v0.6.
- Local quality scores are editing heuristics, not guarantees of views or virality.
- Dynamic zoom chooses OSRS-aware regions; it is not yet tracking every item/player/NPC frame-by-frame.

## Privacy

Source VODs, transcripts, game-event metadata, feedback, edits, renders, queue state and tokens stay on your PC by default. The dashboard and RuneLite bridge bind to `127.0.0.1`. Only media/metadata you explicitly queue is sent to the selected social platform.
