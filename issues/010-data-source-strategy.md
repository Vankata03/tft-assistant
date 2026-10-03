---
id: 10
title: "Data source strategy"
labels: [wayfinder:grilling]
status: closed
assignee: Ivan Terziev
parent: 1
blocked_by: [4]
---

## Question

Which data sources does the coach rely on for statistics and comp guidance, and how does it get them: a site's API, self-aggregation from the Riot API, curated input from guide sites, or a mix? Decide how the data is refreshed each patch.

## Comments

### 2026-10-04 — claude-code (resolution)

Resolved by grilling with the owner. Sources: "TFT stats data sources and their APIs", plus a read-only check of TFT Academy's and MetaTFT's comp data on 2026-10-04.

- **Statistics**: MetaTFT's undocumented JSON is the primary source and tactics.tools the secondary. Each source sits behind its own adapter, so a source can be swapped by replacing one module. There is no Riot API crawler in v1. Self-aggregation is the route for a public release, which is out of scope.
- **Guides**: TFT Academy's embedded comp records are the base: 65 comps with tier, early and final board, carousel, augments, stage tips and alternative builds. Statistics fill in item and augment rankings. An owner override file wins over both. lolchess is excluded because its terms forbid copying.
- **Positioning**: final boards use TFT Academy's `finalComp[].boardIndex` (0–27). Interim boards, and units TFT Academy does not place, use MetaTFT's per-unit cell histogram (`comp_details` → `positioning`), taking the most frequent free cell as MetaTFT's own front end does. The owner override wins. Live adjustments belong to the positioning sub-engine.
- **Interim boards**: the static interim board per comp comes from TFT Academy's `earlyComp` (units and items, no positions). A dynamic interim board built from what the player owns is Live-mode advice. No source has early-board statistics, because the Riot API records only final boards. That board is therefore scored heuristically from static data (trait breakpoints, cost, star level, item fit) toward the Guide's target. The selection logic belongs to "Transition and pivot domain model". Blitz is not a source: its robots.txt bars AI agents and its terms are unread.
- **Static game data**: Data Dragon (names, icons, costs) and CommunityDragon (ability and trait numbers) are fetched automatically. One hand-maintained file per patch covers what both lack, such as the Wisp table, shop odds, XP table and pool sizes, filled from patch notes.
- **Data no API records**: positioning statistics, econ and HP curves, roll-down timing and augment offers. The engine relies on game maths and Guides for these. The coach logs every captured game from day one, but v1 does not depend on that personal dataset.
- **Filter**: statistics default to Diamond and above, all regions, and the filter is configurable.
- **Refresh**: at app start and between games, never during a game. Each refresh checks every source's update timestamp and patch label, and pulls only data that has changed and is past its minimum age: 1 hour for statistics, 6 hours for Guides, and on patch change for static data. A refresh never blocks queueing; if a game starts first, it finishes after the game.
- **Patch day**: each entity uses new-patch statistics once its sample passes a threshold of about 500 boards. Below that, it uses previous-patch statistics flagged as stale. Entities the patch notes changed carry a separate "changed this patch" flag. Live mode lowers its confidence on flagged entities.
- **Breakage**: every response is checked against an expected schema. On failure the coach keeps the last good snapshot, falls back to tactics.tools for unit, item and augment statistics, and shows a visible "data stale since" warning. The coach always runs.
- **Riot API**: the owner registers a personal key, used only for the owner's own matches.

Open fact for the build: whether MetaTFT's `comp_augment_tiers` holds augment statistics per comp. The `augments` field in `comp_details` is empty for Set 18. If both are empty, augment rankings use global augment statistics.

Graduated: "Register a Riot personal API key", which now blocks "Record the pre-coach baseline". The data side of the map's "Patch cadence" fog is settled here.
