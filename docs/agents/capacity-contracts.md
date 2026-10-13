# Team slot capacity contract

Ticket 54 consumes explicit game-data certificates. It does not qualify the values for patch 18.4b. Physical unit count, occupied team slots, positions on the 28-hex board and maximum team-slot budget are distinct quantities. Level selects a sourced base budget; it is not itself a slot budget or a physical unit count.

## Patch metadata

Every playable `unit` and `unit_form` requires `Entity.values.team_slot_cost`, a tagged nonnegative integer. There is no ordinary-unit fallback. Forms sharing a canonical pool must have the same certified slot cost. Zero-slot units can participate in bounded selection and inference, but the par model pauses without a sourced frequency model for them.

The required tagged static field `team_capacity` has these keys:

```json
{
  "levels": {"1": 1, "2": 2},
  "trait_bonuses": [],
  "held_augment_slots": {},
  "inventory_item_slots": {},
  "transition_policy": {
    "deploy": "reserve_before",
    "swap": "remove_then_reserve",
    "bench": "validate_after"
  }
}
```

The numbers above are a shape example, not accepted patch values. Level keys are canonical positive integer strings. Budgets are positive integers. Costs and bonuses reject booleans, fractions, negative values and nonfinite numbers. Unknown keys and unsupported activation policies are unavailable rather than defaulted.

A trait bonus row contains `trait_id`, `breakpoint`, `slots` and `activation="continuous"`. Its breakpoint must exist in the certified trait metadata. Only the highest active breakpoint contributes for each trait; different traits add. Unit/forms use the shared static `trait_rules` helper, which preserves multiplicities. Equipped item grants require tagged `trait_grants` certificates, including an explicit empty mapping when an item grants no traits. Observed counts relevant to capacity must match these units and grants. Counterfactual boards derive their counts again; removed contributions cannot retain the old budget. Unknown external trait activation pauses the dependent model.

A held-augment modifier maps a known augment ID to `{slots, activation:"held"}`. It requires fresh complete held-augment evidence. An item modifier maps a known item ID to `{slots, activation:"continuous", scope}`. Supported scopes are `deployed_equipment`, `equipped_anywhere` and `owned`. The first counts equipment on deployed units; the second includes equipment on bench units; the third also includes loose inventory. Each physical copy contributes separately. Item modifiers require fresh complete item and bench ownership. Timed or conditional activation outside these shapes is unsupported.

## Observations and projections

`CapacityEvidence(held_augments=None, item_bench=None, observed_budget=None)` is immutable. The caller projects freshness and completeness before constructing it. Engine snapshot consumers use fresh literal `held_augments_complete` and `item_inventory_complete` certificates where their rules need them. Optional `fields.team_slot_budget` checks a fully sourced current model; a present stale or conflicting value pauses. An observed budget cannot invent future augments or item modifiers.

`CapacityModel.check` returns `CapacityState(physical_units, occupied_slots, maximum_slots)`. Own-board power, comp screening, strongest-owned selection, forced Guide selection, shop previews, physical grants and Lines use the same model. Baseline projects only its own fresh ownership and capacity evidence through `tft_engine.allowlist.strength`; it does not import planning or opponent inference through the capacity boundary.

Capture requires optional tagged `static.capture_unit_counter={region, semantic}` to certify the HUD counter. Supported semantics are `physical_units` and `occupied_team_slots`; the region must be independently reviewed and configured in the capture profile. Unknown semantics retain legacy raw observations but leave `inventory_complete=False` with `ownership_capacity_status="reviewed_counter_unavailable"`. Slot semantics compare the numerator with the sum of pinned per-unit slot costs, emit `occupied_team_slots` and the positive denominator as `team_slot_budget`, and keep the recognized physical count in `physical_unit_count`. Missing slot certificates or conflicting counts cannot certify ownership. Physical-counter semantics do not reinterpret their denominator as a slot budget. These projection fields require the current own view and preserve the observed timestamp. Capture uses the shared Data metadata helpers, with no Engine import. Actual HUD counter semantics and geometry remain ticket 49 qualification work. Remote counter evidence is not currently produced; an own or old viewer budget is never copied into another player's sighting.

Choice valuation preserves the original seed and original observed state. A changed ownership/augment/item option drops the captured budget from its hypothetical copy and derives a new budget from the same model. `SimulationEffects.item_bench_state` supplies the physical loose inventory for item counterfactuals. It complements `item_state`; an explicit empty inventory does not inherit the old one. An oversized deployed polymorph and grant bench overflow pause unless a supported sourced overflow rule exists.

## Selection and movement

Selection reserves the full incoming cost, uses greedy power plus strict swap improvement, and respects Guide deadlines within the legal budget. It preserves a stronger already legal observed board, including a board supported by an active trait, when forced comp progress is no worse. Duplicate identities remain distinct indexed physical units.

Bench coordinates are inventory positions, not board hexes. An incoming bench unit's proposed board position is left unknown; it cannot retain a bench index as a claimed occupied hex. Indexed move proofs preserve its source identity, and the positioning domain supplies any destination layout. Scalar or stage-mapped transition tolerance is resolved for the actual simulated round and included in board memoization.

The supported transition policy validates removal, reserves the incoming cost before deployment and validates the resulting budget. A swap reuses the incoming unit's bench slot. This is a conservative policy requiring a tagged declaration; it is not evidence for the actual game's atomic trait-swap timing. A self-supporting rearrangement with no supported sequence pauses rather than asserting it is executable.

Transition advice includes ordered `steps`. Each step contains `operation`, indexed incoming/outgoing identities and `before`/`after` values for physical units, occupied slots, maximum slots and bench units. A deterministic breadth-first search respects sourced `bench_size` and the hand-set `capacity_transition_state_cap`. Missing budget, exhaustion or no legal sequence pauses the dependent action. It never publishes a partial path as complete.

Ordinary one-slot rollouts retain the vectorized implementation. General capacity states reuse the public selection policy and memoize complete owned-copy, level and equipment-retention states. Captured deployed identities remain the anchor while still owned. Sale returns remove equipment activation; a later purchase cannot silently re-equip those returned items. Unsupported capacity collapse or equipment merge/overflow pauses valuation. The generic rollout item-power term remains fixed as required by planning ticket 18; physical capacity modifiers use the retained inventory separately.

## Opponent and replay consumers

`TraitSighting.team_slot_budget` is an additive optional positive integer. It is distinct from level and visible physical unit count. Inference's symbolic state includes occupied slots, and its prior still describes physical distinct-unit count. Visible trait bonuses use sourced breakpoints. When augment or item capacity modifiers are possible, an absent observed opponent budget yields an empty posterior with an explicit fallback reason; the model never reads enemy items or units to manufacture capacity.

`OpponentEstimate.expected_unit_count` is an additive physical-count estimate. It combines marginal physical units with slot-aware filler and par growth. `growth.par_unit_count(round_id, data)` uses the base slot budget and the play-rate/shop-weighted inverse slot cost. These are approximations, not observations or fitted facts. Own rollouts still require a resolved active form for variable base identities. Capture currently preserves the base classifier identity plus separate traits/origin observations; those observations are not silently promoted to a typed active form. That producer resolution remains an explicit ticket 48/49 integration condition. Lines, the analytic survival screen and replay forecasts use this count for survivor damage instead of treating level as unit count. An unavailable estimate may use the same par helper, with the qualification disclosed.

Advice required-field fingerprints include the optional capacity observation and relevant inventory fields. Model fingerprints retain tagged static and entity values. Replay and Live transport can retain the structured step proof and scored summaries without reconstructing capacity from English text.

## Reviewed entity input

`bootstrap` and `new-set` accept `--entity-overlay-file`. JSON schema version 1 names the exact patch/set and maps existing canonical entity IDs to tagged `values`; every declaration has a nonempty citation. An optional base catalog hash binds the overlay to checked inputs. The overlay cannot add identities, aliases or change typed identity fields. Capacity and item-certificate validation runs before publication. Failure preserves owner overrides and creates no target, calendar entry or override archive. The patch diff records hashes and before/after tags. These are review declarations, not independent source or statistical-fit qualification.

This adds one required static field and one hand-set tunable: 25 required static fields and 59 tunables, with 26 hand-set entries. Actual patch certificates, the Riftbeast capacity conflict and atomic transition semantics remain ticket 48 qualification work. Target Ryzen/game-running latency and Windows capture remain ticket 49; synthetic CPU tests do not qualify them.
