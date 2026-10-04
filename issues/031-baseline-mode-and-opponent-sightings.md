---
id: 31
title: "Baseline mode and opponent sightings"
labels: [wayfinder:grilling]
status: closed
assignee: claude-code
parent: 1
blocked_by: []
---

## Question

May Baseline mode capture opponent sightings and show a win chance computed from them, and does any Engine function run in-game in Baseline mode?

Two settled tickets disagree:

- "Policy stance and feature modes" rules that anything about opponents' boards is Live mode only, because Riot bans tracking opponents' champions during play. The same ticket puts "a win-chance estimate" and the list of opponents already faced (names and results only) into Baseline mode's grey zone.
- "Board and lobby strength heuristic" defines Baseline mode's win chance as `win_probability` against each possible next opponent from their last sighting. "Advice surface UX" shows it per player-list row on the Baseline-mode overlay.
- "Advice engine architecture" says that in Baseline mode the Engine runs only after a game ends, yet the win chance above calls the Engine's board power functions in-game, and the Baseline-mode Wisp worth table is computed by the Engine offline.

Decide whether Baseline mode records and uses sightings, what its win chance is computed from if not, and how to state which Engine functions Baseline features may call during a game (the `live` package boundary from "Stack and runtime" stands either way).

Raised by "Assemble the MVP spec" as a contradiction between settled tickets. On resolution, update `docs/spec.md` (modes and open items) and `docs/spec/surfaces.md`.

## Comments

### 2026-10-04 — claude-code

Input from "Opponent model from trait-only sightings": a sighting now means the scouted trait panel (rows, unit counts, hidden-row count) and the opponent's level. Win chance comes from an inferred board: a solver over trait counts with priors, then an expected board power. If Baseline mode keeps win chance, it needs that solver and `opponent_star_mix` in-game, not only `win_probability`. Threat tags read traits alone and need no inference.

### 2026-10-04 — claude-code (resolution)

Resolved by grilling with the owner. Sources: "Policy stance and feature modes", "Board and lobby strength heuristic", "Advice engine architecture", "Advice surface UX", "Opponent model from trait-only sightings", and the policy text in `research/riot-third-party-policy.md` ("may not track your opponent's champions/plays ... during gameplay"; scouting is an unapproved use case).

- **The opponent rule has no exception.** Opponent-board data is Live mode only during a game. Per-opponent win chance from sightings needs the inferred board, which is a list of the opponent's likely champions, so it is tracking. MetaTFT's "win chance estimates" are not followed as precedent, because their approved scope is unknown.
- **Sightings are logged in every mode.** Capture and the game log do not change with the mode, so Baseline mode logs raw sightings (trait rows, unit counts, hidden-row count, level). Baseline mode never runs the opponent model on them during a game and never shows them. Post-game review infers boards from the log in both modes, so the Baseline review keeps its fight strip.
- **Par win chance replaces win chance in Baseline mode.** It is `win_probability` of the player's board against the **par board**, the opponent growth curve's board power for the round. It uses no opponent data and is a number only, never an action. The Baseline overlay shows it as one chip during planning, in place of the player-list rows, which now show nothing. The Baseline second screen shows it during planning and combat, beside the opponents already faced (names and results only). An unread own board pauses the chip with the grey dashed tag. Live mode does not show it.
- **Engine use during a game in Baseline mode.** "The Engine runs only after a game ends" is replaced. The advice pipeline (Game plan, sub-engines, Line simulator, opponent model) never runs during a game in Baseline mode. Baseline features may call only an allowlist of pure Engine functions over static data and the player's own state: own-board board power, `win_probability` and the opponent growth curve lookup. One Engine module exposes it, and an import-linter contract keeps Baseline features off the rest of the Engine, beside the existing `live` contract. Offline per-patch Engine output, such as the Wisp worth table, counts as static data.
- **XP-aware leveling hint, now defined.** It states the gap between the player's level and XP and the Guide's stage-keyed level target, counting passive XP up to the target round, for example "Guide: 8 at 4-2 · 3 XP buys (12 gold) short". It is a fact, never "level now". It is arithmetic over the static XP table and the Guide, not an Engine function.

Updated: `docs/spec.md` (modes and policy, open items), `docs/spec/surfaces.md`, `docs/spec/engine.md` (mode separation, win chance), `docs/spec/runtime.md` (second import-linter contract). Glossary: Par board and Par win chance added; Win chance and Baseline mode updated in `CONTEXT.md`.
