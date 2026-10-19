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

## Important constraint

Reference performance is inspiration and validation data, not a formula for copying a creator's voice, branding, captions, or edits. Postal AutoClip should learn the structural properties of strong OSRS clips while producing creator-specific outputs.
