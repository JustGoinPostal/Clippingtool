# OSRS clip reference research

This document records public reference material used to design Postal AutoClip's OSRS-specific editing rules. It stores observations and links only. It does **not** bundle, redistribute, or train on copies of other creators' media.

Checked: 2026-10-18/19.

## Reference creators / ecosystems

- Odablock / Odablock clips and shorts
  - https://www.youtube.com/watch?v=vAqrWtXZ28U
  - https://odablock.com/
  - https://odablock.com/leaderboard
  - https://streamerclips.com/channel/odablock
- B0aty
  - https://streamerclips.com/games/old-school-runescape
  - https://www.twitchmetrics.net/c/27107346-b0aty/clips
- Westham
  - https://www.twitchmetrics.net/c/45887494-westham/clips
- Dino_xx
  - https://www.twitchmetrics.net/c/227217502-dino_xx/clips
- Torvesta / high-level OSRS PvP references
  - https://www.youtube.com/@TorvestaRS
  - https://www.twitchmetrics.net/g/459931-old-school-runescape/clips
- DMM / All Stars competitive clip set
  - https://dmmosrs.com/events/all-stars-season-3/clips

## Rights-aware public-reference policy

Postal AutoClip deliberately separates **public metadata research** from **structural media analysis**.

### Standard YouTube-license/public videos

Public metadata can be used as a market/reference signal:
- video id / public URL
- creator/channel title
- public title
- publish time
- duration
- public view/like counts
- embeddable status
- reported YouTube license
- AutoClip-defined category

These references are `metadata_only`. They must not contain copied descriptions, tags, transcripts, captions, frames, source media, or hook/payoff timing annotations.

### Creative Commons or explicitly permissioned videos

A reference can contribute frame/timing/edit observations only when one of these is true:
1. the official YouTube Data API reports `status.license=creativeCommon`, or
2. the creator/rightsholder has explicitly granted permission and that permission is recorded.

Those references may contain AutoClip's derived structural annotations such as:
- hook time
- setup time
- payoff time
- reaction tail
- presence of facecam / burned captions / zooms / hard cuts
- AutoClip-defined hook/payoff archetypes

The source video itself still does not belong in this repository unless the rights grant explicitly allows that use.

### Why the separation is enforced in code

`app/public_reference.py` rejects timing/edit annotations for `metadata_only` references. `creative_commons` mode requires the verified Creative Commons license value, while `permission` mode requires an explicit permission confirmation. This prevents a future developer from accidentally turning a list of public links into an unlicensed training/test corpus.

## Official YouTube API workflow

`app/youtube_reference_api.py` uses the official YouTube Data API rather than scraping YouTube pages.

Set a local API key outside Git:

```powershell
$env:YOUTUBE_DATA_API_KEY="..."
```

Import public metadata for known references:

```powershell
postal-autoclip-reference fetch https://www.youtube.com/watch?v=VIDEO_ID --category pvp
```

Search specifically for Creative Commons OSRS references:

```powershell
postal-autoclip-reference search-cc --query "Old School RuneScape PvP" --category pvp --max-results 20
```

Generate an aggregate report:

```powershell
postal-autoclip-reference report
```

The local catalog is stored at `data/public_reference_catalog.json` and is Git-ignored. A small checked-in starter list of public **metadata-only** examples lives at `references/osrs_public_metadata_seeds.json`.

Seed it locally with:

```powershell
postal-autoclip-reference seed .\references\osrs_public_metadata_seeds.json
```

## Observed patterns

### 1. The payoff is the title
Strong OSRS clip titles frequently identify the actual game event: item name, KC milestone, death, PK target, stack, DMM consequence, or unusual interaction. Generic titles such as “crazy gaming moment” throw away information the OSRS audience understands immediately.

AutoClip implication: exact RuneLite context should outrank generic transcript wording when generating titles and hooks.

### 2. Different OSRS events want different edit lengths
Public high-view reward examples include clips around 18s, 23s, 30s, 39s and 43s. Competitive PK/death clips frequently cluster around ~29–30s. Chases, escapes and multi-stage competitive stories commonly need ~45–60s or longer source context.

AutoClip implication: do not use one generic boundary envelope for every moment. Reward reveals, direct PK finishes, deaths, raid payoffs and narrative/chase moments require separate profiles.

### 3. PKs are stories, not isolated death ticks
The interesting sequence is commonly setup -> spec/stack -> death -> loot/reaction. A clip beginning exactly at ActorDeath loses why the kill was impressive; a clip ending exactly at death loses loot value and reaction.

AutoClip implication: group nearby big-hit, PvP-kill and player-loot telemetry into one canonical story moment.

### 4. Reward events often duplicate telemetry
A single drop can generate loot, rare-drop wording, raid completion/reward signals and a collection-log message within seconds.

AutoClip implication: collapse those signals into one reward reveal rather than generating multiple near-identical candidates.

### 5. Personality remains first-class
Odablock's public clip catalog includes gameplay, DMM, reactions and personality-driven moments, while B0aty's strongest catalog contains both rare rewards and human/reaction moments.

AutoClip implication: RuneLite exact events should improve ranking, not replace transcript/audio discovery. A funny moment with no game event must still be able to win.

### 6. Context value matters
A kill worth 50M is not the same content opportunity as a routine low-value kill. A Twisted Bow is not the same as ordinary NPC loot. A collection-log completion or pet is not equivalent to a generic item drop.

AutoClip implication: event value, rarity, item identity, target identity, damage stack and event combination should feed moment strength, with caps to avoid one extreme outlier permanently dominating creator learning.

## Current implementation derived from these observations

- `app/osrs_story.py`: groups RuneLite events into PK, reward and death story moments and defines event-specific edit envelopes.
- `app/osrs_story_apply.py`: promotes those stories into the final candidate set while retaining personality-only clips.
- `app/hooks.py`: exact OSRS context can generate hooks from item/value/damage instead of generic hype.
- `app/metadata.py`: titles can use item, target, value and damage context.
- `app/benchmark.py`: objective precision/recall/boundary benchmark for labeled VODs.
- `app/public_reference.py`: rights-aware public metadata / structural reference catalog.
- `app/youtube_reference_api.py`: official YouTube Data API metadata + Creative Commons discovery.
- `app/reference_research.py`: local CLI for seeding, refreshing, CC discovery, and aggregate reference reporting.

## Important constraint

Reference performance is inspiration and validation data, not a formula for copying a creator's voice, branding, captions, or edits. Postal AutoClip should learn the structural properties of strong OSRS clips while producing creator-specific outputs.
