---
id: 3
title: "Automatic game-state capture options for TFT"
labels: [wayfinder:research]
status: closed
assignee:
parent: 1
blocked_by: []
---

## Question

Which routes can read TFT game state automatically, and which fields does each provide? Fields of interest: stage and round, gold, level, XP, HP, streak, shop, bench, board, items and components, augments, opponents' boards and HP, and the set mechanic's state. Routes to compare: Overwolf Game Events Provider for TFT, Riot's Live Client Data API, screen capture with computer vision or OCR, and anything else in use (for example the techniques behind open-source TFT overlays). For each route give field coverage, latency, reliability, platform requirements (Overwolf account, app approval), and whether it is usable by a personal, unpublished tool on Windows.

## Comments

### 2026-10-04 — claude-code (resolution)

Findings: branch `research/game-state-capture-options`, file `research/game-state-capture-options.md`, 26 dated and graded sources.

- **Overwolf Game Events Provider (GEP)** is the only route that gives near-complete structured state today:
  - Fields: stage and round, gold, level, XP, HP for all eight players, shop, own board and bench with stars and items, every player's item bench, and opponents' boards (the current opponent live, all boards per stage). All TFT keys were green on 2026-10-03.
  - Gaps: no streak field (derive it from round results), and no Set 18 mechanic keys found.
  - Augment data is exposed, but Overwolf's docs say apps must not use it because it breaks Riot's terms.
  - A personal unpublished app needs Overwolf developer access: a Console API key or an approved developer status. Riot approval matters only at publication.
- **Riot Live Client Data API (port 2999)** is not usable for TFT. It is undocumented, gives no board, bench, shop or round, and may not exist on the new Unreal client.
- **Screen capture with OCR and vision** is the only route with no Overwolf dependency. HUD numbers and text are easy. Board and bench units need a trained vision model, retrained each set. Opponent boards are visible only while scouting. It is fragile to resolution and UI changes.
- **Memory reading** is ruled out. Vanguard blocks external memory readers.
- **Timing risk**: TFT moved to Unreal Engine with Set 18, and a dedicated PC client is due 2026-10-09 or 2026-11-03 (Riot's pages disagree). All capture routes need re-checking after it ships.

Open questions moved to "Game-state capture route": whether GEP survives the dedicated client, what Overwolf developer approval involves for a never-published app, GEP data freshness during planning, Set 18 mechanic coverage, and board-recognition accuracy on the RX 6800.
