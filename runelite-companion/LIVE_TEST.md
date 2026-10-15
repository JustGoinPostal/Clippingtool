# Postal AutoClip RuneLite Companion - Live Verification

This is the final test before treating the RuneLite bridge as production-ready.

## What this test proves

A successful Java compile proves that the plugin matches the current RuneLite API. It does **not** prove that live OSRS events fire exactly as expected on your account. Only an in-game test can confirm that.

Postal AutoClip never automates game input. The companion only observes RuneLite events and sends local metadata to `http://127.0.0.1:8787`.

## 1. Start Postal AutoClip

Start the normal Postal AutoClip application first. Open:

- Main UI: `http://127.0.0.1:8787/`
- RuneLite monitor: `http://127.0.0.1:8787/static/runelite.html`

Leave the RuneLite monitor open during the test.

## 2. Jagex Account development login

RuneLite's official development flow for a Jagex Account is:

1. Make sure the RuneLite launcher is 2.6.3 or newer.
2. On Windows, open **RuneLite (configure)** from the Start menu.
3. Add `--insecure-write-credentials` to **Client arguments** and save.
4. Launch RuneLite once through the Jagex Launcher.
5. RuneLite writes temporary launcher credentials to `%USERPROFILE%\.runelite\credentials.properties`.
6. Close that RuneLite client.
7. Launch the Postal companion development client.

**Never share `credentials.properties`.** It is an authentication credential. After testing, remove `--insecure-write-credentials` and delete the credential file if you no longer need development login. If you ever need to invalidate it immediately, end your RuneScape/Jagex account sessions.

Official RuneLite guide: `https://github.com/runelite/runelite/wiki/Using-Jagex-Accounts`

## 3. Launch the companion

### Packaged artifact

Download the latest successful **Build RuneLite Companion** GitHub Actions artifact, extract it, and double-click:

`run-windows.bat`

The package contains the runnable development-client JAR with Postal AutoClip Companion already loaded.

### Source checkout

If you are developing from the repository directly, run the Gradle `run` task from `runelite-companion`. It starts RuneLite with `--developer-mode --debug` and loads `PostalAutoClipPlugin` as a builtin external plugin.

## 4. Connection check

Within roughly 30 seconds of entering the game, the RuneLite monitor should show:

`CONNECTED`

The companion sends `bridge_online` on startup and a `bridge_heartbeat` approximately every 50 game ticks. If the monitor does not connect, confirm Postal AutoClip is listening on port `8787`, the companion endpoint is `http://127.0.0.1:8787/api/game-events`, and the bridge token matches AutoClip's `runelite_bridge_token`.

## 5. Golden-path gameplay tests

Perform these naturally in game. Do not use macros or automated input.

### Incoming big hit

Take a hit at or above the configured big-hit threshold.

Expected event: `big_hit_taken`

Expected payload characteristics:

- `target_local: true`
- `attributed_to_local: false`
- correct damage amount

It must **not** appear as `big_hit`.

### Outgoing big hit

Deal a hit at or above the threshold to an NPC or player.

Expected event: `big_hit`

Expected payload characteristics:

- `target_local: false`
- `attributed_to_local: true`
- correct damage amount
- target name/type when RuneLite exposes it

A nearby player's hit must not be credited to you.

### Your own death

Die normally.

Expected event: `player_death`

Expected payload characteristic: `local_player: true`.

### PvP kill attribution

Kill another player after dealing the final/recent damage yourself.

Expected event: `pvp_kill`

Expected payload characteristics:

- correct dead-player name
- `attributed_to_local: true`
- recent locally-owned damage recorded
- `ticks_since_local_damage` inside the configured attribution window

Important negative case: if a different nearby player dies and you did not recently damage that exact player, **no** `pvp_kill` should be emitted for them.

### Loot

Receive normal NPC loot above the configured minimum value.

Expected event: `npc_loot` or `loot`.

Verify item ID, item name, quantity, estimated unit price, total value, and source where available.

### Raid reward / unique

When practical, complete CoX, ToB, or ToA and inspect the reward.

Expected: a `loot`, `rare_drop`, `raid_complete`, `collection_log`, or normalized `raid_reward` event depending on the exact RuneLite source. AutoClip's Python normalizer turns raid-related loot into `raid_reward` for scoring when the payload/source identifies a raid.

## 6. PASS criteria

The bridge is live-test approved when all of these are true:

- heartbeat remains connected while RuneLite is open;
- outgoing big hits are yours, not other players';
- incoming big hits never become outgoing big-hit events;
- your death is recognized;
- PvP kills require a recent confirmed hit on the exact dead player;
- unrelated nearby deaths do not become your kills;
- loot payloads contain usable item/source/value information;
- no gameplay action is automated or altered by the plugin.

If one event is wrong, copy the event payload shown in the RuneLite monitor and reproduce only that event. The payload gives enough information to patch the attribution rule without guessing.
