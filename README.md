# Postal AutoClip v0.3

A clean-room, local-first automatic VOD clipper for long gaming streams, tuned for OSRS and RuneLite. It watches OBS recordings, transcribes locally, scans gameplay/audio, learns from your Keep/Great/Reject decisions, and renders 9:16 captioned Shorts.

v0.3 adds an **optional RuneLite companion bridge** so important OSRS events can be detected from the game client itself instead of guessed only from pixels.

## v0.3 highlights

- No facecam requirement.
- Exact RuneLite event bridge on localhost.
- NPC loot detection with a configurable minimum estimated value.
- Player/PK loot detection.
- Loot Tracker reward-event support for raids/chests/other tracked rewards.
- Collection-log message detection.
- Local-player and other-player death detection.
- Big-hit detection with configurable threshold.
- Wall-clock alignment from RuneLite events to the finished OBS recording.
- Exact game events are merged with audio, transcript and visual signals.
- Visual detector now also tracks center-screen changes, gold/reward colors and red/damage-color bursts.
- Exact events become a learnable preference signal.
- Long sessions are protected from event spam by temporal clustering and seed limits.
- Scores shown in the dashboard are capped at 100.

## Pipeline

`RuneLite event metadata + OBS recording -> audio scan + gameplay scan + Whisper -> time alignment -> OSRS event seeds -> smart clip boundaries -> de-dup/diversity -> personal ranking -> optional local AI -> review -> vertical render`

The RuneLite companion is optional. Without it, Postal AutoClip continues to work using transcript, audio and video analysis.

## Install Postal AutoClip on Windows

1. Install Python 3.11 or 3.12.
2. Extract this folder.
3. Open PowerShell in the folder.
4. Run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
.\launch.ps1
```

Dashboard: `http://127.0.0.1:8787`

The installer also attempts to install FFmpeg with winget if it is missing.

## OBS workflow

Set `watch_folder` in `config.json` to your OBS recording folder, for example:

```json
"watch_folder": "D:/OBS/Recordings"
```

When OBS finishes a `.mkv`, `.mp4`, `.mov`, `.webm`, or `.ts` recording, Postal AutoClip can queue it automatically.

## RuneLite companion bridge

The optional source project is in:

`runelite-companion/`

Its default endpoint is:

`http://127.0.0.1:8787/api/game-events`

The default local bridge token is:

`postal-local`

This must match:

```json
"runelite_bridge_token": "postal-local"
```

in Postal AutoClip's `config.json`.

### What the companion sends

Only small event metadata objects to localhost, such as:

- event timestamp
- event type
- loot item id/name/quantity and estimated local RuneLite price when available
- loot source
- hit amount for big hits
- selected important game messages

It does **not** send your Jagex credentials, RuneLite credentials, VOD, microphone audio, password, or account token.

### Events used by v0.3

- `npc_loot`
- `player_loot`
- `loot`
- `collection_log`
- `rare_drop`
- `raid_complete`
- `actor_death`
- `big_hit`

Postal AutoClip normalizes these into categories such as `raid_reward`, `pvp_kill`, `player_death`, `rare_drop`, and `big_hit`.

### Why this is more accurate

Video-only analysis can notice that something purple appeared or the inventory changed, but it cannot always know *what happened*. The RuneLite bridge can identify the exact event time; Postal AutoClip then checks the surrounding video, audio and transcript to decide whether it is worth clipping.

For example:

`RuneLite says Twisted bow loot at 02:14:31 -> transcript hears a reaction -> audio spikes -> purple visual detected -> candidate score rises -> clip starts before the chest opens and ends after the reaction`

## Test the bridge without RuneLite

Start Postal AutoClip, then run:

```powershell
.\test_bridge.ps1
```

The dashboard's **RuneLite game-event bridge** panel should show a test event. This verifies the local API before you install the companion plugin.

## Visual detection

The camera-free video pre-scan currently tracks:

- overall gameplay change
- lower-left chatbox activity
- right-side inventory/UI activity
- center-screen popup/change activity
- purple/magenta reward-like bursts
- gold/reward-like color bursts
- red/damage-like color bursts

These remain heuristic signals. The companion bridge is the higher-confidence path.

## Learning your taste

Use:

- **Keep** = good clip
- **Great** = very strong positive example
- **Reject** = bad/uninteresting clip

After enough decisions, Postal AutoClip learns which feature combinations you tend to keep. v0.3 includes exact RuneLite events as one of those features, so it can learn whether you care more about drops, PK moments, reactions, visual action, and so on.

Nothing is uploaded for this learning step.

## Optional Ollama second pass

Set an installed local Ollama model in `config.json`:

```json
"ollama_model": "your-local-model-name"
```

If configured, top candidates can receive a local second-pass judgment for hook, context and payoff, plus a title suggestion. If Ollama is missing or unavailable, the deterministic pipeline continues normally.

## Useful config values

```json
{
  "video_sample_seconds": 2.0,
  "big_hit_threshold": 35,
  "runelite_bridge_enabled": true,
  "runelite_bridge_token": "postal-local",
  "max_candidates": 20,
  "diversity_per_type": 6
}
```

The RuneLite companion also has its own `big hit` and NPC-loot minimum-value settings.

## Output

Rendered clips go to `data/output/`.

The default `blur_fit` layout preserves the whole OSRS game image instead of blindly center-cropping away the inventory/chatbox.

## Known limitations

- Exact RuneLite events are captured only while Postal AutoClip is running and the companion can reach localhost.
- OBS start-time alignment prefers media creation metadata and otherwise estimates start time as `file modified time - duration`.
- A public RuneLite Plugin Hub install would require the normal RuneLite review/submission process. The included companion project is source for local development/sideload testing.
- Visual OSRS recognition is intentionally heuristic until a RuneLite event exists for the moment.
- Direct TikTok/YouTube/Instagram publishing is not included in v0.3 yet.

## Privacy

Everything is local by default: VODs, transcripts, video features, RuneLite event metadata, feedback, ranking and renders. The default bridge listens only on `127.0.0.1`.
