---
id: 9
title: "Game-state capture route"
labels: [wayfinder:grilling]
status: closed
assignee: Ivan Terziev
parent: 1
blocked_by: [2, 3, 13]
---

## Question

Which automatic capture route (or combination) does the coach use, given the field coverage, reliability and policy findings? Decide what happens when a required field is unavailable from the chosen route, since manual entry is ruled out.

## Comments

### 2026-10-04 — claude-code

Input from "Policy stance and feature modes": Live mode may use every field the chosen route exposes, including Overwolf's augment keys and opponent-board keys (`board.opponent_board_pieces`, `match_stats.board_players`). Baseline mode needs augment names during selection for its statistics table, and the stage, shop and own board for Guide steps and shop highlighting. Policy therefore does not rule out any field; route choice can rest on coverage and reliability.

### 2026-10-04 — claude-code

Input from "Advice engine architecture": the Engine runs on the CPU only, with a budget of 100 ms per snapshot, so the GPU is shared only between the game and a vision model if screen capture is chosen. Each sub-engine declares its required fields and stays silent when the route lacks one, so a route gap disables specific advice rather than the coach. "Positioning decisions" is blocked on this ticket because live positioning depends on which opponent boards the route reveals.

### 2026-10-04 — claude-code

Input from "Transition and pivot domain model": contest is counted from each opponent's latest board sighting, plus benches only if the route exposes them. A sighting has full weight for about 2 rounds, then fades and lowers confidence; with no opponent data there is no contested term. The owner accepts scouting every opponent's board each round if a screen-capture route reads scouted boards reliably.

### 2026-10-04 — claude-code

Input from "Board and lobby strength heuristic": the error metrics for board power need, per combat round, the opponent fought, the result, and the player's HP lost. Scouted boards should record items and star levels when visible, because missing fields are imputed at the stage average and lower advice confidence. A route that logs these lets `win_probability` and `surviving_units` be calibrated from fight logs.

### 2026-10-04 — claude-code

Input from "Item decisions": the item sub-engine requires the items on the player's units and the item bench, and stays silent without the item bench. It also reads item offers (anvils, Item-category Wisps) and held removers and Reforgers when the route exposes them. Opponents' items are not used by this sub-engine.

### 2026-10-04 — claude-code

Input from "Augment decisions": the augment sub-engine requires the three offered augment ids, the offer tier, which options still have a reroll, and the augments the player holds. Advice must show within about 2 s of the offer appearing (the selection timer is about 43 s, then 58 s). The Riot match API no longer records augments for Set 18, so capture is the only source of held augments, and the coach's game log must record every offer, reroll and pick for post-game review.

### 2026-10-04 — claude-code

Input from "Shop, Wisp and carousel decisions": the shop and Wisp sub-engines require the shop's champion slots, the offered Wisp's id and cost, gold, board and bench, and the shop's slot count (5, or 4 with a Wisp) on every roll. The carousel sub-engine requires each carousel option's unit and item before the player's pick. A sub-engine whose fields are missing emits nothing.

### 2026-10-04 — claude-code

Input from "Probe live game data sources in a real TFT game": port 2999 is closed during a TFT game, and the League client API gives only the gameflow phase (start, reconnect, end), so the realistic routes are screen capture and Overwolf (not installed on the owner's PC). Borderless GDI capture at 2560×1440 reads every field the sub-engines need as text, including Wisp text, augment names and reroll buttons, and scouted boards. The owner wants scouting captured at about 1.5 s or faster, because a 10 s interval misses scouted boards and rerolls. The game process can crash and restart mid-match, so capture must re-attach. Correction to the augment input above: the selection timer opened at about 48–49 s for all three offers. TFT Academy's approved desktop app already overlays tier letters on live augment, item and Wisp choices and records whole games as video.

### 2026-10-04 — claude-code (resolution)

Resolved with the owner in a grilling session. Two research passes informed it; their findings are summarised below.

**Research findings (checked 2026-10-04).**

- **Overwolf GEP access is not self-serve.** A Console API key needs Console access, which is granted only after Overwolf QA approves a submitted app. `OW_DEV_KEY` needs a DevRel review of an app concept. No current page states a timeline or whether a never-published personal app qualifies. TFT's GEP (game id 21570, all keys green) covers own board, bench and items, the item bench for all players, all boards per stage, the shop, carousel, round type, outcome and opponent. It has no Wisp, Set 18 or streak keys and no opponent benches, and Overwolf forbids using its augment keys. A second TFT id, 28164, has appeared, possibly the new client.
- **How existing apps get live data.** Every Overwolf-hosted TFT app (TFT Academy as ow-electron, MetaTFT, Mobalytics, OP.GG Desktop as ow-electron, Porofessor, MetaBot) uses Overwolf GEP. Apps off Overwolf read the screen: TFTSense (own Electron app, computer vision, live on Set 18) and probably Blitz. Riot documents no live TFT API and no partner feed, and its policy has no rule on screen capture. On 2026-10-06 Riot blocks memory access for unknown apps; approved tools have until April 2027 to move off it. Whether GEP's board data comes from memory is unconfirmed.
- **Reusable screen readers.** [TFT-COACH](https://github.com/mallangmallang0619/TFT-COACH) (MIT, pushed 2026-09-10) has a Set 18 champion classifier (EfficientNet, ONNX), item-icon matching against Riot art, trait-panel reading and Tesseract OCR for the HUD. TFT-Copilot (PolyForm Noncommercial) and wbLoki/tft-coach (no licence) are reference only, so a public build stays possible. Roboflow Universe hosts community TFT datasets.
- **Correction to "Probe live game data sources in a real TFT game".** Units on the board and bench are 3D models with no name label, so they are not readable as text. Star levels are pips, and items are icons. Text covers the HUD, shop, Wisps, augments, carousel, the trait panel, the player list and the scouted player's name.

**Decision.**

1. **Route.** Screen capture only, plus the League client API (LCU) for the game's lifecycle. The owner does not apply for Overwolf developer access (see Out of scope on the map).
   - The LCU gameflow phase marks game start, end and reconnect, and its game id keys the game log.
   - GDI capture of the "TFT" window feeds OCR for the HUD (stage, round, timer, level, XP, odds, gold, streak, all players' names and HP), the shop, Wisp cards, augment cards with tier colour and reroll buttons, carousel options, the trait panel and scouted player names.
   - The own board, the bench and scouted boards come from **purchase tracking** combined with a reused vision model (see 2).
2. **Board reading.** Purchase tracking derives unit identities from shop OCR and gold changes, sells, carousel picks and unit-granting Wisps and encounters, with star levels from copy counts. The trait panel checks it each round. On top of that, TFT-COACH's MIT champion classifier runs per hex on the own board, bench and scouted boards, together with item-icon matching and star-pip reading. It runs on the CPU (onnxruntime), only on frames whose board region changed, so the GPU stays with the game. The vision part is gated by "Benchmark open-source board recognition on probe frames". If accuracy is too low, v1 uses purchase tracking alone, and scouted opponents give traits only.
3. **Cadence.** A change check runs at about 4 Hz on small regions (stage bar, gold, shop strip, choice-card area, board). OCR, vision and the Engine run only on regions that changed, so a roll, Wisp, augment offer or scout is read within about 250–500 ms. Full frames are taken only for keyframes.
4. **Missing, stale and conflicting fields.** Each field keeps its last known value with a timestamp and source. Each sub-engine declares a maximum age per required field; past it the field counts as missing and the sub-engine stays silent. A failed read is never guessed, except for the opponent imputation settled in "Board and lobby strength heuristic". When vision and purchase tracking disagree, vision decides position, star level and items. Unit identity follows vision above a confidence threshold and purchase tracking below it. Every disagreement is logged with a keyframe.
5. **Augments** are read from the screen in both modes, never from any GEP key. Held augments are tracked from the picks.
6. **Game log.** Structured snapshots (every offer, roll, pick, sighting and fight result) are kept forever. Media is a setting: keyframes by default (each shop after a roll, each augment, Wisp and carousel offer, each scouted board, the end of each planning phase; roughly 100–300 MB per game), or full video. Media is capped at 20 GB with the oldest deleted first; the 50 Live-mode evaluation games are pinned.
7. **Display support.** Any aspect ratio (16:9, 16:10, 21:9) and window mode. Screen regions are fractions of the game window, anchored per HUD element. The in-game UI scale is read from the game's config. OCR matches names in the client's locale against Data Dragon and CommunityDragon. A one-round calibration check flags a layout that reads nothing.
8. **Crash and reconnect.** Capture re-scans for the window and continues under the same LCU game id. The missed span is recorded as a gap.
9. **Opponents.** The coach uses whatever boards the player scouts and shows each opponent's sighting age. Whether the coach prompts the player to scout belongs to "Advice surface UX".

**Map changes.** New task "Benchmark open-source board recognition on probe frames", which now blocks "Positioning decisions". "Stack and runtime" and "Advice surface UX" graduate from the fog into tickets. Model retraining per set joins the "Patch cadence" fog. Overwolf joins Out of scope.
