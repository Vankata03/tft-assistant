---
id: 22
title: "Positioning decisions"
labels: [wayfinder:grilling]
status: closed
assignee: Ivan Terziev
parent: 1
blocked_by: [9, 24]
---

## Question

How does the positioning sub-engine adjust the Guide's static positioning during a game? Live adjustments depend on what the capture route reveals about opponents' boards. Decide which adjustments v1 makes (for example carry corner against assassins, spreading against area damage, the next opponent's threats), which opponent data each needs, and what it advises when only scouted boards are available.

## Comments

### 2026-10-04 — claude-code

Input from "Transition and pivot domain model": the recommended board decides which units are fielded each planning phase; this sub-engine decides where they stand.

### 2026-10-04 — claude-code

Input from "Game-state capture route": the route is screen capture only, with no Overwolf, so opponent boards are known only from the player's own scouting, each with a sighting age. If "Benchmark open-source board recognition on probe frames" passes, a scouted board gives units, hex positions, star levels and items; otherwise it gives the scouted player's traits only, and live positioning has no opponent positions to react to. The own board's hex positions come from the vision model; purchase tracking alone does not know them. The next opponent is not known before combat from capture, apart from what the player scouts.

### 2026-10-04 — claude-code

Input from "Post-game review scope": the review replays every decision point through the Engine and shows the costliest moments. Positioning review follows whatever this ticket settles. For it to work, the game log needs the own board's hex positions at the end of each planning phase and any scouted opponent positions, so the replay record can hold positions per fight.

### 2026-10-04 — claude-code

Input from "Benchmark open-source board recognition on probe frames": v1 uses TFT-COACH's board reader, with fixes, beside purchase tracking. The reader gives the own board's hex positions, units, star levels and items. In the probe game, every unit it read was right, but late-game 5-costs were often missed until the build fixes land, and purchase tracking fills those hexes without a position. It does not read opponents, so scouted boards give traits only in v1, with no opponent positions or items. Live positioning therefore has the own board's positions but only scouted traits to react to.

### 2026-10-04 — claude-code (resolution)

Resolved by grilling with the owner. Sources: "Game-state capture route", "Benchmark open-source board recognition on probe frames", "Board and lobby strength heuristic", "Data source strategy", "Transition and pivot domain model", "Policy stance and feature modes" and "Post-game review scope".

- **Rule-based, not scored.** Positioning is the one rule-based sub-engine. Board power has no hex term, v1 has no combat simulator, and no source records position statistics; MetaTFT's cell histogram gives frequency, not performance. The sub-engine emits a target layout with a template reason. It adds no comp fit term, gets no placement delta and never enters the Line simulation. A combat simulator that could score hexes is post-v1.
- **Base layout.** The recommended board decides which units are fielded. Units the Guide places keep the Guide's hex (owner override first, then TFT Academy `boardIndex`). Every other unit is placed by one assignment that maximizes the summed log-frequency of MetaTFT's per-unit cell histogram over the free cells, so a filler unit cannot take a carry's usual cell. Baseline mode shows only the Guide's own final and interim layouts, never the dynamic layout of the recommended board.
- **v1 adjustments**, applied in this order. Each unit takes at most one adjustment, and owner-override hexes never move.
  1. **Own positional mechanics** (B): traits and augments with hex effects, such as Greenfather's seed hex buffs. Reads own state only.
  2. **Anti-dive** (C): when the likely opponents threaten the backline, the carry goes to a corner with a bodyguard tank, or to the side away from the threat.
  3. **Anti-AoE spread** (D): when the likely opponents carry area damage, backliners that C did not place are spread apart.
  4. **Fill** (A): every remaining unit, including interim-board units, units from augments or Wisps, and extra slots at a higher level, takes its base-layout hex.

  C and D may move units the Guide placed.
- **Threat source.** C and D read the possible next opponents: the lobby minus the recently met players, the same set Baseline mode's win chance uses. The threat share is the fraction of those opponents whose sighting carries the threat tag, each weighted by sighting confidence, which fades with age. An adjustment turns on at `threat_share_on` (about 0.5) and off below `threat_share_off` (about 0.3), so the carry does not flip corners every round. Opponents never scouted are left out of the share, not imputed: the power imputation in "Board and lobby strength heuristic" does not extend to traits. With no sightings, C and D stay off.
- **Threat tags** (`backline_access`, `aoe`) are derived, not hand-typed. Keyword rules run over CommunityDragon's trait and ability text (Data Dragon holds no ability text): for example leap, dash, jump, blink, "farthest" and "backline" for `backline_access`, and "adjacent", "hexes around", "in a line", "cone" and "all enemies within" for `aoe`. Units are tagged from their ability text. A trait is tagged from its own text, and also when most of the units that can activate it carry the unit tag, because a sighting gives traits only. A tag applies from the trait's lowest breakpoint unless the text ties the effect to a higher one. No local LLM is used. The owner's override file gains a threat-tag section that wins over derived tags. Each refresh logs every tag with the phrase that matched and a diff against the previous patch, for a quick patch-day review.
- **Form and timing.** Advice is a target layout for the whole board. Units whose current hex the board reader knows get a move arrow; a unit known only to purchase tracking shows its target hex without an arrow. It is issued once per planning phase when the board has settled (no unit change for about 2 s) and re-issued only when the recommended board changes or C or D flips. Voice speaks only when C or D turns on, for example "carry to corner, assassins likely". Layout detail belongs to "Advice surface UX".
- **Review and harness.** Positioning is never a moment. The post-game review shows a positioning note per fight: whether a layout was advised and followed, and the fight result against win chance. The evaluation harness reports the `win_probability` residual on fights where C or D was active, split by followed and not followed. It is report-only, never a pass gate, because samples will be few. The game log already keeps own-board hexes at the last snapshot before each combat and sightings with traits ("Game-state capture route").
- **Out of v1:** counter-positioning against an enemy carry's hex, and placement against Zephyr, Shroud or other position-mirroring items. Both need opponent positions and items, which v1 does not read.
- **Tunables owned here:** `threat_share_on`, `threat_share_off`, `board_settle_seconds` and the threat keyword lists.

Glossary terms Target layout and Threat tag added to `CONTEXT.md`.

Input posted to "Advice surface UX" (target layout display and voice rule) and "Evaluation harness" (report-only metric and the threat-share tunables).
