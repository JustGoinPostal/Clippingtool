# Postal AutoClip OSRS Golden Benchmark

This directory is for **labels, manifests and small metric reports**, not redistributed creator videos.

The production-quality benchmark must be built from recordings the creator owns or has permission to use. Public Odablock, Westham, Dino, Torvesta, B0aty and competitive-event clips are useful structural references for pacing/payoff patterns, but their media must not be copied into this repository as training or test assets without permission.

## Commercial release rule

A detector/editing change is not "better" because a few demos look good. Before creator-ready v1.0, Postal AutoClip needs a stable private golden corpus with a **tuning split** and a **held-out split**. The held-out recordings are the release truth and should not be watched repeatedly while tuning weights/rules.

`corpus.example.json` is the bootstrap coverage contract. Its initial minimums are deliberately meaningful rather than tiny: 60 total labeled moments, 24 held-out labels, at least two held-out sessions and required OSRS event families. Increase those numbers as the corpus grows; do not lower them merely to make a release green.

## Required corpus coverage

A release-quality corpus should deliberately include both wins and boring/false-positive traps:

- PvP: ordinary kills, high-value kills, smites with spoken corroboration, specs, multi-hit stacks, tank tests, close escapes, failed escapes and deaths.
- Raids: CoX/Olm, ToB rooms/Verzik, ToA paths/Wardens, purple/reward reveals, deaths/wipes and PBs.
- PvM: Inferno/Zuk, Colosseum/Sol, DT2 bosses, Nex, Vorkath, Zulrah, CG and other boss kills/deaths.
- RNG: pets, collection-log slots, uniques, ordinary loot that must **not** be promoted, dry streak reactions.
- Achievements: combat tasks, 99s, total-level milestones, quests and personal bests.
- Personality: funny/reaction moments that have no RuneLite payoff event.
- Negative sections: bankstanding, ordinary skilling, travel, AFK/silence, repetitive chat and harmless visual spikes.

## 1. Label an owned VOD

Keep labels in a private/untracked directory such as `benchmarks/private/`. A labels file can be a list or an object containing `labels`:

```json
{
  "labels": [
    {
      "id": "tob_verzik_death_001",
      "start": 412.0,
      "end": 438.0,
      "event_type": "player_death",
      "weight": 1.4
    },
    {
      "id": "purple_reveal_001",
      "start": 912.5,
      "end": 936.0,
      "event_type": "raid_reward",
      "weight": 2.0
    }
  ]
}
```

`weight` expresses creator importance, not expected views. A pet, huge PK or raid unique can carry more weight than an ordinary but still clip-worthy moment.

## 2. Process the VOD normally, then export predictions

After AutoClip finishes the recording, use its job id:

```powershell
python -m app.benchmark_export --job-id 12 `
  --labels .\benchmarks\private\postal_tob_001.labels.json `
  --output .\benchmarks\private\postal_tob_001.case.json
```

The exported case contains label windows and clip prediction metadata only. It intentionally omits source paths, VOD bytes and transcripts so benchmark artifacts do not become a privacy leak.

## 3. Add the case to the private corpus manifest

Copy `corpus.example.json` to an untracked `benchmarks/private/corpus.json` and point each session at its case file. Every session must have a unique id and a split of `tuning` or `heldout`.

Do not move held-out sessions into tuning just because a change misses them. A miss is evidence that the product needs work.

## 4. Run the whole corpus

```powershell
python -m app.benchmark_corpus .\benchmarks\private\corpus.json `
  --output .\benchmarks\private\current_report.json `
  --fail-gate
```

The corpus runner calculates exact micro-aggregated metrics across sessions rather than averaging rounded percentages. It also verifies corpus coverage requirements.

After accepting a production baseline, compare future held-out results against it:

```powershell
python -m app.benchmark_corpus .\benchmarks\private\corpus.json `
  --baseline .\benchmarks\accepted_corpus_baseline.json `
  --output .\benchmarks\private\current_report.json `
  --fail-gate
```

Only the small accepted metric report belongs in Git. Private cases, labels and media should remain private.

## Metrics

`app.benchmark` / `app.benchmark_corpus` measure:

- recall and weighted recall
- precision
- top-K label recall
- duplicate candidate rate
- false-positive rate
- boundary IoU / start/end error
- event-type accuracy
- exact raw counts and weights used to produce every aggregate metric

The detector must be judged by all of them. Maximizing recall by producing hundreds of clips is not acceptable, and maximizing precision by finding only obvious purple drops is not acceptable either.

## Release discipline

1. Label moments before tuning against that recording when practical.
2. Keep held-out sessions out of day-to-day tuning decisions.
3. Do not commit private VODs, transcripts, local paths or creator-private benchmark cases.
4. Compare every meaningful detection/boundary change against the same corpus.
5. Add new failure cases whenever a creator finds a missed or embarrassing clip.
6. Never lower a threshold or coverage requirement merely to make a release green; document any legitimate product-driven threshold change.
7. A green unit-test suite is not a replacement for a green held-out corpus.
