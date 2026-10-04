---
id: 21
title: "Augment decisions"
labels: [wayfinder:grilling]
status: closed
assignee: Ivan Terziev
parent: 1
blocked_by: [12]
---

## Question

How does the augment sub-engine rank an augment offer in Live mode? Inputs are the Game plan, augment statistics (per comp if MetaTFT's `comp_augment_tiers` holds them, otherwise global), the current board and the stage. Decide how per-comp and global statistics combine, how rerolls are advised, how an augment that fits a different comp raises a pressure signal on the Game plan, and how flagged or stale statistics change the ranking.

## Comments

### 2026-10-04 — claude-code

Input from "Transition and pivot domain model": the augment pressure signal is the augment fit term this sub-engine contributes to comp fit through `fit(comp, state) → term`. An augment offer is ranked by the best comp fit across candidate comps after taking each option (the top-k candidates while the plan is Open; the target comp, the Backup comp and other Guides once Committed). The sub-engine never changes the plan; if an augment makes another comp best, the Game plan layer pivots on its next check, through the pivot margin. Checked scenario: with full AD items, an AP augment raises AP comps' fit only slightly because their item fit is near zero, so it ranks low and no pivot follows. A comp-defining augment is a commitment trigger.

### 2026-10-04 — claude-code (resolution)

Resolved by grilling with the owner. Sources: "Transition and pivot domain model", "Item decisions", "Econ, level and roll Line simulation", "Data source strategy", "TFT stats data sources and their APIs", and a fact check made for this ticket.

**Fact found while resolving: no Set 18 augment statistics exist.** On 2026-10-04 the Riot match record for a Set 18 ranked game has no `augments` field at all; the only `DA_` ids in it are units, traits and emblem items (checked on one of the owner's ranked games, A). The statistics sites show the same gap at scale: MetaTFT's explorer (`tft-explorer-api/augments_by_stage`) returns 7.2 million samples with every augment id null, tactics.tools reports 3.2 million games with an empty augment table, and MetaTFT's `comp_details` holds only an empty no-augment bucket. What remains is curated letter tiers:

- MetaTFT `comp_augment_tiers?cluster_id=<id>`: per comp, tiers S, A and B, 41 comps with 1 to 97 augments each, apparently matched from hand-made guides (`source_title`, `distance`).
- MetaTFT `tft-stat-api/augments_tiers`: a global curated list (S 30, A 85, B 122, C 22), updated 2026-10-03.
- TFT Academy's per-comp `augments` lists.

MetaTFT's own in-game app converts tiers to placement deltas as S −0.3, A −0.15, B 0, C +0.15, D +0.3. The statistics schemas still exist (tactics.tools `p1/p2/p3` per pick stage, MetaTFT `orders` 0/1/2), so statistics may return if Riot restores the field.

Augment rules assumed for Set 18, to be confirmed by "Probe live game data sources in a real TFT game": offers at 2-1, 3-2 and 4-2; all three options in an offer share a tier; each option can be rerolled once, for free; the selection timer is about 43 s for the first offer and 58 s for the second and third.

- **Augment value.** The value of augment A for comp C is a placement delta from a chain. While no statistics exist, it is the per-comp MetaTFT tier, else the global MetaTFT tier, converted through `augment_tier_delta` (starting at MetaTFT's map). An augment absent from the comp's list uses its global tier with lowered confidence. Once a source publishes Set 18 augment rows past the roughly 500-board threshold from "Data source strategy", that augment switches to statistics: comp C's average placement with A minus comp C's average, shrunk toward the global delta by sample size, with a thin global delta shrunk toward a tier prior (silver, gold, prismatic). Per-stage statistics are used when available.
- **Augment fit.** The term this sub-engine contributes to comp fit through `fit(comp, state) → term`: the sum of the values of the augments the player holds, for that comp. Slots not yet picked count 0, as an average augment. Values add up; augment pairs and trios are not modelled. This keeps augment fit a delta on top of the comp average that already sits inside the simulated placement, as item fit is.
- **Econ augments.** Augments tagged as econ in the per-patch static file (gold, XP or free rolls, encoded like Wisp effects) are valued by a same-seed Line simulation pair, with and without the augment. The simulated delta replaces the tier or statistics value for these augments, which makes them depend on HP, Line and stage.
- **Augments that grant items, units, emblems or traits** use the tier or statistics value only. Their average effect is already in it, and adding item fit for random grants would count it twice.
- **Pick stage.** Tier values do not depend on the stage. Econ augments are stage-aware through the simulation pair. Statistics, when they return, are read per pick stage.
- **Ranking an offer.** Each option is scored by the best comp fit across candidate comps after taking it, as settled in "Transition and pivot domain model". The sub-engine never changes the Game plan.
- **Rerolls.** Rerolling an option the player will not pick is free and can only help, so the advice is to reroll every option except the current best, then re-rank the new options. Rerolling the best option is advised only if the expected best value after the reroll beats keeping it. The expectation runs over the offer's tier pool minus the options shown, with uniform weights, using the same value chain.
- **Comp-defining augment.** A pick commits the Game plan when, after it, the top candidate comp's fit leads the second candidate's by at least `comp_defining_margin` and augment fit accounts for most of that lead. There is no hand-tagged list.
- **Guide augment list.** TFT Academy's per-comp list is a display tag and a tie-break only.
- **Confidence and ties.** Advice built from tiers is capped at medium confidence. A tier list whose `updated` date is before the current patch date is flagged stale. When options share a tier and no simulated delta separates them, the advice says "close", shows both, and breaks the tie by the Guide tag, then the global tier. Once statistics return, a stale or changed-this-patch flag multiplies the prior strength (`augment_flag_prior_multiplier`) and lowers confidence; a flagged augment is never excluded, and options inside each other's 95 % margin are shown as "close". A new augment with no data uses the tier prior plus the Guide tag.
- **Advice.** Live mode gives "Take X" and "Reroll options 1 and 3", with the value source in the reason (for example "X: S-tier for this comp (−0.3), Line simulation +0.2"). It must show within about 2 s of the offer appearing. Baseline mode was set to show an average-placement table during selection, but no such statistics exist for Set 18, so Baseline mode shows the per-comp and global tiers with the Guide tag instead, and switches to the statistics table if statistics return. Post-game review replays offers, rerolls and picks through the same rules.
- **Required fields.** The three offered augment ids, the offer tier, which options still have a reroll, and the augments held. Held augments now come only from capture, because the match API dropped them. Without the offer the sub-engine emits nothing. Without held augments, augment fit is 0 for every comp.
- **Tunables owned here:** `augment_tier_delta`, `augment_prior_strength`, `augment_flag_prior_multiplier` and `comp_defining_margin`. The per-patch static file holds the econ augment tags with their effects and each tier's augment pool.

Glossary terms Augment fit and Comp-defining augment added to `CONTEXT.md`.

Input posted to "Game-state capture route" (required fields), "Probe live game data sources in a real TFT game" (augment rules to confirm), "Post-game review scope" (augment review needs the capture log), "Econ, level and roll Line simulation" (econ augment pairs) and "Data source strategy" (correction: no augment statistics for Set 18).
