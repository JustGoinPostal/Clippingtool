# Postal AutoClip v0.9 — App Overview

Postal AutoClip is a local-first Windows OSRS stream clipping, editing, publishing, scheduling, and audience-learning application.

## 1. Windows launcher

`PostalAutoClip.exe` is the entry point.

The launcher is a dark two-column control window.

### Left: Control

- OBS recording folder picker
- Save Folder
- Run Setup
- START AUTOCLIP
- STOP
- Open Clips
- Analytics
- Accounts
- Secrets
- Activity log

### Right: Status

- Server: RUNNING / STOPPED
- Setup: READY / SETUP NEEDED
- YouTube: CONNECTED / PARTIAL / NOT CONNECTED
- TikTok: CONNECTED / NOT CONNECTED
- Instagram: CONNECTED / NOT CONNECTED
- RuneLite: EVENTS SEEN / WAITING / SERVER OFF
- MANAGE ACCOUNTS button

The launcher performs first-run dependency setup, starts the local FastAPI server on `127.0.0.1:8787`, and the local account manager on `127.0.0.1:8790`.

## 2. Main browser dashboard

URL: `http://127.0.0.1:8787`

The dashboard now has a sticky navigation row:

- Clips
- Publishing
- Processing
- Analytics
- Accounts

`Clips`, `Publishing`, and `Processing` jump to sections on the main local dashboard. `Analytics` opens the analytics page. `Accounts` opens the account manager.

### Analyze a recording

You can paste a source recording path and start analysis manually. Normally the watcher can process new recordings automatically from the configured OBS folder.

### Candidate clips

Each detected moment shows:

- AutoClip score
- event type
- editorial status
- generated title
- generated opening hook
- start/end timing
- transcript excerpt
- Keep / Great / Reject controls
- Edit button
- 22s / 38s / 58s render buttons
- Render All
- BEST variant badge
- Queue BEST
- local video preview once rendered

Keep / Great / Reject feeds the personal preference model.

### Clip editor

The editor opens over the dashboard and includes:

- source VOD preview
- exact start/end controls
- set start/end from current playhead
- preview selected range
- editable generated hook
- regenerate hook
- save edit
- render Short / Medium / Long
- Render All + Pick BEST
- render quality cards
- generated cover preview
- BEST marker

Changing timing or hook invalidates stale renders so an old edit is not accidentally published.

## 3. Publishing

The Publishing area contains three pieces.

### Account summary

Shows readiness for:

- YouTube
- TikTok
- Instagram Reels

Account attachment/reconnection is performed from the Accounts page.

### Weekly distribution planner

The planner uses approved Keep/Great clips that have rendered output.

Current strategy rule:

- same strong clip across selected platforms
- same local calendar date across platforms
- platform-specific minute offsets are allowed
- platform-specific packaging is allowed
- platform-specific render length can be learned after enough evidence
- the content calendar is not shuffled onto different days just because one platform historically likes a category more

Controls include:

- selected platforms
- number of approved clips
- number of days
- starting local time
- daily posting slots
- Preview Week
- Queue This Week

### Publishing queue

Each queued item tracks:

- clip
- platform
- render variant
- scheduled time
- queue state
- failures/retry
- published URL when available

TikTok and Instagram asynchronous publishing is polled until the platform reports completion.

## 4. Accounts

URL: `http://127.0.0.1:8790`

This is now the single social-account connection center.

### YouTube

- choose the Google Desktop OAuth client JSON directly in the browser
- save it locally under `secrets/`
- Connect YouTube opens Google authorization
- one authorization requests both publishing and read-only analytics scopes
- publishing and analytics connection states are shown separately
- Disconnect removes local user OAuth tokens while leaving the developer client file available

### TikTok

- enter Client Key and Client Secret once
- shows the exact localhost redirect URI to register
- Connect TikTok opens browser OAuth using PKCE
- requests publishing + owned-video analytics scopes
- access tokens are refreshed automatically when possible

### Instagram

- enter Meta App ID and App Secret once
- shows the localhost redirect URI to register
- Connect Instagram opens Meta authorization
- AutoClip discovers eligible linked Professional Instagram accounts
- if multiple are available, choose the desired account
- stores the page token and Instagram user ID locally
- keeps the local resumable Reel upload workflow

All app credentials and OAuth tokens stay under the Git-ignored `secrets/` directory.

## 5. Analytics

URL: `http://127.0.0.1:8787/static/analytics.html`

The analytics system stores snapshots in local SQLite and can collect supported metrics from each platform.

It tracks platform-level and post-level performance and builds audience-learning signals.

The learning model is intentionally split conceptually into:

1. Global quality — is this a good Postal clip at all?
2. Platform fit — how strongly does this type of clip historically perform on YouTube, TikTok, or Instagram?

Good clips still cross-post everywhere by default. Platform fit influences prioritization, packaging, and eventually preferred render length rather than hiding a good clip from a platform.

Audience performance does not immediately train the model. Default guardrails require a post to be old enough and have enough views before analytics influence future ranking.

## 6. Processing

The Processing section shows recording jobs with:

- job ID
- source file
- current status
- progress bar
- status message

Processing can include:

- source probing
- Whisper transcription
- audio energy/reaction detection
- sampled visual analysis
- optional RuneLite event matching
- candidate generation and ranking

## 7. RuneLite companion

RuneLite events can provide exact OSRS context that video/audio analysis cannot always infer reliably.

Event categories include things such as:

- raid reward
- collection log
- rare drop
- player loot
- PvP kill
- player death
- big hit/spec
- boss kill
- raid completion

The launcher shows whether RuneLite events have been seen recently.

## 8. Rendering

For an approved candidate AutoClip can produce:

- Short: 22 seconds
- Medium: 38 seconds
- Long: 58 seconds

The editor includes:

- animated captions
- generated opening hook
- OSRS-aware focus layout
- event/payoff zoom emphasis
- conservative dead-air trimming
- generated cover frame
- local post-render quality score

Render All scores the variants and marks one global BEST. After enough platform history exists, the planner may choose a different available variant for a specific platform while still posting the same core clip on the same date.

## 9. End-to-end workflow

`OBS stream -> recording watcher -> transcription/audio/video/RuneLite analysis -> candidate ranking -> Keep/Great/Reject -> edit -> 22/38/58 renders -> BEST -> cover -> synchronized cross-platform planner -> publishing queue -> YouTube/TikTok/Instagram -> analytics -> better future ranking`

## 10. Current product state

v0.9 is functional but still a pre-1.0 application. The major remaining product-quality work includes:

- real-world testing on the user's streaming PC
- current RuneLite companion API attribution/compile validation
- stronger active-recording file stability protection
- a formal render/process job queue instead of some raw worker threads
- more polished settings UI
- additional analytics visualization and diagnostics
- platform/app-review setup validation against real connected accounts
- installer/signing/release flow suitable for broader public distribution

The current goal is to make the user's own workflow solid before treating the project as a public consumer application.
