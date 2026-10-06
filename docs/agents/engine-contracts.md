# Engine contract pointers

Ticket 39 owns the shared contracts and board/opponent functions. Ticket 40 owns the complete `advise(snapshot, history, data, mode)` pipeline. Imports for Baseline features must come from `tft_engine.allowlist` only.

## Snapshot and log shape

`GameSnapshot(game_id, round_id, captured_at, fields, snapshot_id='')` contains an immutable mapping of `FieldValue(value, read_at, source, confidence=1.0)`. Timestamps must have a timezone. `snapshot.field(name, now=..., max_age_seconds=...)` returns the value or `None` when it is missing or stale. Engine callers pass the shared field-age tunable; the convenience default is two seconds.

A `Board` contains `units`, `bench` and optional authoritative `trait_counts`. Each own `Unit` has `unit_id`, `stars`, equipped item IDs and an optional `position`. Duplicate units contribute power separately but contribute their traits once. Variable trait grants require authoritative own trait counts.

A `TraitSighting` contains only `opponent_id`, `round_id`, `level`, `traits` and `hidden_traits`. It cannot encode opponent units, stars, positions or items. `GameHistory` contains snapshots and sightings. Every public log contract exposes `to_dict()` and `from_dict()`; their output is JSON-compatible. Snapshot decoding restores typed own boards and benches, and freezes other JSON fields.

`Advice` contains the required decision, action, urgency, confidence, reason template, numbers and validity. It also carries stable decision and option IDs, a structured payload, scored `ScoredOption` records, anchors and validity-state values. Scored options preserve expected placement and its standard error when applicable; positioning can leave these absent. `rank_advice` ranks urgency before placement impact. Surfaces do not re-rank it.

## Board and opponent functions

The public functions take a `DataSnapshot` explicitly. `strength(board, level, data)` returns a number; `estimate_strength` also returns confidence, the three weighted terms and warnings. `win_probability`, `placement` and `surviving_units` implement the specified combat projections. `placement` receives aligned opponent power and HP sequences and the stage damage divisor. `surviving_units` receives the winner's unit count.

`classify(board_or_marginals, data, limit=...)` returns normalized similarities and labels. Own bench presence is weighted once and cannot double-count a unit on the board. `infer_opponent(sighting, data, previous=...)` returns marginal unit probabilities, top-set certainty and the exact candidate count. `estimate_opponent` adds expected power, the advanced level, fading expected pool copies, labels and confidence. `opponents_from_history` folds sightings chronologically without hidden state.

Opponent confidence is age weight multiplied by inference certainty and data confidence. Trait-only threat consumers use the age weight. Never-seen or unsupported opponents use the par growth curve with no inferred pool reduction.

## Data additions

The Engine requires `level_calendar` (round to standard level), `stage_items` (stage to `finished`, `component`, `high_cost_finished`) and the lobby top-4 rate. `opponent_star_mix` is round to cost to three probabilities. `cost_star_baseline` is cost to star to prior power. `size_level_prior` is level to distinct-unit count to probability; `emblem_count_prior` is count to probability. Item values use `finished`, `component` and `high_cost_bonus`; classifier weights use `carry`, `key`, `other` and `bench`.

Trait entities expose `values.breakpoints`. Rich statistics expose unit-star or trait-breakpoint top-4 rates and sample counts, plus public unit play rates. Explicit tagged entity values named `top4_rate_<star-or-breakpoint>`, `sample_count_<star-or-breakpoint>` and `play_rate` are also supported. Average placement is never a substitute for a top-4 rate. Missing unit splits use the configured cost-star prior with lower confidence. Missing required game tables raise `DataError`.

Unit power uses a binomial prior centered on the cost-star power transformed back to a top-4 rate. Trait power uses a separate `trait_prior_strength` centered on the lobby rate. Shrinkage occurs before the logit, which makes thin 0% and 100% rows finite without an invented epsilon. Endpoint rows without sample counts or positive prior strength are unavailable. Unsampled interior tagged trait rates remain usable as explicit values.

`trait_rules` is keyed by unit ID. `replace` lists complete trait-count variants. Otherwise `counts` overrides base trait counts, `choose_one` lists additive alternatives and `optional_traits` allows any subset. This represents Lux's chosen origin, Elder Dragon's doubled grant and Kha'Zix's evolution subsets without set-specific logic in code.

`growth_curve(data, observations=...)` returns an immutable computed table. A refresh caller can pass it as the `opponent_growth_curve` computation hook. Optional observations are `(round_id, power, confidence)` triples and produce a stage correction. `growth_curve_lookup` computes other rounds from the calendar, shop odds, star mix and generic items.

## Evidence limits

Tests use synthetic public-boundary fixtures. They cover exact posterior sets, hidden inactive rows, emblem slack, special grants, fading sightings, finite endpoints and JSON replay. A bounded subprocess checks an ambiguous 215,553,195-set case. No current roster, fitted owner-match parameters, Windows capture, live-game accuracy or Ryzen 7 7800X3D budget qualification is claimed. Mixed variable-grant candidates use pruned exhaustive enumeration and still need full-roster performance qualification.
