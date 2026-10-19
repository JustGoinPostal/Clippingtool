# Postal AutoClip v0.9

Postal AutoClip is a local-first **Old School RuneScape-specific** clipping and social-distribution application. It combines RuneLite telemetry, audio reactions, local Whisper transcription, targeted video analysis, OSRS story logic, finished-video QA, social publishing and audience learning.

The goal is not to be a generic clip cutter with an OSRS skin. AutoClip should understand why an OSRS moment matters: the PK payoff, loot value, raid/boss context, pet, collection-log slot, achievement, death, close escape or streamer reaction.

> v0.9 is a hardening preview. The `production-hardening` work remains draft until the creator-ready gates in issue #2 are satisfied.

## What v0.9 understands

### RuneLite-first OSRS intelligence

- Confirmed local PvP kills using locally-attributed damage instead of guessing every player death is your kill.
- Big outgoing/incoming hits and player/NPC loot.
- PK story clustering: setup hit -> confirmed kill -> loot/reaction.
- High-value PK scoring using loot value without allowing one huge outlier to dominate the model forever.
- Smite story promotion only when a confirmed PK is independently corroborated by the creator's local transcript (`smite`, `smited`, `no prayer`, etc.). AutoClip does **not** pretend RuneLite exposes an opponent's prayer points.
- Close-escape inference that requires recent PvP, incoming damage, dangerous HP, meaningful world movement, disengagement and survival. Inferred events are explicitly marked as inferred.
- Raid/reward clustering for CoX/ToB/ToA rewards, rares and collection-log events.
- Pet drops, combat achievements, personal bests, skill milestones, quest completions and boss kills.
- RuneLite HP/prayer/world-position/current-target telemetry for encounter context.
- Encounter enrichment for major raids and bosses, including Olm/CoX, ToB rooms/Verzik, ToA paths/Wardens, Inferno/Zuk, Colosseum/Sol and many standalone bosses.
- Personality/reaction moments remain eligible even when RuneLite has no exact event.

### OSRS-aware editing

- Event-specific clip windows instead of forcing every moment into the same duration.
- RuneLite X **and Y** player/target focus for vertical smart framing.
- Exact event-timed payoff zooms when authoritative event timing exists.
- 22s / 38s / 58s render variants and automatic BEST selection.
- OSRS-context hooks/titles using item, target, damage, GP value, smite/escape, raid/boss and achievement context.
- Animated captions and calibrated real webcam overlay; AutoClip does not invent a facecam or guess arbitrary RuneLite UI regions.

### Finished-render QA

AutoClip inspects the **encoded MP4**, not just the edit plan, before allowing automatic publishing. Current QA checks include:

- video and audio stream presence
- vertical resolution / near-9:16 aspect
- encoded duration vs intended edit window
- A/V stream start offset and duration delta
- prolonged black frames / black-frame ratio
- frozen-frame duration / ratio
- effectively silent audio
- mean audio level and peak-risk warnings
- decoded PCM full-scale saturation, including sustained saturation runs
- configured caption/hook safety limits
- actual ASS-rendered hook/caption pixel bounds measured from rendered pixels
- expected hook/caption presence
- RuneLite-guided X+Y camera travel and excessive framing speed
- encoded webcam-border verification and near-black camera-interior warnings

Each render stores `qa_status` and detailed findings. Only `PASS` renders can become BEST or enter automatic distribution when the QA guard is enabled. Legacy/unknown renders fail closed until they are re-rendered/rechecked.

## Publishing safety

- YouTube Shorts, TikTok and Instagram Reels queue.
- Queue state persists across app restarts.
- Exponential retry/backoff for safe failures.
- Ambiguous submissions become `needs_review` instead of being blindly replayed.
- Explicit duplicate-risk confirmation before retrying uncertain posts.
- TikTok/Instagram remote IDs checkpointed before risky upload work continues.
- TikTok byte-range upload retries for rate limits, retryable request states, 5xx and transport timeouts; permanent 4xx fails immediately.
- TikTok 416 recovery accepts a replayed byte range only when TikTok's progress evidence proves those bytes were already accepted.
- A single quarantined/broken job cannot abort the rest of the due-post batch.
- Submitted TikTok/Instagram posts are polled for platform-side completion/failure.
- QA is enforced again immediately before the network publishing stage.

## Creator consoles

Main dashboard:

`http://127.0.0.1:8787`

Creator health / render-QA console:

`http://127.0.0.1:8787/static/health.html`

Analytics dashboard:

`http://127.0.0.1:8787/static/analytics.html`

The Health console surfaces RuneLite heartbeat, recording processing errors, social-account readiness, render-QA status and publishing jobs that need attention. Blocked renders can be sent through **Render All + QA** again instead of silently posting a bad video.

## Distribution strategy

Default model:

**one strong original moment -> all selected platforms**

The same approved moment can be posted to YouTube Shorts, TikTok and Instagram Reels on the same calendar date while each platform keeps independent performance analytics. Packaging can differ by platform without turning the product into three disconnected content calendars.

A platform-aware duplicate guard prevents accidental repetitive posting without treating legitimate cross-posting of the same original creator content as a duplicate.

## Audience learning

- Local YouTube/TikTok/Instagram performance history in SQLite.
- Platform-specific performance scoring.
- Learning waits until posts have enough age/views by default.
- Audience signals are bounded and do not replace creator Keep/Great/Reject feedback.
- Future ranking can learn per-platform performance while the creator's explicit feedback remains higher authority.

## Objective OSRS benchmark

`app.benchmark` evaluates labeled OSRS moments using:

- recall / weighted recall
- precision
- top-K hit rate
- duplicate candidate rate
- false-positive rate
- boundary quality
- event-type accuracy

`app.benchmark_corpus` aggregates exact counts across separate tuning and held-out sessions. `app.benchmark_gate` compares a candidate build against an accepted baseline and fails when held-out metrics regress beyond bounded tolerances. See `benchmarks/README.md` for the golden-VOD workflow.

### Golden VOD Lab

Run:

```powershell
postal-autoclip-labeler
```

The local lab opens at `127.0.0.1:8792` and supports owned/permitted VOD playback, keyboard boundary marking, event classification, importance weights, atomic autosave and private corpus export.

Held-out integrity is fail-closed: revealing AutoClip predictions permanently marks that VOD assisted server-side. Reloading, resaving or client flags cannot make it blind again. Legacy/corrupt drafts with unknown provenance are tuning-only.

Private VOD bytes, transcripts, labels and benchmark cases stay out of Git by default.

## Rights-aware public OSRS reference research

Popular public OSRS YouTube videos are useful for **market/reference metadata**, but public availability is not treated as permission to copy, download, train on or perform frame-level structural analysis of the source media.

AutoClip separates reference evidence into three modes:

- `metadata_only`: public URL/video ID, creator, title, duration, publish time, public views/likes, embeddable status and reported license. Timing/edit annotations are rejected.
- `creative_commons`: structural timing/edit annotations are allowed only when the official YouTube Data API reports `status.license=creativeCommon`.
- `permission`: structural analysis requires explicit permission plus a non-empty local audit reference describing the rights basis.

The reference client uses the official YouTube Data API rather than scraping YouTube pages.

Set a separate read-only API key locally:

```powershell
$env:YOUTUBE_DATA_API_KEY="..."
```

Seed known metadata-only references:

```powershell
postal-autoclip-reference seed .\references\osrs_public_metadata_seeds.json
```

Refresh metadata for known videos:

```powershell
postal-autoclip-reference fetch https://www.youtube.com/watch?v=VIDEO_ID --category pvp
```

Search specifically for Creative Commons OSRS references:

```powershell
postal-autoclip-reference search-cc --query "Old School RuneScape PvP" --category pvp --max-results 20
```

Generate the aggregate reference report:

```powershell
postal-autoclip-reference report
```

The local catalog lives at `data/public_reference_catalog.json` and is Git-ignored. Standard-license popular videos can influence research hypotheses through public metadata, but they cannot contribute structural timing/edit annotations. Popularity data does **not** automatically change detector/editor weights; every meaningful tuning change still has to beat the private held-out benchmark.

See `docs/osrs_clip_reference_research.md` for methodology and guardrails.

## Install

Use Python 3.11 or 3.12 on Windows.

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
.\launch.ps1
```

Then open the main dashboard at `http://127.0.0.1:8787`.

## RuneLite companion

The companion sends local OSRS events to the AutoClip API. By default it uses:

`http://127.0.0.1:8787/api/game-events`

The token must match `runelite_bridge_token` in `config.json`. Smart framing and lightweight local-state telemetry are configurable in the RuneLite plugin settings.

Gameplay must never depend on AutoClip being open: network work runs away from the RuneLite client thread and bridge failures are ignored by the game client.

## YouTube publishing / analytics

Publishing uses a local Google Desktop OAuth client at:

`secrets/youtube_client_secret.json`

YouTube publishing keeps its narrow upload scope. Public-reference discovery uses a separate read-only API-key path instead of silently increasing every creator's OAuth permissions.

YouTube analytics uses the separate local read-only analytics flow:

```powershell
.\connect_analytics.ps1
.\refresh_analytics.ps1
```

## TikTok

TikTok publishing uses the Content Posting API. Creator-info/privacy capabilities are queried before upload. The access token used for owned-video analytics also needs the applicable `video.list` permission.

Public Direct Post behavior must continue to follow TikTok's current audit/policy requirements; the release gate tracks the remaining production policy/consent UX.

## Instagram

Instagram Reels uses the local credential configuration in `secrets/instagram_token.json`, creates a resumable media container, uploads the render, polls container processing and publishes only after Meta reports it ready.

## Privacy

Source VODs, transcripts, RuneLite event history, creator feedback, render QA details, analytics history and OAuth/access tokens stay local by default. Credential files under `secrets/` are Git-ignored. Only media/metadata explicitly queued for a selected platform is sent to that platform.

Do not commit private VODs/transcripts into the public benchmark repository. Commit small labels/metric results instead.

The public-reference catalog is also local and Git-ignored. Checked-in starter references contain public metadata only, not copied video, audio, transcripts, captions or frames.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

GitHub Actions validates Linux + FFmpeg, Windows + FFmpeg, and the RuneLite companion against the current API/package path.

## Creator-ready release rule

Do **not** call Postal AutoClip v1.0 creator-ready until issue #2's P0 gates are satisfied, the real labeled OSRS VOD benchmark is repeatable, platform failure injection is comprehensive, and a long real-world soak test completes without duplicate posts, silent failures or embarrassing renders.
