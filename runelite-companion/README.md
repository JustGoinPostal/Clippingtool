# Postal AutoClip RuneLite Companion

This optional companion makes Postal AutoClip game-aware instead of relying only on video inference.
It sends **only local gameplay event metadata** to `http://127.0.0.1:8787` by default. No VOD, password,
Jagex credential, chat history, or account token is uploaded anywhere.

Events currently surfaced:

- NPC loot
- player/PK loot
- Loot Tracker reward events (raids, chests, etc.)
- collection-log messages
- confirmed PvP kills
- local-player deaths
- outgoing big hits dealt by the local player
- incoming big hits on the local player as a separate `big_hit_taken` event
- selected rare-drop / raid-completion chat messages
- bridge startup + heartbeat status for live connection monitoring

## Attribution rules

The companion deliberately avoids treating every visible combat event as yours.

- Outgoing damage uses RuneLite's `Hitsplat#isMine()` ownership signal, the same signal used by RuneLite's built-in DPS counter.
- A remote player death only becomes `pvp_kill` when that exact player received confirmed local-player damage within the configured PvP attribution window.
- A nearby player dying without confirmed local damage is ignored instead of becoming a false PvP clip.
- Damage received by the local player is sent as `big_hit_taken`, not `big_hit`, so an enemy spec does not look like your own big spec.
- `PlayerLootReceived` remains useful post-kill/loot context, but player loot by itself is not used as proof that you got the kill.

The default PvP attribution window is 12 game ticks and can be changed in the plugin settings.

The bridge is optional. Postal AutoClip still works with its audio/transcript/vision detector when this plugin is not running.

## Fast live-test path

Every successful **Build RuneLite Companion** GitHub Actions run now produces a downloadable artifact named:

`PostalAutoClip-RuneLite-Live-Test`

It contains:

- a runnable development-client JAR with Postal AutoClip Companion already loaded;
- `run-windows.bat` for Windows;
- `LIVE_TEST.md` with the exact gameplay verification checklist and Jagex Account development-login steps.

Start Postal AutoClip first, extract the artifact, and run `run-windows.bat`.

The local event monitor is:

`http://127.0.0.1:8787/static/runelite.html`

## Jagex Accounts

For a Jagex Account, use RuneLite's official development flow. On Windows, open **RuneLite (configure)**, add
`--insecure-write-credentials` to Client arguments, launch RuneLite once through the Jagex Launcher, then close it and start
the development client. RuneLite writes temporary developer-login credentials to `%USERPROFILE%\.runelite\credentials.properties`.
Never share that file. Remove the launcher argument and delete the credentials file after development testing when you no
longer need it.

Official guide: `https://github.com/runelite/runelite/wiki/Using-Jagex-Accounts`

## Source development

The Gradle project tracks RuneLite `latest.release` and targets Java 11, matching the current RuneLite example-plugin guidance.
Open this folder as a Gradle project in IntelliJ or run the Gradle `run` task. The development client starts with
`--developer-mode --debug` and loads **Postal AutoClip Companion** as a builtin external plugin.

The default bridge token is `postal-local`. It must match `runelite_bridge_token` in Postal AutoClip `config.json`.

The repository includes a GitHub Actions compile/package check for the companion so API incompatibilities are caught when the
RuneLite source or companion changes.

## Local bridge self-test

With Postal AutoClip running from a repository checkout, run:

`python tools/runelite_bridge_selftest.py`

This verifies the HTTP bridge, token, database write, and read-back path. Synthetic events are timestamped at January 1, 2000,
so they cannot overlap a modern OBS recording or become real candidate clips. This test does not replace the live in-game
verification in `LIVE_TEST.md`.

For a normal public Plugin Hub install, submit the plugin through RuneLite's review process. Because this plugin communicates
with a local third-party service, any future Plugin Hub submission should clearly disclose the local request behavior.
