---
id: 8
title: "Policy stance and feature modes"
labels: [wayfinder:grilling]
status: closed
assignee: Ivan Terziev
parent: 1
blocked_by: [2]
---

## Question

Given Riot's policy, which features run in the compliant baseline and which go into the opt-in real-time mode? Decide where the line falls for each v1 decision (econ, level, roll, shop, transitions, pivots, items, augments, positioning, carousel) and each surface (overlay, second screen, voice), and what risk the owner accepts for the opt-in mode.

## Comments

### 2026-10-04 — claude-code (resolution)

Resolved by grilling with the owner. Sources: "Riot third-party app policy for real-time TFT advice" and "Automatic game-state capture options for TFT".

- **Two modes, one engine.** The spec targets **Live mode**, which gives advice computed from the live game state. **Baseline mode** is the same engine behind a policy filter, so a policy-respecting subset always exists. Baseline mode alone would duplicate free approved apps (Mobalytics, TFT Academy) and is unlikely to move placement.
- **Account risk.** Live mode runs on the owner's main account. The owner accepts the Terms of Service risk. Riot publishes no detection method or penalty, and no ban precedent for a non-automating screen-reading advisor was found. A hardware ban, as Vanguard does in VALORANT, is possible but unverified for TFT.
- **Line per decision.**

  | Decision | Baseline mode | Live mode |
  |---|---|---|
  | Comp choice | Picker sorted by meta tier, chosen by the player pre-game or mid-game, not filtered by the board | Suggests a comp from opener, items and augments |
  | Econ | Static stage plan from the comp's Guide (for example "fast 8 at 4-2") | Save or spend calls from gold, HP and streak |
  | Level and roll | Stage-keyed level and roll plan from the Guide | "Level now", "roll to 20 gold", hit odds |
  | Shop | Display-only highlight of the comp's units | Buy, sell or hold calls |
  | Wisp | Static table of which Wisp effects are worth buying at which stage | Live buy call |
  | Items | Recipes and best-in-slot items for the comp | "Slam X now", component allocation |
  | Augments | Statistics table (average placement) during selection, plus a tag when the augment is in the comp's Guide | Ranked pick from the live state |
  | Positioning | Static positioning from the Guide | Live adjustments |
  | Carousel and opener | Static priority list per comp | Pick from the board and items |
  | Transition | The Guide shows the interim board and the transition stage | "Swap X for Y now" |
  | Pivot | Alternatives listed pre-game ("if contested, go Y"); the player decides | Live pivot call |

- **Grey zone goes to Baseline mode.** Baseline mode also shows an XP-aware leveling hint, a win-chance estimate, and the list of opponents already faced (names and results only). Approved apps ship these features, but their approved scope is not public, so Baseline mode is compliant by approved-app precedent, not provably compliant. A public release would need Riot's audit regardless.
- **Opponent information.** Anything about opponents' boards is Live mode only, because Riot explicitly bans tracking opponents' champions during play. Live mode uses whatever opponent data the chosen capture route gives: every player's board through Overwolf's `match_stats.board_players` and `board.opponent_board_pieces`, or only the boards the player scouts with screen capture.
- **Surfaces.** The policy judges content, not surface. Overlay, second screen and voice follow the same mode rules; no surface is treated as safer. In Baseline mode, voice reads only stage-keyed Guide steps.
- **Post-game review joins v1.** It replays a finished game's decisions against the full engine. It is encouraged by Riot's policy and runs in both modes.
- **Separation.** Live mode is a separable component that a public build can omit entirely, because Riot audits features rather than toggles. The owner's build exposes it as one on/off switch per session, off by default.
- **Measurement.** 50 games without the coach, then 50 games in Live mode with post-game review on.

Graduated: "Post-game review scope" and "Record the pre-coach baseline". Glossary terms Baseline mode, Live mode, Guide and Post-game review added to `CONTEXT.md`; Advice narrowed to Live mode.
