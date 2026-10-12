# Changelog

## 0.4.0

- Added browser-based source-VOD clip editor.
- Added editable candidate start/end boundaries.
- Added source-video scrubbing and range preview from the dashboard.
- Added Short (22s), Medium (38s), and Long (58s) render variants.
- Added Render All workflow and per-variant render tracking.
- Added OSRS-aware `osrs_focus` vertical layout.
- Added combat, chat/reward, right-side UI, and center focus modes.
- Added conservative dead-air trimming for speech/reaction/chat clips.
- Gameplay-heavy PvP/drop/raid clips stay continuous by default.
- Upgraded ASS captions with tighter groups, word timing, emphasis scaling, and pop animation.
- Added v0.4 render/editor configuration values.
- Added v0.4 render-logic smoke tests.
- Facecam remains completely optional/not required.

## 0.3.0

- Added optional localhost RuneLite companion bridge.
- Added game-event database/API and batch endpoint.
- Added OBS recording-time alignment for RuneLite event timestamps.
- Added exact OSRS event scoring for loot, PK loot, collection log, deaths, big hits and raid/reward events.
- Added RuneLite loot-value weighting and event summarization.
- Added exact-event clustering/limits for long sessions.
- Added center-screen, gold/reward and red/damage visual signals.
- Added exact RuneLite event as a preference-learning feature.
- Added dashboard bridge status/recent event panel.
- Added bridge test script.
- User-facing candidate scores now cap at 100.
- Facecam remains completely optional/not required.

## 0.2.0

- Added camera-free visual pre-scan.
- Added chatbox, inventory/UI and purple/reward signals.
- Added smart clip boundaries, de-duplication and event diversity.
- Added Keep/Great/Reject preference learning.
- Added highlight timeline and optional local Ollama second pass.
