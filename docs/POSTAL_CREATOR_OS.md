# Postal Creator OS

## Goal

Postal Creator OS is a local-first creator automation stack hosted on Postal's dedicated home server. The normal workflow is intentionally simple:

1. Postal starts OBS and streams normally.
2. The streaming PC sends completed recordings and lightweight telemetry to `CREATOR-01` over the LAN.
3. The server detects moments, renders clips, packages content, schedules/publishes posts, collects analytics, runs bots, and stores history.
4. ChatGPT is the human-facing analysis and control surface when Postal wants to inspect or change something.
5. Routine automation must continue even when ChatGPT is closed.

The target is a one-person creator operation where streaming is the main manual task.

## Hard rules

- Host Creator OS on a dedicated VM/server, not the streaming PC.
- Keep `RENTAL-01` isolated and untouched.
- Default recurring infrastructure cost target is $0 beyond services already owned.
- No OpenAI API dependency by default.
- Paid APIs/cloud services are optional and disabled until explicitly enabled.
- Large media stays local.
- Cloudflare is a secure HTTP front door, not the compute platform.
- SMB/file ingestion stays LAN-only.
- Destructive/security-sensitive actions require approval.

## Architecture

```text
STREAMING PC
OBS / RuneLite / game / microphone
        |
        | LAN
        v
CREATOR-01 (dedicated home-server VM)
+---------------------------------------------------+
| ingest | AutoClip | Whisper | FFmpeg | analytics |
| bots   | queue    | scheduler | local DB/storage |
+---------------------------------------------------+
        |
        +--> social platform APIs (publish/metrics)
        |
        +--> Cloudflare Tunnel (dashboard/control only)
        |
        +--> ChatGPT bridge/app when available
```

## Streaming-PC responsibilities

The streaming PC should remain lightweight:

- OBS streaming/recording
- RuneLite/game clients
- lightweight recording handoff agent
- lightweight OBS/RuneLite telemetry relay

It should not perform long VOD analysis, analytics collection, social scheduling, or bot hosting once `CREATOR-01` is operational.

## Dedicated-server responsibilities

`CREATOR-01` owns:

- recording ingestion
- source VOD storage
- local Whisper transcription
- audio/video/event analysis
- clip candidate detection
- FFmpeg rendering
- captions/hooks
- platform-specific packaging
- social publishing queue
- retries
- analytics collection
- platform-specific learning
- Discord/Kick bots
- stream reports
- content calendar/state
- Creator dashboard
- ChatGPT control bridge

## Continuous automation without paid AI

The always-on pipeline uses deterministic code and local processing first:

```text
recording / telemetry
        v
local event detection
        v
local scoring
        v
candidate clips
        v
local render/caption/package
        v
schedule/publish
        v
analytics
        v
platform-specific learning
```

Local models such as Ollama may be used where they improve quality, but they are optional. The system must remain functional without a paid AI API.

## ChatGPT's role

ChatGPT is the operator/strategist surface, not a required runtime dependency.

When the control bridge is connected, ChatGPT should be able to inspect:

- current system health
- current/previous streams
- recent events
- detected clips
- publishing queue
- analytics
- failures
- local recommendations

And, where supported and permitted, perform safe actions such as:

- render a clip
- schedule a clip
- publish a clip
- change posting settings
- restart a failed worker
- update a content plan

Until direct app access is available for the account, a replaceable control bridge (for example GitHub-backed command/state exchange) may be used without redesigning the core system.

## Automation policy

### Fully automatic

- ingest completed recordings
- transcribe
- detect candidates
- render variants
- create captions
- rank variants
- schedule according to configured policy
- publish according to configured policy
- gather analytics
- retry transient failures
- update Discord/go-live state
- create post-stream/local reports

### Approval required

- deleting source VODs
- deleting published posts
- credential/security changes
- mass messaging
- account actions that could create a ban/lockout risk
- enabling any paid service/API

## Data/storage

Use local storage for:

- VODs
- clips/renders
- transcripts
- event logs
- analytics
- local configuration

Start with SQLite for application/event metadata. Move to PostgreSQL only if the workload later justifies it. Video files are never stored as database blobs.

## Network/security

- Creator VM lives on the existing private Proxmox network.
- SMB ingest is LAN-only.
- Do not port-forward raw Creator services.
- Cloudflare Tunnel/Access may expose authenticated HTTP dashboard/control surfaces.
- Social credentials belong on `CREATOR-01` when possible.
- Never commit credentials or tokens to Git.

## Implementation sequence

### 1. Dedicated server + zero-touch ingestion

- create `CREATOR-01`
- create local Creator directories
- create authenticated `postal-ingest` SMB share
- run streaming-PC handoff agent
- verify completed OBS recordings arrive automatically

### 2. Server-side AutoClip

- make existing AutoClip Linux/server friendly
- automatic ingest worker
- local Whisper/FFmpeg pipeline
- server-hosted dashboard

### 3. Stream telemetry

- OBS WebSocket relay
- RuneLite event relay
- Kick/chat collector
- chat/viewer spike detection
- crowd `!clip` signal

### 4. Distribution + analytics

- automatic render selection
- cross-platform scheduling
- posting/retry workers
- analytics collection
- per-platform learning

### 5. Bots + notifications

- Discord/Kick bot hosted on server
- go-live/stream-end automation
- immediate failure alerts
- local post-stream reports

### 6. ChatGPT control plane

- expose safe status/actions through a replaceable bridge
- connect a Postal Creator ChatGPT app/plugin where account support allows it
- keep all server-side approval rules independent of ChatGPT

## Definition of success

A successful normal day:

- Postal opens OBS and streams.
- Postal does not move VOD files manually.
- Postal does not mark clip timestamps manually.
- Postal does not cut Shorts manually.
- Postal does not copy captions between platforms manually.
- Postal does not manually check multiple analytics dashboards.
- Creator OS continues operating when ChatGPT is closed.
- Postal can open ChatGPT and ask what happened, what is working, what failed, or request a safe change.
- The next content queue is already prepared/published according to policy.
