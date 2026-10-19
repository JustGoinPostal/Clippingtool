# Postal AutoClip OSRS Golden Benchmark

This directory is for **labels and metrics**, not redistributed creator videos.

The production-quality benchmark should be built from recordings the creator owns or has permission to use. Public Odablock, Westham, Dino, Torvesta, B0aty and competitive-event clips are useful as structural references for pacing/payoff patterns, but their media should not be copied into this repository as training or test assets without permission.

## Required corpus coverage

A release-quality corpus should deliberately include both wins and boring/false-positive traps:

- PvP: ordinary kills, high-value kills, smites with spoken corroboration, specs, multi-hit stacks, tank tests, close escapes, failed escapes and deaths.
- Raids: CoX/Olm, ToB rooms/Verzik, ToA paths/Wardens, purple/reward reveals, deaths/wipes and PBs.
- PvM: Inferno/Zuk, Colosseum/Sol, DT2 bosses, Nex, Vorkath, Zulrah, CG and other boss kills/deaths.
- RNG: pets, collection-log slots, uniques, ordinary loot that must **not** be promoted, dry streak reactions.
- Achievements: combat tasks, 99s, total-level milestones, quests and personal bests.
- Personality: funny/reaction moments that have no RuneLite payoff event.
- Negative sections: bankstanding, ordinary skilling, travel, AFK/silence, repetitive chat and harmless visual spikes.

## Label format

Each owned recording should have a JSON payload that can be passed to `python -m app.benchmark`:

```json
{
  "top_k": 3,
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
  ],
  "predictions": []
}
```

`weight` expresses creator importance, not expected views. A major payoff such as a pet, huge PK or raid unique can be weighted more heavily than an ordinary but still clip-worthy moment.

## Metrics

`app.benchmark` measures:

- recall and weighted recall
- precision
- top-K label recall
- duplicate candidate rate
- false-positive rate
- boundary IoU / start/end error
- event-type accuracy

The detector should be judged by all of them. Maximizing recall by producing hundreds of clips is not acceptable, and maximizing precision by finding only obvious purple drops is not acceptable either.

## Regression gate

After a corpus is stable:

```powershell
python -m app.benchmark .\benchmarks\postal_session_01.json --output .\benchmarks\current.json
python -m app.benchmark_gate .\benchmarks\current.json --baseline .\benchmarks\accepted_baseline.json
```

A tuning change should not be merged if the gate reports a meaningful regression. `app.benchmark_gate` also contains conservative bootstrap floors so a tiny or broken detector cannot appear healthy just because no accepted baseline exists yet.

## Release discipline

1. Label moments before tuning against that recording when practical.
2. Keep a held-out subset that is not used while changing weights/rules.
3. Record the accepted metrics and commit the small JSON result, not private VOD/transcript data.
4. Compare every detection/framing change against the same corpus.
5. Add new failure cases whenever a creator finds a missed or embarrassing clip.
6. Never lower a benchmark threshold just to make a release green without documenting why the product behavior is genuinely acceptable.
