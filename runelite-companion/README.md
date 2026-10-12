# Postal AutoClip RuneLite Companion

This optional companion makes Postal AutoClip game-aware instead of relying only on video inference.
It sends **only local gameplay event metadata** to `http://127.0.0.1:8787` by default. No VOD, password,
Jagex credential, chat history, or account token is uploaded anywhere.

Events currently surfaced:

- NPC loot
- player/PK loot
- Loot Tracker reward events (raids, chests, etc.)
- collection-log messages
- local-player / actor deaths
- big hits above the configured threshold
- selected rare-drop / raid-completion chat messages

The bridge is optional. Postal AutoClip still works with its audio/transcript/vision detector when this plugin is not running.

## Development install

RuneLite recommends Plugin Hub development for new plugins. Open this folder as a Gradle project in IntelliJ,
run it with a compatible RuneLite plugin-development setup, then enable **Postal AutoClip Companion**.

The default bridge token is `postal-local`. It must match `runelite_bridge_token` in Postal AutoClip `config.json`.

For a normal public Plugin Hub install, submit the plugin through RuneLite's review process. Because this plugin communicates
with a local third-party service, any future Plugin Hub submission should clearly disclose the local request behavior.
