# Postal AutoClip v0.4

A clean-room, local-first automatic VOD clipper for long gaming streams, tuned for OSRS and RuneLite. It watches OBS recordings, transcribes locally, scans gameplay/audio, learns from Keep/Great/Reject decisions, and renders captioned 9:16 Shorts without requiring a facecam.

v0.4 adds the editing layer: source-VOD scrubbing, editable clip boundaries, multiple output lengths, smarter OSRS-focused reframing, upgraded captions, and conservative dead-air cleanup.

## v0.4 highlights

- No facecam requirement.
- Browser clip editor using the original source recording.
- Scrub the VOD and set exact clip start/end points.
- Preview the selected range before saving.
- Render three variants from one candidate:
  - Short: 22 seconds
  - Medium: 38 seconds
  - Long: 58 seconds
- Render All button for all three versions.
- Each render is tracked separately instead of overwriting the previous export.
- New `osrs_focus` vertical layout.
- Event-aware focus modes:
  - combat/PvP/big hit -> center combat area
  - drops/raid rewards/collection log -> chat/reward area
  - strong UI/inventory activity -> right-side interface
  - otherwise -> general center gameplay
- The full RuneLite frame remains visible for context while a second focus panel enlarges the important area.
- Conservative dead-air trimming for speech/reaction/chat clips.
- PvP, drops, raids, big hits, and gameplay-heavy events remain continuous by default.
- Tighter word-synced ASS captions with emphasis and pop animation.
- Existing RuneLite event bridge, visual analysis, audio analysis, transcription, and personalized ranking remain intact.

## Pipeline

`OBS recording + optional RuneLite events -> audio/video scan -> Whisper -> exact event alignment -> candidate scoring -> personal ranking -> browser editor -> OSRS-aware 9:16 render -> 22s / 38s / 58s exports`

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

`http://127.0.0.1:8787`

The installer attempts to install FFmpeg with `winget` if FFmpeg is missing.

## OBS workflow

Set `watch_folder` in `config.json` to your OBS recording folder, for example:

```json
"watch_folder": "D:/OBS/Recordings"
```

When OBS finishes a supported recording, Postal AutoClip can queue it automatically.

Supported source extensions include `.mkv`, `.mp4`, `.mov`, `.webm`, `.m4v`, and `.ts`.

## Editing a candidate

1. Let Postal AutoClip analyze the recording.
2. Open a candidate from the dashboard with **Edit Timing**.
3. Scrub the original source VOD.
4. Use **Set Start = Playhead** and **Set End = Playhead** or type exact seconds.
5. Use **Preview Range** to review the selection.
6. Save the timing.
7. Render Short, Medium, Long, or all three.

Editing the timing clears the tracked render records for that candidate so new exports are tied to the new range. Old files are not automatically deleted from disk.

## OSRS-aware vertical layout

The default layout is now:

```json
"layout": "osrs_focus"
```

Instead of blindly center-cropping RuneLite, v0.4 keeps a full-game view and adds a zoomed focus panel selected from the candidate type and visual features.

You can still use `blur_fit` or `center_crop` in `config.json`.

## Render variants

Default lengths:

```json
"render_variants": {
  "short": 22,
  "medium": 38,
  "long": 58
},
"primary_variant": "medium"
```

If a candidate is already shorter than the target length, Postal AutoClip keeps the available range instead of padding fake footage.

## Dead-air trimming

Enabled by default:

```json
"dead_air_trim_enabled": true,
"dead_air_padding_seconds": 0.55,
"dead_air_min_clip_seconds": 6.0
```

This only tightens speech-like candidates such as reactions and chat-heavy moments. It intentionally avoids cutting the middle out of gameplay-heavy events where context and continuous action matter.

## Captions

Useful v0.4 caption settings:

```json
"caption_font": "Arial",
"caption_font_size": 76,
"caption_words_per_group": 4,
"caption_margin_v": 205,
"caption_emphasis_scale": 118,
"caption_uppercase": true
```

Words associated with reactions, rare drops, PvP, and major OSRS moments receive extra visual emphasis while retaining word-level timing.

## RuneLite companion bridge

The optional source project is in:

`runelite-companion/`

Default endpoint:

`http://127.0.0.1:8787/api/game-events`

Default local bridge token:

`postal-local`

This must match `runelite_bridge_token` in `config.json`.

The companion can provide exact event timing for loot, PK/player loot, collection-log messages, deaths, big hits, and selected important game messages. Postal AutoClip then combines those events with the surrounding video, audio, transcript, and learned preferences.

The RuneLite companion is optional. Video/audio/transcript analysis still works without it.

## Test the bridge

Start Postal AutoClip and run:

```powershell
.\test_bridge.ps1
```

The dashboard should receive the test event.

## Learning your taste

- **Keep** = good clip
- **Great** = strong positive example
- **Reject** = bad/uninteresting clip

After enough decisions, the local preference model changes future candidate ranking. Nothing needs to leave your PC for this step.

## Optional Ollama second pass

Set an installed local Ollama model in `config.json`:

```json
"ollama_model": "your-local-model-name"
```

The local second pass can score hook/context/payoff and suggest a title. If Ollama is not installed, the deterministic pipeline continues normally.

## Output

Rendered files go to:

`data/output/`

v0.4 output filenames include the render variant, for example:

`0012_short_example_title.mp4`

`0012_medium_example_title.mp4`

`0012_long_example_title.mp4`

## Development tests

Install the optional dev dependency and run:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

## Known limitations

- The focus panel uses OSRS-aware heuristics and event categories; it is not yet object tracking every individual item or player on every frame.
- Source-VOD editing works through the local dashboard and depends on the browser being able to seek the source container/codec.
- OBS start-time alignment prefers media creation metadata and otherwise estimates from file modified time and duration.
- Exact RuneLite events are available only when Postal AutoClip and the companion can communicate during the session.
- Direct TikTok/YouTube/Instagram publishing is not included yet.
- Public RuneLite Plugin Hub distribution would require the normal RuneLite review/submission process.

## Privacy

Everything is local by default: source VODs, transcripts, video features, RuneLite event metadata, feedback, edits, ranking, and renders. The default dashboard and bridge bind to `127.0.0.1`.
