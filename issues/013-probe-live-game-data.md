---
id: 13
title: "Probe live game data sources in a real TFT game"
labels: [wayfinder:task]
status: closed
assignee: Ivan Terziev
parent: 1
blocked_by: []
---

## Question

What do the local data sources actually return during a live TFT game on the owner's PC, now that TFT runs on Unreal Engine? This is a HITL task: the owner plays one game while the agent runs read-only probes. Record:

- Whether Riot's Live Client Data API answers, for example `curl -k https://127.0.0.1:2999/liveclientdata/allgamedata`, and which fields it returns.
- Which client is in use (the League client or the dedicated TFT client, if it has shipped).
- Screenshots of the planning phase at the owner's resolution, for judging OCR and vision feasibility. They should show the HUD, shop with a Wisp, board and bench.

The results feed "Game-state capture route".

None of these probes reads game memory, so the Vanguard change of 2026-10-06 (see "Riot third-party app policy for real-time TFT advice") does not affect them. If an Overwolf developer build becomes available, record which Overwolf TFT game-event keys still update; once the dedicated TFT client ships, re-run the client and port 2999 checks.

## Comments

### 2026-10-04 — claude-code

Input from "Transition and pivot domain model": also screenshot one or two scouted opponent boards (with the bench if it shows), so the probe can judge whether screen capture reads opponents' boards well enough for the contested count.

### 2026-10-04 — claude-code

Input from "Econ, level and roll Line simulation": during the probe game, also record rules facts the simulator currently takes as defaults: whether a PvE round keeps, breaks or ignores a win or loss streak; the gold that PvE orbs drop in each PvE round; and whether the Wisp's 4-champion shop alternates per round or per roll (and what the shop shows after a Wisp is bought). Each confirmed fact replaces a default in the per-patch static file.

### 2026-10-04 — claude-code

Input from "Board and lobby strength heuristic": during the probe game, also record the HP lost on a few lost rounds together with the number and star levels of the opponent's surviving units, so the per-unit damage rule in the static file can be confirmed for Set 18.

### 2026-10-04 — claude-code

Input from "Item decisions": during the probe game, confirm the Set 18 item rules the item sub-engine assumes: a finished item stays on its unit until the unit is sold (items return to the item bench) or a Magnetic Remover is used; a single component can sit on a unit and gives its stats; a second component combines in place. Also note which special item kinds appear (emblems, artifacts, Radiant, support items, Reforger, item anvils) and how they show on the item bench.

### 2026-10-04 — claude-code

Input from "Augment decisions": during the probe game, confirm the Set 18 augment rules the augment sub-engine assumes: offers at 2-1, 3-2 and 4-2; all three options in one offer share a tier (silver, gold or prismatic); each option can be rerolled once, for free; the selection timer is about 43 s for the first offer and 58 s for the others. Screenshot one augment offer before and after a reroll, for judging how capture reads augment names and the remaining rerolls.

### 2026-10-04 — claude-code

Input from "Shop, Wisp and carousel decisions": during the probe game, also note whether low gold seems to limit which Wisps are offered (the unconfirmed affordability rule), what the shop shows after a Wisp is bought, and which opening encounter the lobby got. Screenshot one carousel, for judging how capture reads each option's unit and item.

### 2026-10-04 — claude-code (resolution)

Resolved with the owner, who played one ranked game on 2026-10-04 (14:03 to 14:39, top 4) while [`probe/probe.ps1`](../probe/probe.ps1) recorded it, following [`probe/CHECKLIST.md`](../probe/CHECKLIST.md). The probe polled port 2999 and the League client's gameflow phase every 5 s and took 1,185 full-resolution screenshots, about one every 1.6 s. A 10 s interval was tried first and dropped, because a scouted board or an augment reroll lasts only a few seconds. Nothing read game memory or sent input. The full run (6.6 GB of PNG) stays local and gitignored in `probe/out/2026-10-04_140538/`; nine key frames are committed as JPEG in [`probe/screenshots/2026-10-04/`](../probe/screenshots/2026-10-04/).

**Live Client Data API.** Port 2999 was closed on every one of 357 checks, in the lobby and throughout the game; no TCP port is opened by the game process at all. The API is unusable for TFT, as "Automatic game-state capture options for TFT" found. The League client API (LCU) stays reachable during a game with the port and token from `LeagueClientUx.exe`'s command line. It reports the gameflow phase (`Lobby`, `Matchmaking`, `ReadyCheck`, `InProgress`, `Reconnect`, `PreEndOfGame`), which gives game start and end, but it has no live game state: its TFT endpoints cover only the pass, the team planner and end-of-game stats (`lol-end-of-game/v1/tft-eog-stats`).

**Client.** The dedicated TFT client has not shipped. The owner uses the League client 16.19.823.722 under Riot Client 140. The game itself is `TFTClient-Win64-Shipping.exe` (an Unreal build, launched by `TFTClient.exe`), window title "TFT"; its executable path is not readable from a normal user process. Vanguard 1.19.1 was running and did not interfere with screen capture or the LCU. Overwolf is not installed, so no Overwolf event keys were checked.

**Screen capture.** The game runs borderless at 2560×1440, 100 % scale, on the primary of two 2560×1440 monitors, so a second screen is available for a surface. Plain GDI capture (`CopyFromScreen`) returns clean frames with no black screens. Readable as text in the frames:

- HUD: stage and round, round timer, level and XP, the five shop-odds percentages, gold, streak count, all eight players' names and HP.
- Shop: each unit's name, traits and cost; a Wisp's name, cost and effect text.
- Trait panel, own board and bench, the item choice cards, every augment card's name, text and reroll buttons, carousel units, and scouted opponent boards with their names.
- The loading screen, which lists all eight players and their Little Legends before round 1-1.

Frames: [planning HUD](../probe/screenshots/2026-10-04/01-planning-hud-1-3.jpg), [shop with a Wisp](../probe/screenshots/2026-10-04/02-shop-with-wisp-2-3.jpg), [shop after the Wisp was bought](../probe/screenshots/2026-10-04/03-shop-after-wisp-bought-2-3.jpg), [scouted opponent board](../probe/screenshots/2026-10-04/04-scouted-opponent-board-2-2.jpg), [completed item choice](../probe/screenshots/2026-10-04/05-completed-item-choice-2-1.jpg), [carousel](../probe/screenshots/2026-10-04/06-carousel-2-4.jpg), [augment offer before](../probe/screenshots/2026-10-04/07-augment-offer-before-reroll-4-2.jpg) and [after a reroll](../probe/screenshots/2026-10-04/08-augment-offer-after-reroll-4-2.jpg), [mid-game planning](../probe/screenshots/2026-10-04/09-planning-midgame-3-2.jpg).

**Crash and reconnect.** The game process exited at 14:23:29 and a new one started two seconds later; the client showed `Reconnect`, then `InProgress`. A capture route must re-attach to a new game process mid-game. The probe did so by re-scanning for the window.

**Rules facts for the per-patch static file.**

- **PvE rounds and streaks** (owner): a PvE round ignores the streak. The streak stays as it is until the next player round.
- **PvE orb gold**: not recorded. The simulator's default stands.
- **Wisp** (owner, confirmed by the frames):
  - It is sold in the rightmost slot of every other shop, and rerolls count as shops. At 6-3 the frames show no Wisp, Wisp, no Wisp, Wisp, then two rolls inside 1.8 s ending on a Wisp.
  - A player can buy one Wisp per round.
  - A Wisp is only offered at a price the player can afford when the shop appears. Buying a champion afterwards can leave too little gold for it.
  - A shop showing a Wisp shows four champions. After a Wisp is bought, its slot refills with a champion (Forest Twins at 2-3, refilled with Hecarim).
  - The 16 Wisps seen cost 0 to 4 gold: Take One With Ya 1, Forest Twins 4, Rain 1, Propagate 1, Middle Path 4, Moonlight Ritual 2, Crystal Ball 1, Salvager 0, Flow 3, Nature's Ally 2, Blaze 3, Stand Alone 2, Hero's Entrance 2, Backrow Star 1, Phantom Emblem 2, Prolific Power 0.
- **Damage per surviving unit**: not recorded. The default in the static file stands. The local frames hold HP and boards for every round if the rule needs checking later.
- **Items** (owner): a finished item stays on its unit until the unit is sold or a remover is used, and the owner used removers through the game; the in-game consumable is named "Item Remover". A single component sits on a unit and gives its stats, and a second component combines in place. Special items seen in tooltips: a Defender Emblem on a carousel and a Lesser Champion Duplicator; how the item bench shows each kind was not checked frame by frame.
- **Opening encounter** (owner): this lobby's encounter gave two completed items. The frames show a "Choose One" of five completed items at 2-1 (24 s bar) and a second completed-item choice around 6-1. The encounter's name was not captured, because the first two minutes fell between probe restarts.
- **Augments**: offers came at 2-1, 3-2 and 4-2. All three options in an offer share a tier, and the icon colour shows it: prismatic at 2-1, silver at 3-2, gold at 4-2 in this game. Each option has its own reroll button, usable once and free; it greys out after use. **The selection timer opened at about 48–49 s for all three offers**, not the assumed 43 s and 58 s.
- **Carousel**: at 2-4, 3-4, 4-4 and 5-4.

**Other findings.**

- **TFT Academy's desktop app (0.9.22)** runs beside the game and draws an in-game overlay: a comp tracker, "All Comps" and "Planner" buttons, and S/A/B tier letters with comp icons on augment cards, item choices and Wisp cards. An approved app therefore already overlays tiers on live choices. The owner reports it also records the whole game as video and deletes old recordings after a while.
- **Storage**: lossless PNG at 1.6 s costs about 6 GB per game. Any route that keeps frames for review needs video encoding or keeps only selected frames.
