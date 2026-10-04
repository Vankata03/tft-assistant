# Game-state capture

Part of the [MVP spec](../spec.md). Sources: [Automatic game-state capture options for TFT](../../issues/003-game-state-capture-options.md), [Probe live game data sources in a real TFT game](../../issues/013-probe-live-game-data.md), [Game-state capture route](../../issues/009-game-state-capture-route.md), [Benchmark open-source board recognition on probe frames](../../issues/024-benchmark-board-recognition.md), [Stack and runtime](../../issues/025-stack-and-runtime.md), [Advice surface UX](../../issues/026-advice-surface-ux.md), [Opponent model from trait-only sightings](../../issues/030-opponent-model-from-trait-only-sightings.md).

Capture turns the game window into a [Snapshot](../../CONTEXT.md): every field with its last known value, its age and its source. Manual entry is never used.

## Route

The coach reads the screen and the League client API (LCU), nothing else.

- **Not used.** Overwolf is out of scope. Riot's Live Client Data API on port 2999 was closed on all 357 checks during the probe game; the game process opens no TCP port. Memory reading is blocked by Vanguard.
- **The game window.** The game is `TFTClient-Win64-Shipping.exe` (an Unreal build launched by `TFTClient.exe`), window title "TFT". The dedicated TFT client had not shipped by 2026-10-04; the owner uses the League client.
- **The League client API.** Port and token come from `LeagueClientUx.exe`'s command line. The gameflow phase (`Lobby`, `Matchmaking`, `ReadyCheck`, `InProgress`, `Reconnect`, `PreEndOfGame`) marks game start, end and reconnect. Its game id keys the game log. The LCU has no live game state.

## Capture method

- **Windows.Graphics.Capture (WGC)** of the "TFT" window is primary, with the yellow capture border turned off. It reads the window's own content, not the windows above it. Desktop BitBlt is the fallback if WGC fails.
- The overlay windows are flagged `WDA_EXCLUDEFROMCAPTURE` (Electron `setContentProtection(true)`) as a second guard against reading the coach's own overlay. As a side effect, OBS, Discord and Game Bar recordings do not show the overlay.
- **Display mode.** The game must run borderless or windowed, because an overlay cannot draw over exclusive fullscreen. When the core detects exclusive fullscreen, the second screen shows a warning and the overlay stays off. The owner runs borderless at 2560×1440, 100 % scale, on the primary of two 2560×1440 monitors.
- **Any layout.** Any aspect ratio (16:9, 16:10, 21:9) and window mode is supported. Screen regions are fractions of the game window, anchored per HUD element. The in-game UI scale is read from the game's config. A one-round calibration check flags a layout that reads nothing.

## Fields

Read as text (OCR):

- HUD: stage and round, round timer, level and XP, the five shop-odds percentages, gold, streak count, and all eight players' names and HP.
- Shop: each champion's name, traits and cost; a Wisp's name, cost and effect text; the shop's slot count (5, or 4 with a Wisp).
- Augment cards: name, text, tier colour and each option's reroll button.
- Item choice cards, carousel options (unit and item), the trait panel, and the scouted player's name and level (the number on their tactician's nameplate). On a scouted board the trait panel shows at most 9 rows, active and inactive, each with its unit count, and an "N+" button counting the hidden rows; the coach reads the rows and N.

Units on the board and bench are 3D models with no name label, star levels are pips and items are icons, so none of these is text. They come from purchase tracking and the board reader.

**OCR engines.** Digits (gold, HP, level, XP, timer, stage) are read by template matching against the game font. Names (units, augments, items, Wisps, traits, players) are read with RapidOCR (PaddleOCR models on onnxruntime, CPU) and fuzzy-matched to the client locale's name list from Data Dragon and CommunityDragon. Windows.Media.Ocr is a fallback behind the same interface. A build session benchmarks both on the probe frames before the choice is locked.

## Board reading

The own board and bench come from two sources, and neither is trusted alone.

- **Purchase tracking** derives which units the player owns from shop reads and gold changes, sells, carousel picks, and units granted by Wisps and encounters. Star levels follow from copy counts. The trait panel checks it each round.
- **The board reader** is TFT-COACH's (MIT, commit `bf22ac9`). It finds units by their green health bars, classifies each crop with an EfficientNet-B0 ONNX model, reads star level with a MobileNetV3-small ONNX model, and matches equipped items against Riot item art. It runs on the CPU (onnxruntime), only on frames whose board region changed. One board, bench, star and item pass took 24 ms median and 52 ms p95; DirectML is not needed.
- **Benchmark result.** Every accepted own-board read and star level was right. Equipped items: 171 of 177 read, none wrong (all misses were Tactician's Cape, which has no template). Recall falls late in the game: 6.0 of 10 units on average across stage-6 frames.
- **Fixes the build applies:**
  1. Widen the health-bar search upward with per-champion foot offsets (Maokai first).
  2. Retrain on crops from the owner's game logs labelled by purchase tracking, to cover Lux's Avatar forms and board views of 5-costs (see the training-crop pipeline in [patch-workflow.md](patch-workflow.md)).
  3. Add a Tactician's Cape template and fetch the component templates from CommunityDragon.
  4. Read bench slot 9, which TFT-COACH skips.
- **Merging.** Purchase tracking fills any hex the reader leaves empty, without a position. When they disagree, the reader decides position, star level and items. Unit identity follows the reader above `board_reader_identity_min` (0.55) and purchase tracking below it. Every disagreement is logged with a keyframe.
- **Scouted boards give traits only in v1.** The reader does not read opponents (enemy units carry red bars). Opponent positions and items are not read. A sighting is the trait panel's rows with their unit counts, the hidden-row count and the opponent's level; the Engine infers the units from it ([engine.md](engine.md#opponent-model)).

Augments are read from the screen in both modes. Held augments are tracked from the picks, because the Riot match record for Set 18 has no augments.

## Cadence

- A change check runs at about 4 Hz on small regions: the stage bar, gold, the shop strip, the choice-card area and the board. OCR, the board reader and the Engine run only on regions that changed, so a roll, a Wisp, an augment offer or a scout is read within about 250 to 500 ms.
- Outside a roll-down the shop strip must be read within about 0.3 s, so shop calls meet their 0.5 s budget.
- During a roll-down capture reads only the shop strip, at about 15 Hz, so buys and the roll-down tracker show within 0.25 s of each new shop. A roll-down starts when the advised Line rolls down now, or when the player rolls twice within about 2 s. It ends after about 3 s without a roll, or at the gold floor.
- Full frames are taken only for keyframes.

## Missing, stale and conflicting fields

- Each field keeps its last known value with a timestamp and source.
- Each sub-engine declares the fields it requires. Each field has one maximum age, shared by every sub-engine (`field_max_age_seconds`: 2 s by default, 0.5 s for the shop in roll-down mode). Past that age the field counts as missing and the sub-engines that require it stay silent. A route gap therefore disables specific advice, not the coach.
- A failed read is never guessed. The only imputation is for opponents' board power ([engine.md](engine.md#opponent-model)).
- HUD-layout drift after a patch needs no special mode: fields that fail to read go stale and silence their sub-engine.

Required fields per sub-engine:

| Sub-engine | Required fields |
| --- | --- |
| Shop, Wisp | Shop champion slots, the offered Wisp's id and cost, gold, board, bench, slot count on every roll |
| Items | Items on the player's units and the item bench (silent without the item bench); item offers, held removers and Reforgers when available |
| Augments | The three offered augment ids, the offer tier, which options still have a reroll, augments held |
| Carousel | Each option's unit and item, before the player's pick |
| Positioning | Own-board hexes (from the board reader); sightings with traits |
| Board power metrics | Per combat round: the opponent fought, the result and the HP lost |

## Crash and reconnect

The game process can crash and restart mid-match: in the probe game it exited and a new one started two seconds later, with the client showing `Reconnect`, then `InProgress`. Capture re-scans for the window and continues under the same LCU game id. The missed span is recorded as a capture gap. A restarted core does the same ([runtime.md](runtime.md#processes)).

## Game log

Capture writes the game log described in [review-and-harness.md](review-and-harness.md#game-log).
