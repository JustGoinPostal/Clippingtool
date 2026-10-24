# Postal Creator OS

## Goal

Postal Creator OS is a local-first, highly automated creator operating system whose normal workflow is:

1. Postal starts streaming.
2. The system observes the stream, chat, OBS, game events, and account metrics.
3. It identifies moments worth keeping and creates publishable edits.
4. It packages and schedules content per platform.
5. It collects performance data and learns what works on each platform.
6. OpenAI acts as the reasoning and decision layer across the system.
7. Postal receives concise updates only when something changed, needs attention, or is worth knowing.

The target is not "AI-assisted editing." The target is a self-operating creator stack that reduces routine creator-management work to nearly zero.

## Operating principles

- Local-first for VODs, transcripts, raw events, account tokens, and private analytics.
- No API keys in config files or Git. Secrets come from environment variables or the existing secrets directory where appropriate.
- Automation by default; approval only for account authorization, destructive actions, or actions explicitly placed behind an approval policy.
- Every automated action is attributable to an event and is logged.
- AI recommendations never silently overwrite source media or credentials.
- Platform learning is separate by platform even when the same clean master clip is cross-posted.
- Cost-aware model routing: cheap/high-volume analysis for routine events; stronger reasoning only when the decision is important.
- Failure isolation: clipping, publishing, analytics, Discord, and OpenAI failures must not take down the stream.

## High-level architecture

```text
OBS / Kick / RuneLite / Discord / Social APIs / Local files
                         |
                         v
                    EVENT BUS
                         |
          +--------------+--------------+
          |              |              |
          v              v              v
      AutoClip       PostalBot      Analytics
          |              |              |
          +--------------+--------------+
                         |
                         v
                    POSTAL BRAIN
                   (OpenAI layer)
                         |
       +-----------------+------------------+
       |                 |                  |
       v                 v                  v
  Decisions         Recommendations      Updates
       |                 |                  |
       v                 v                  v
 Publishing        Content Strategy   ChatGPT/Discord/UI
```

## Postal Brain responsibilities

Postal Brain is a reusable reasoning service, not a UI chatbot. It receives normalized events and produces structured decisions or summaries.

Initial responsibilities:

- Explain noteworthy stream events.
- Score whether an event warrants attention.
- Generate titles, hooks, captions, descriptions, and platform-specific packaging.
- Create post-stream summaries.
- Interpret analytics changes and identify likely causes.
- Recommend the next content action.
- Detect automation failures that need human attention.
- Produce concise notification text.

Later responsibilities:

- Multi-event story detection across a whole stream.
- Live stream co-pilot suggestions.
- Content research with web search where enabled.
- Thumbnail concept generation and image-generation prompts.
- Discord community summaries and moderation assistance.
- Platform scheduling strategy.
- Experiment design and automatic A/B test interpretation.
- Creator memory: recurring jokes, collaborators, series, formats, and audience preferences.

## Event schema

Every module should emit a normalized event.

```json
{
  "event_id": "uuid",
  "created_at": 1792812345.123,
  "source": "runelite",
  "kind": "player_death",
  "priority": "high",
  "stream_id": "optional-stream-id",
  "payload": {},
  "tags": ["osrs", "death"]
}
```

Recommended priorities:

- `debug`: internal telemetry, no AI by default.
- `normal`: stored and available to summaries.
- `high`: eligible for immediate AI analysis.
- `critical`: alert immediately and retain until acknowledged.

## Event sources

### OBS

- stream_started
- stream_ended
- recording_started
- recording_stopped
- scene_changed
- source_muted
- source_unmuted
- dropped_frames_high
- encoder_overload

### Kick / chat

- chat_message
- chat_velocity_spike
- repeated_phrase
- viewer_spike
- follower
- subscription
- gifted_subscriptions
- raid
- moderator_action
- clip_command_spike

### RuneLite / game bridge

- death
- kill
- rare_drop
- raid_started
- raid_completed
- raid_wipe
- boss_kill
- big_hit
- pvp_event
- collection_log

### AutoClip

- candidate_created
- candidate_scored
- render_completed
- render_failed
- publish_queued
- publish_completed
- publish_failed

### Analytics

- analytics_refresh_completed
- clip_outperforming
- clip_underperforming
- retention_anomaly
- follower_conversion_spike
- platform_growth_change

## AI model routing

Do not use the strongest model for every event.

### Fast lane

Use for:

- classification
- short summaries
- title/caption variants
- notification wording
- basic clip analysis

### Reasoning lane

Use for:

- post-stream strategy
- analytics diagnosis
- deciding which content formats to emphasize
- cross-platform conflicts
- experiment analysis
- complex failure recovery recommendations

### Realtime lane

Use only where latency materially improves the stream experience:

- optional live transcription
- optional live co-pilot
- voice interaction
- rapid stream-state interpretation

Routine stream transcription should remain local when local Whisper is sufficient, then send only relevant transcript windows to OpenAI. This controls cost and preserves privacy.

## OpenAI integration map

### Responses API

Primary reasoning interface for Postal Brain.

Use cases:

- event interpretation
- structured decisions
- strategy reports
- copy generation
- tool/function calling into Postal Creator OS

### Function calling

Expose safe creator actions as functions, for example:

- get_stream_status
- get_recent_events
- get_clip
- render_clip
- queue_clip
- get_platform_analytics
- build_distribution_plan
- send_discord_update
- update_stream_metadata

Actions are classified by approval policy.

### Realtime / transcription

Optional second-stage live intelligence. Local transcription remains the default for full VOD processing; Realtime is reserved for features that benefit from low latency.

### Web search

Use for trend/research tasks, not for every stream event. Research jobs should have explicit budgets and cache results.

### Image generation

Use for thumbnail concepts, social graphics, announcements, and branding assets after a content decision is made.

### Background responses + webhooks

Long-running strategy/research jobs may run asynchronously at the API level, with completion delivered back to Postal Creator OS by webhook. The local system should persist a job record so process restarts do not lose work.

## ChatGPT integration

The API-based Postal Brain and ChatGPT are complementary.

### Custom Postal Creator plugin / MCP server

Postal Creator OS should expose a secured MCP server that ChatGPT can connect to. This lets ChatGPT directly inspect and control the creator system instead of requiring copied logs or screenshots.

Initial MCP tools:

- creator_status
- current_stream
- recent_streams
- recent_events
- clips
- clip_detail
- analytics_summary
- platform_summary
- publishing_queue
- failures
- recommendations
- approve_action
- reject_action

Later writable tools:

- render
- schedule
- publish
- change_title
- change_category
- send_discord_message
- update_content_calendar

### ChatGPT scheduled updates

Once the plugin is connected, recurring ChatGPT tasks can request periodic creator summaries. These are ideal for hourly or daily updates that should appear inside ChatGPT.

### Event-triggered updates

Where a connected app supports event-triggered tasks, use them for external events. Postal Creator OS should also publish important alerts to Discord immediately, because ChatGPT scheduled tasks are not a sub-minute notification transport.

### Dot / proactive agent

If available on the account, a dedicated Postal creator dot can use connected creator information, scheduled work, and proactive research as an additional personal-agent surface.

## Notification policy

The system should not spam Postal.

### Immediate

- stream health problem
- account authentication expired
- publishing failure after retries
- viral/outlier content event
- platform policy/API failure affecting automation
- unusually large gifted-sub/revenue event if enabled

### During stream, batched

- high-confidence clip moments
- chat/viewer spikes
- content opportunity suggestions

### Post-stream

Send exactly one primary report containing:

- stream duration
- average/peak viewers if available
- follows/subs/gifts if available
- best detected moments
- clips created
- content queued
- failures
- recommendation for the next stream/content action

### Daily

- platform growth
- best/worst posts
- unusual analytics changes
- queue health
- recommended actions

## Autonomy policy

### Fully automatic

- ingest recordings
- transcribe
- detect candidates
- render variants
- score variants
- gather analytics
- retry transient API failures
- generate drafts
- prepare schedules
- archive low-value intermediate files according to retention policy

### Automatic after account setup

- publish approved/high-confidence content under configured policy
- cross-post
- collect platform metrics
- Discord go-live and post-stream updates

### Approval required by default

- changing connected-account credentials
- deleting published content
- deleting source VODs
- spending above a configured API budget
- mass messaging
- actions that could lock or ban an account
- changing security settings

## Recommended local services

Initially keep this a single Windows-friendly application and split services only when load requires it.

Logical modules:

- `postal_brain` - OpenAI reasoning and decision layer
- `event_bus` - event persistence and subscriptions
- `autoclip` - existing clipping pipeline
- `publisher` - existing posting queue
- `analytics` - existing collectors and learning
- `postal_bot` - Kick/Discord automation
- `obs_bridge` - OBS WebSocket integration
- `creator_mcp` - ChatGPT/MCP interface
- `notifications` - Discord/desktop/ChatGPT update routing

Storage progression:

1. Existing SQLite while single-machine/local.
2. Move event/analytics workloads to PostgreSQL only when scale or remote access makes it useful.
3. Store large media on local disks; database stores metadata and paths, not video blobs.

## Security boundaries

- OpenAI key: `OPENAI_API_KEY` environment variable only.
- Platform credentials remain in ignored secret files or OS credential storage.
- MCP server starts local-only by default.
- Remote MCP exposure requires HTTPS, authentication, and explicit tool allowlists.
- Writable MCP tools must validate parameters and enforce approval policy server-side.
- Never expose raw API keys through the dashboard or MCP responses.

## Cost controls

Track AI usage per stream and per feature.

Configuration should include:

- daily AI budget
- per-stream AI budget
- maximum live requests per minute
- model routing policy
- maximum trend-research calls per day
- whether live Realtime features are enabled

When a soft limit is reached, degrade gracefully to local heuristics instead of stopping the creator pipeline.

## v1 implementation sequence

### Milestone 1 - Postal Brain foundation

- Normalized event model.
- Persistent JSONL event log initially.
- Responses API client.
- AI health/status.
- Manual `ask`/analysis endpoint.
- AI usage/cost telemetry.
- Approval-policy primitives.

### Milestone 2 - AutoClip integration

- Emit job, candidate, render, publish, and analytics events.
- Ask Postal Brain for second-pass clip interpretation only on top candidates.
- Generate platform packaging from the same master clip.
- Produce automatic post-stream report.

### Milestone 3 - Stream telemetry

- OBS WebSocket bridge.
- Kick/chat bridge.
- Chat-velocity and viewer-spike detection.
- Live high-confidence clip markers.

### Milestone 4 - PostalBot + Discord

- Discord creator hub automation.
- Go-live notices.
- Stream summaries.
- Moderator commands.
- `!clip` crowd signal.

### Milestone 5 - ChatGPT control plane

- Local MCP server.
- Read-only tools first.
- Writable tools after validation.
- ChatGPT scheduled creator briefs.
- Optional event-driven integrations where supported.

### Milestone 6 - Content strategy automation

- Trend research.
- Content calendar.
- Long-form VOD story extraction.
- Thumbnail concepts/images.
- Platform-specific strategy model.
- Experiments and automatic interpretation.

## Definition of success

A successful normal day looks like this:

- Postal launches the creator stack once.
- Postal streams.
- Postal does not manually mark timestamps.
- Postal does not manually cut Shorts.
- Postal does not manually copy captions between platforms.
- Postal does not manually check three analytics dashboards.
- Postal receives a concise post-stream summary and only actionable alerts.
- The next day's content queue is already prepared or published according to policy.
- ChatGPT can answer "what happened on stream?", "what should I do next?", and "why did this clip perform well?" directly from the creator system.
