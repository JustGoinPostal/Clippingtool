# OSRS clip reference research

This document records public reference material used to design Postal AutoClip's OSRS-specific research workflow. It stores observations and links only. It does **not** bundle, redistribute, or train on copies of other creators' media.

Checked: 2026-10-18/19.

## Reference creators / ecosystems

Popular OSRS creators and competitive ecosystems remain useful **market/reference targets** for public metadata research, including Odablock, B0aty, Westham, Dino_xx, Torvesta and DMM/All Stars content. Their ordinary public uploads are not presumed to authorize frame-level structural analysis or redistribution.

Starter public metadata-only examples are stored in `references/osrs_public_metadata_seeds.json`.

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
2. the creator/rightsholder has explicitly granted permission and that permission has a recorded audit basis.

Those references may contain AutoClip's **derived annotations**, such as:
- hook time
- setup time
- payoff time
- reaction tail
- presence of facecam / burned captions / zooms / hard cuts
- AutoClip-defined hook/payoff archetypes

The source video itself still does not belong in this repository unless the rights grant explicitly allows that use.

### Why the separation is enforced in code

`app/public_reference.py` rejects timing/edit annotations for `metadata_only` references. `creative_commons` mode requires the verified Creative Commons license value. `permission` mode requires both explicit permission confirmation and a non-empty `rights_basis` audit reference. This prevents a future developer from accidentally turning a list of public links into an unlicensed training/test corpus.

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

## Research discipline

### Metadata can form hypotheses, not product truth

High-view public videos can suggest useful questions: Do strong OSRS uploads skew toward direct event-specific titles? Which categories are common? What durations appear repeatedly? How much does public engagement vary across categories?

Those observations are **not** allowed to directly retune AutoClip. Channel size, upload age, existing audience and many hidden factors confound public performance data.

Any detector, boundary, framing, hook or ranking change inspired by public research must still be evaluated against the private held-out golden-VOD corpus before it is accepted.

### Structural observations require reusable rights

For Creative Commons or explicitly permissioned references, structural annotations may be used to test hypotheses such as:
- how early a hook appears
- how far before the payoff setup begins
- how long a reaction tail survives after payoff
- whether zooms/cuts/captions tend to cluster around certain OSRS story types

Even then, AutoClip learns **aggregate structural properties**, not a creator's voice, branding or exact edit.

## OSRS hypotheses already reflected in the product

These are product hypotheses derived from OSRS domain knowledge, creator feedback and permitted/reference research. They must continue to be judged by the private benchmark rather than assumed true forever.

### 1. The payoff belongs in the title
Strong OSRS titles often identify the actual game event: item name, KC milestone, death, PK target, stack, consequence or unusual interaction. Generic titles throw away information the OSRS audience understands immediately.

AutoClip implication: exact RuneLite context should outrank generic transcript wording when generating titles and hooks.

### 2. Different OSRS events want different edit lengths
Reward reveals, direct PK finishes, deaths, raid payoffs, chases/escapes and personality moments do not need identical context windows.

AutoClip implication: event-specific boundary envelopes are preferred over one generic duration rule.

### 3. PKs are stories, not isolated death ticks
The meaningful sequence can be setup -> spec/stack -> death -> loot/reaction.

AutoClip implication: group nearby big-hit, PvP-kill and player-loot telemetry into one canonical story moment rather than clipping only the terminal tick.

### 4. Reward events can duplicate telemetry
One reward may emit loot, rare-drop wording, raid reward/completion and collection-log signals within seconds.

AutoClip implication: collapse overlapping reward signals instead of generating near-identical candidates.

### 5. Personality remains first-class
Exact RuneLite events improve certainty but cannot represent every funny, emotional or socially compelling moment.

AutoClip implication: transcript/audio/reaction discovery remains eligible even with no exact game event.

### 6. Context value matters
A huge-value PK is not equivalent to an ordinary kill; a raid mega-rare, pet or collection-log completion is not equivalent to routine loot.

AutoClip implication: event value, rarity, identity, target, damage and event combinations can feed strength, with caps/normalization so extreme outliers do not permanently dominate creator learning.

## Current implementation

- `app/osrs_story.py`: groups RuneLite events into PK, reward and death story moments and defines event-specific edit envelopes.
- `app/osrs_story_apply.py`: promotes those stories into the final candidate set while retaining personality-only clips.
- `app/hooks.py`: exact OSRS context can generate hooks from item/value/damage instead of generic hype.
- `app/metadata.py`: titles can use item, target, value and damage context.
- `app/benchmark.py`: objective precision/recall/boundary benchmark for labeled VODs.
- `app/public_reference.py`: rights-aware public metadata / structural reference catalog.
- `app/youtube_reference_api.py`: official YouTube Data API metadata + Creative Commons discovery.
- `app/reference_research.py`: local CLI for seeding, refreshing, CC discovery and aggregate reference reporting.

## Important constraint

Reference performance is inspiration and hypothesis generation, not a formula for copying a creator's voice, branding, captions or edits. Postal AutoClip should produce creator-specific output, and any research-inspired behavior must survive the private held-out benchmark before release.
