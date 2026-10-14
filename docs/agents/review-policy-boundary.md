# Partial review and harness implementation

Ticket 42 remains open. This checkpoint makes the historical review producer, protected report routes and background worker available to tickets 44 and 55. It does not complete the review or harness specification.

## Review service and background worker

`ReviewService(sessions, data_store, repository=..., hooks=None)` uses the original immutable data pin and the shared Engine. `job_identity(game_id)` requires a finished log and returns `job_id`, `game_id`, `engine_version`, `data_snapshot_id`, `log_hash`, `schema_version` and the full replay identity. The identity includes the current commit, relevant dirty contents, actual running package sources, hooks, tunables and logged model version. Reading it does not evaluate advice or fetch data.

`produce(game_id, expected_job_id=...)` checks that identity before evaluation and again before publication. The stored review also checks the original log hash atomically. The worker checks identity after publication. A changed input requires a new job; an absent historical pin stays unavailable.

The production process is `python -m tft_core.review_worker GAME --log-root PATH --config-root PATH --snapshots PATH --repository PATH --expected-job-id HASH`. The installed command is `tft-review-worker`. It lowers POSIX priority with `os.nice(10)` before heavy imports; failure returns an unavailable receipt. On Windows the parent supervisor sets below-normal priority. Ticket 55 owns deadlines, process termination, durable scheduling and bounded output collection.

Worker stdout contains one JSON receipt with status `review_ready` or `review_unavailable`, game/job/engine/data identities, nullable report/evidence identities, lock status, priority and a sanitized reason. It never includes private advice, a graph or filesystem paths. Locked reviews are computed privately, but their receipt and protected summary expose no report content. Every summary, detail, what-if and tag route checks the authoritative stored lock and log hash. What-if selects an already scored option and never runs a replacement simulation.

## Renderer contract

The unlocked summary contains `section_paths`. Normal sections are at `surface/lines`, `surface/fights`, `surface/plan_timeline`, `surface/timeline` and `surface/positioning`; Debug is at `debug`. `detail` returns authenticated, byte-bounded EvidenceGraph pages. Top moments carry an authenticated `moment_path`, small player/Engine choice headers and an optional causal logged WebP reference. Media access still goes through ReviewAccess.

Line headers contain `line_id`, schedule, placement estimate, standard error, death/hit probabilities, confidence and round projections. Each projection retains the Engine's round, gold, level, HP, hit probability, expected placement and planned gold. Raw rollout arrays remain in the private evidence graph and are excluded from normal chart headers. Fight rows distinguish forecasts from observed results and retain the physical-unit-count approximation source. Missing player policies, display acknowledgements or results remain nullable with reasons.

## Verified slices and remaining acceptance

Semantic replay retains every raw context and its original timestamps while valuing only declared dependency changes and freshness transitions. Custom hooks declare their additional dependencies. Timer-only polls do not force evaluation. Signed cost remains Engine placement minus player placement, and harmful moments use its negative values. The current observed Line slice identifies confirmed level-up schedules, labels them ex-post, and simulates against the original snapshot, history and seed; paid-roll stopping policies remain unavailable.

The harness currently implements fight Brier/log loss, damage error, equal-game aggregation and paired whole-game bootstrap gates. Finite identical differences have a valid degenerate interval; fewer than two independent games and undefined comparisons remain unavailable. Family 1 fitting searches an explicit bounded parameter grid using older games only, then checks the chronological holdout. It publishes no data. The deterministic-form, zero-emblem next-sighting slice uses an actual normalized joint event mass; general form/emblem/capacity laws are not supplied by this checkpoint.

Still required in ticket 42: general next-sighting law integration; the remaining prediction metrics and naive baselines; report-only diagnostics, advice differences and flip reports; complete functional fitting, stage pooling/shrinkage, family 2 margins and family 3 public-statistics priors; all CLI workflows against committed tunables; full observed roll/pin and other-domain attribution; semantic deviation grouping, shown/follow attribution and complete normal review sections/cross-game summaries; and full-game resource qualification. The strict 50-game baseline validator is implemented, but its owner-facing API/CLI workflow is not yet connected.

Fixtures establish software behavior only. Current source mechanics, statistical cohorts/fits, live LCU end-of-game payloads and match-ID joining remain separately unqualified. macOS process/test results do not qualify Windows capture, target latency or the initiating cause of the historical native teardown failure.
