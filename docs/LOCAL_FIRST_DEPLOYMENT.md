# Postal Creator OS — Local-First Deployment

## Core rule

Default every workload to the local machine. Use Cloudflare as the secure public edge and OpenAI only for intelligence that benefits from a frontier model. Avoid paid infrastructure unless a local option is materially worse.

## Target monthly infrastructure cost

- Local compute/storage: existing hardware
- Cloudflare Tunnel/DNS/Access: free tier where possible
- Database: local SQLite initially; migrate to local PostgreSQL only if/when needed
- Redis/message broker: avoid until needed; use local in-process/background workers first
- Object/video storage: local filesystem
- Dashboard/API: local FastAPI
- Reverse proxy/public ingress: Cloudflare Tunnel
- OpenAI API: usage-based, budget-capped, selective calls only
- Social APIs: direct platform APIs where available
- Backups: local snapshots / external storage before considering paid cloud backup

Goal: recurring SaaS infrastructure cost should be approximately $0. OpenAI usage is the main intentional variable cost.

## Local architecture

```text
Streaming PC / Home Server
|
|-- Postal Creator OS
|   |-- AutoClip
|   |-- Postal Brain
|   |-- Publishing worker
|   |-- Analytics collector
|   |-- PostalBot
|   |-- Local dashboard/API
|   |-- MCP server
|   |-- Scheduler
|   `-- Event bus
|
|-- Local AI
|   |-- faster-whisper
|   |-- optional Ollama/local LLM
|   `-- local video/audio scoring
|
|-- Local data
|   |-- SQLite / future PostgreSQL
|   |-- VODs
|   |-- rendered clips
|   |-- transcripts
|   |-- analytics history
|   `-- event logs
|
`-- cloudflared
    |
    `-- Cloudflare edge
        |-- creator.postalops.com -> local dashboard
        |-- mcp.postalops.com     -> local MCP gateway
        `-- optional webhook hostname -> local webhook receiver
```

## Cloudflare role

Cloudflare is an edge/gateway, not the application host.

Use one Cloudflare Tunnel with multiple hostname routes. Do not expose inbound ports on the router. `cloudflared` makes outbound connections to Cloudflare and routes approved hostnames to local services.

Recommended routes:

```text
creator.postalops.com -> http://127.0.0.1:8787
mcp.postalops.com     -> http://127.0.0.1:8790
```

Protect the human dashboard with Cloudflare Access. Keep MCP authentication separate and enforce authorization again inside Postal Creator OS; do not rely on the tunnel alone for write permissions.

Do not deploy Cloudflare Workers just to proxy requests when Tunnel can reach the local API directly. Workers may be added later only when edge logic has a concrete benefit.

## OpenAI cost strategy

OpenAI should not continuously receive an entire multi-hour stream.

Local pipeline:

1. Record/process locally.
2. Transcribe locally with faster-whisper.
3. Detect candidate windows locally using audio, video, RuneLite events and chat signals.
4. Rank candidates locally.
5. Send only the strongest candidate metadata/transcript windows to OpenAI for semantic judgment, packaging or strategy.
6. Store the result locally.

Recommended model routing:

- Cheap/high-frequency classification: lowest-cost capable model.
- Clip title/caption/hook generation: inexpensive model by default.
- Post-stream strategy: stronger model once per stream.
- Weekly strategic analysis: strongest model only when useful.
- Web research: explicitly budgeted and not run continuously.

Postal Brain must enforce daily/monthly API budgets and degrade gracefully to local-only mode when a budget is reached.

## What remains local

- Source VODs
- Rendered clips until upload
- Transcripts
- RuneLite/game events
- Chat event history
- Analytics database
- Creator knowledge/profile
- Scheduling queue
- Publishing state
- OAuth/access tokens
- API keys
- Logs
- Dashboard
- MCP server
- Discord bot process
- Learning models and feature weights

Only data required for a specific external action should leave the machine.

## Public/private boundaries

### Public-facing via Cloudflare Tunnel

- ChatGPT/MCP gateway (authenticated)
- optional webhook receiver
- optional read-only creator status endpoint

### Private via Cloudflare Access

- creator dashboard
- admin pages
- logs
- account connection pages
- settings

### Localhost/LAN only

- raw database access
- VOD directories
- secrets directory
- internal worker endpoints
- destructive/admin service endpoints whenever possible

## Failure behavior

If Internet access fails:

- stream capture continues
- local transcription continues
- clipping continues
- renders continue
- events are stored locally
- publishing is queued
- analytics refresh waits
- OpenAI analysis waits or falls back locally

When connectivity returns, queued external work resumes.

If OpenAI is unavailable or a spend limit is reached:

- AutoClip continues locally
- local scoring selects clips
- local templates generate fallback titles/captions
- publishing may continue using safe local packaging
- Postal Brain records that AI enrichment was skipped

OpenAI must never be a single point of failure for basic creator operations.

## Deployment phases

### Phase 1 — current machine

Keep the existing FastAPI app on port 8787 and add Postal Brain locally. Add an MCP process on a separate localhost port. Run `cloudflared` as a service.

### Phase 2 — service isolation

When the project grows, split processes into local services without moving them to paid cloud infrastructure:

- creator-api
- postal-brain
- publish-worker
- analytics-worker
- discord-bot
- mcp-gateway

Use Docker Compose or native services depending on which is easier to maintain on the host.

### Phase 3 — optional dedicated local host

If streaming performance becomes affected, move background services to another machine on the LAN/home server. The architecture stays identical; only service addresses change.

## Cost-control rules

1. No managed database unless there is a demonstrated need.
2. No paid object storage for primary VOD storage.
3. No paid queue service.
4. No paid hosted dashboard.
5. No paid serverless functions when a local endpoint works.
6. No continuous frontier-model analysis of raw streams.
7. OpenAI calls require purpose, model routing and usage accounting.
8. Set hard API spend limits and warning thresholds.
9. Prefer direct social platform APIs over third-party posting SaaS.
10. Prefer one Cloudflare Tunnel with multiple routes instead of additional hosted services.

## Immediate implementation changes

- Add Postal Brain budget tracking and local-only fallback.
- Add FastAPI brain status/ask/digest endpoints.
- Emit AutoClip lifecycle events into Postal Brain.
- Add local MCP gateway.
- Add Cloudflare Tunnel deployment/config documentation.
- Add dashboard controls for AI budget and autonomy.
- Keep SQLite for now; do not introduce PostgreSQL until SQLite is actually limiting us.
