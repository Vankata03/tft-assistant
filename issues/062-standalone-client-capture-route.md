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

## Comments

### 2026-10-20 — Claude

First acceptance item done in `bcd8392`. The players branch of `_parse` in `tft_capture/pipeline.py` claims the owner's row only when it is a lone number, at least 1.4 times the median opponent-HP height, with its right edge at or left of the opponent-HP column, and exactly one such row exists. `test_capture_complete.py` has a positive case and a negative case (a nameless opponent HP in the normal column). On 61 sampled probe frames with the draft profile, own HP read on 39 frames and fell from 85 to 13 consistently with the game.

### 2026-10-20 — Claude

Second acceptance item (`game_config`): the owner chose to establish the HUD scale by measuring frames rather than reading or assuming it. `HudLayout.from_config` now accepts a measured HUD record (`format = "tft-assistant-measured-hud/1"`) that names the standalone client's `GameUserSettings.ini` for window mode and carries the measured scale with its date, client size and method. It records `scale_source = "measured"`. Pointing `game_config` straight at `GameUserSettings.ini` fails with a message asking for the record. Surface geometry accepts `measured` alongside `game-config`.

Measurement: across 61 sampled in-game frames from probe run `2026-10-20_191350`, the median white-text boxes of level, gold and streak equal the 2026-10-04 probe reference frames to the pixel, with 21 px glyph height in both. The scale is therefore 1.0 relative to the reference geometry at 2560×1440. The owner's local record is `%USERPROFILE%\.config\tft-assistant\game\measured-hud-standalone-2560x1440.toml`; it loads the real client settings as `windowed` (`FullscreenMode=2`).

Finding for the stage/timer item: the 2026-10-04 reference frames show the same top-bar layout as the standalone client, with the stage text near x 1025 px. The `_REGIONS` stage and timer rectangles in `layout.py` (stage starting at 1072 px) therefore do not match their own reference frames either. This is a mis-cut reference, not an old-client difference.

### 2026-10-20 — Claude

Third acceptance item (stage/timer geometry): the reference rectangles in `tft_capture/layout.py` are now cut from the 2026-10-04 reference frames, which share the standalone client's top bar. Stage is `(1016,0,1146,50)` px and timer `(1506,0,1556,64)` px at 2560×1440. The top bar narrows in stage 1, so the stage rectangle spans both widths (its parser takes one round match among the icons). The timer covers the stage-2-and-later position only; the stage-1 timer near x 1440–1470 stays unread. Both keep vertical margin because RapidOCR's detector returns nothing on tight crops.

Verification with the bundled RapidOCR on 50 sampled standalone-client frames and the 9 reference frames: stage parsed 56/59, matching every reference filename and progressing monotonically from 2-2 to 6-1. Timer parsed 55/59. A visual check confirmed six frames that read `1`. Misses are the two augment-offer frames (the overlay hides the bar), one frame without the HUD, and the stage-1 timer. The previous draft rectangles parsed stage 55/59 and timer 48/59. The owner's local draft profile now uses the new rectangles.

### 2026-10-20 — Claude

Phase signal, by owner decision: the standalone client's top bar is identical in planning and combat, and the shop is open in both, so neither can carry the phase. The owner chose the enemy side of the board instead. `tft_capture/phase.py` reports `combat` when red health bars appear on the upper half of the owner's board, and `planning` when there are none and the round's first timer countdown is still running from an observed round start. It applies only in own view and in pinned `round_types` `combat` rounds. Everything else leaves the phase unavailable.

Replay over the 2026-10-20 probe's PvP frames, against a timer-reset reference (first countdown is planning, later countdowns are combat): planning frames 663 correct, 16 read as combat, 3 unavailable; combat frames 748 correct, 0 wrong, 182 unavailable (mostly the start-of-combat banner before units spawn and the end of fights after enemies die). The replay did not apply the own-view gate, which should remove scouting frames among the 16. PvE monsters stand on the enemy side during planning, which is why PvE rounds stay unavailable. This replaces the phase templates for PvP rounds; augment, carousel and end states still need their own signals.
