# Postal AutoClip v0.5

Postal AutoClip is a clean-room, local-first automatic VOD clipper for long gaming streams, tuned for OSRS and RuneLite. It watches OBS recordings, transcribes locally, scans gameplay/audio, learns from Keep/Great/Reject decisions, and renders captioned 9:16 Shorts without requiring a facecam.

v0.5 adds automatic editing polish: opening hooks, event-aware payoff zooms, per-render quality scoring, and automatic best-version selection.

## v0.5 highlights

- No facecam requirement.
- Automatic opening hook text generated locally for every candidate.
- Hooks can be edited or regenerated from the browser editor.
- Hook text is burned into the opening seconds of the Short.
- Event-aware dynamic zoom pulse in the OSRS focus panel.
- Combat moments emphasize the combat area.
- Raid/drop/collection-log moments emphasize the reward/chat area.
- UI-heavy moments emphasize the right-side RuneLite interface.
- Short (22s), Medium (38s), and Long (58s) renders receive separate quality scores.
- Local quality scoring considers:
  - hook readability
  - pacing
  - clip length fit
  - payoff strength
  - context
  - dead air
  - OSRS focus mode
- Render All automatically compares the three outputs and marks the highest-scoring version as **BEST**.
- The BEST render becomes the candidate's primary preview/output automatically.
- All deterministic hook generation and quality scoring are local and require no paid API.

## Pipeline

`OBS recording + optional RuneLite events -> audio/video scan -> Whisper -> exact event alignment -> candidate scoring -> personal ranking -> automatic hook -> browser edit -> OSRS-aware render -> 22s / 38s / 58s quality comparison -> BEST version`

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
2. Open a candidate with **Edit + Scores**.
3. Scrub the original source VOD.
4. Adjust exact start/end boundaries.
5. Edit the generated opening hook if desired.
6. Preview the source range.
7. Render one length or choose **Render All + Pick Best**.
8. Refresh scores to compare outputs.

Changing timing or hook text clears that candidate's tracked render records because the old renders no longer represent the current edit. Existing files already written to disk are not deleted automatically.

## Automatic hooks

Enabled by default:

```json
"auto_hook_enabled": true,
"hook_duration_seconds": 2.8,
"hook_font_size": 68,
"hook_margin_v": 110
```

Hooks are deterministic and event-aware, so they work without Ollama or a cloud model. Examples include PvP, big-hit, raid-reward, rare-drop, collection-log, death, and reaction-specific opening text.

The dashboard lets you overwrite the generated text manually or regenerate it.

## Dynamic OSRS payoff zoom

The default `osrs_focus` layout keeps the full RuneLite frame for context and adds a second focus panel. v0.5 adds a brief zoom pulse around the likely payoff point instead of keeping that panel completely static.

Default settings:

```json
"dynamic_zoom_enabled": true,
"dynamic_zoom_strength": 0.16,
"dynamic_zoom_seconds": 2.6
```

This is event-aware reframing, not per-object computer vision tracking. It chooses a relevant OSRS screen region and emphasizes it near the expected payoff.

## Render variants and BEST selection

Default lengths:

```json
"render_variants": {
  "short": 22,
  "medium": 38,
  "long": 58
},
"primary_variant": "medium",
"quality_scoring_enabled": true,
"best_variant_auto_select": true
```

After a render finishes, Postal AutoClip gives that exact final timing window a local quality score. When multiple variants exist, the highest-scoring render is marked **BEST** and becomes the candidate's primary output.

The quality score is a local editing heuristic, not a promise or prediction of actual views, retention, or virality.

## OSRS-aware vertical layout

The default layout is:

```json
"layout": "osrs_focus"
```

Focus modes include:

- PvP / big hit / death / player loot -> combat area
- drops / raid rewards / collection log -> reward/chat area
- strong inventory/UI activity -> right-side interface
- otherwise -> general center gameplay

You can still use `blur_fit` or `center_crop` in `config.json`.

## Dead-air trimming

Enabled by default:

```json
"dead_air_trim_enabled": true,
"dead_air_padding_seconds": 0.55,
"dead_air_min_clip_seconds": 6.0
```

This tightens speech/reaction/chat candidates only. PvP, drops, raids, big hits, and other gameplay-heavy moments stay continuous so context is not cut out.

## Captions

Useful caption settings:

```json
"caption_font": "Arial",
"caption_font_size": 76,
"caption_words_per_group": 4,
"caption_margin_v": 205,
"caption_emphasis_scale": 118,
"caption_uppercase": true
```

Reaction, PvP, and rare-drop words receive stronger animated emphasis while retaining word-level timing.

## RuneLite companion bridge

The optional companion source is in:

`runelite-companion/`

Default endpoint:

`http://127.0.0.1:8787/api/game-events`

Default local bridge token:

`postal-local`

The companion can provide exact event timing for loot, PK/player loot, collection-log messages, deaths, big hits, and selected important game messages. Postal AutoClip combines those signals with video, audio, transcript, and learned preferences.

The companion is optional. Video/audio/transcript analysis still works without it.

## Test the RuneLite bridge

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

The optional local model can add a second opinion on hook/context/payoff and suggest a title. If Ollama is absent, the deterministic pipeline continues normally.

## Output

Rendered files go to:

`data/output/`

Output filenames include the render variant, for example:

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

- The v0.5 quality score is a deterministic editing heuristic and does not predict social-platform performance.
- Dynamic zoom currently emphasizes the selected OSRS screen region around an estimated payoff point; it is not yet tracking a specific item, hitsplat, player, or NPC frame by frame.
- Source-VOD editing depends on the browser being able to seek the source container/codec.
- OBS start-time alignment prefers media creation metadata and otherwise estimates from file modified time and duration.
- Exact RuneLite events are available only when Postal AutoClip and the companion can communicate during the session.
- Direct TikTok/YouTube/Instagram publishing is not included yet.
- Public RuneLite Plugin Hub distribution would require the normal RuneLite review/submission process.

## Privacy

Everything is local by default: source VODs, transcripts, video features, RuneLite event metadata, feedback, hooks, quality scores, edits, ranking, and renders. The default dashboard and bridge bind to `127.0.0.1`.
