---
id: 62
title: Capture route for the standalone Unreal TFT client
labels: [implementation:task, bug]
status: open
assignee:
parent: 34
blocked_by: []
---

# Capture route for the standalone Unreal TFT client

TFT now runs in its own client, `TFTClient-Win64-Shipping.exe` (build `rls-18.4.0 … Set18FullPC`), instead of the League game process. The first Windows probe game on 2026-10-20 (`probe/out/2026-10-20_191350`, ignored; 2560×1440, ranked, EUNE, en_US) shows which parts of the capture route still hold.

## Observations

- **LCU still works.** `/lol-gameflow/v1/session` returns `gameData.gameId`, `queue.gameMode="TFT"`, `type="RANKED_TFT"` and `map.gameMode="TFT"`, so positive TFT identification is unchanged. `/lol-end-of-game/v1/tft-eog-stats` returns all eight players and `localPlayer.ffaStanding` after the game. The game client posts end-of-game stats, early exit and a session event into the LCU at game end, and nothing during the game.
- **No local game API.** Port 2999 (Live Client Data API) was closed in all 2835 polls. The game processes were not listening on any port 9 seconds into the game, and `%LOCALAPPDATA%\TFT\Saved\Logs\TFT.log` shows no local server. A mid-game listening-port check is still pending. Screen capture is the only in-game source.
- **Game configuration moved.** The new client stores settings in Unreal's `%LOCALAPPDATA%\TFT\Saved\Config\WindowsClient\GameUserSettings.ini` (`ResolutionSizeX/Y`, `FullscreenMode`). There is no `[HUD] GlobalScale`. `HudLayout.from_config` requires League's `game.cfg` with that key, so `settings.toml` `game_config` has no valid target for this client.
- **HUD geometry partly moved.** The committed probe-reference regions came from the old client. On the new client, the bottom HUD (level, xp, odds, gold, streak, shop), traits and player list still line up at 2560×1440. The top-bar `stage` and `timer` boxes land on the round icons instead. Measured replacements, in pixels: `stage` `(985,0,1090,50)` and `timer` `(1510,0,1556,56)`. Tighter crops fail because the RapidOCR detector needs margin, and a wider timer box picks up the clock icon.
- **Own player row is never identified.** The new player list shows the owner as an avatar with HP and no name tag, so `is_self` is never set (0 of 61 sampled frames).

With a draft regions-only profile using the measured boxes, `tft-capture inspect` with real RapidOCR on 61 frames sampled about once a minute read `round` in 49 (a clean 2-2 to 6-1 sequence), gold in 46, level/xp/odds/player rows in 45, and streak/timer in 42. The unread frames were loading, dimmed-modal and transition frames. `phase` was never read because the draft has no signal templates.

## Acceptance

- The owner's player row is identified on the standalone client without a visible name tag, and `is_self` is set only on positive evidence.
- `game_config` accepts the standalone client's configuration, records its window mode, and handles the absent HUD scale explicitly rather than guessing.
- The probe-reference stage and timer geometry is corrected for the new client, or the reason to keep both clients' geometry is recorded. Old-client references remain only if that client is still supported.
- Phase signal templates are cropped from real new-client frames and reviewed by the owner before use.
- The probe, handoff and runtime-boundary documents name the new process, config path and the absence of port 2999.
- A mid-game listening-port check of the TFT processes confirms or refutes that the client exposes no local API.
