---
id: 42
title: Replay, post-game review and evaluation harness
labels: [implementation:task]
status: open
assignee: codex-review-harness
parent: 34
blocked_by: [35, 41, 52]
---

# Replay, post-game review and evaluation harness

## Sources

- [docs/spec/review-and-harness.md](../docs/spec/review-and-harness.md)

## Acceptance

Replay same Engine with historical snapshots/data, explicit choice/cost/scored-option records, grouping/close-call/capture-gap/positioning rules, dirty-safe cache, tags/review locks, all evaluation metrics/naive baselines/game-bootstrap gates/flip reports, chronological fit holdout and tunable-family restrictions.

Implement all referenced requirements. Verify through the approved public seams in [implementation contract](../docs/agents/implementation.md). Record platform checks separately; keep unmet acceptance explicit.

## Comments

### 2026-10-14 — Independent corrected storage integration

A different merger reviewed exact author commit `5427406dde960b8c7e4a6118ad876767752c8a93` against integration `2fe0820` and merged it as `197022d434cdfb8c89b65180b7c6bd5b347be6be`. Source inspection covered shared per-root reentrant exclusion, the shared one-second acquisition deadline, nonblocking OS contention, private SQLite rebuild files, connection closure before replacement, failed-rebuild preservation and sequence invalidation after external appends. No storage-scope blocker was found; storage source was not changed during review.

Independent candidate verification passed 99 public storage/process/worker/policy/replay/runtime tests in 15.25 seconds, process exit 0. The original eight-child public constructor reproduction returned all ten games from every child and zero failures. After merging, the same 99 tests passed in 15.93 seconds, process exit 0; the original eight-child reproduction again returned ten games from each child and zero failures, process exit 0. The tests include actual two/eight-process constructors, cache publishers alongside later core games, alternating writers, held external OS-lock timeout, retry recovery, unchanged committed records, last-good index preservation and metadata-only operator path resolution. Merged-root import contracts kept 2 with 0 broken; schema, frozen lock and whitespace checks exited 0.

This review did not rerun the complete training suite or the Live-absent suite; those remain the explicitly bounded author evidence above. UI source is unchanged. Actual Windows locking/rename execution, native-cause and production/live-game qualification remain open. Ticket 55 still owns verified orphan-child reconciliation, ticket 44 owns its separate narrow tag/fsync correction, and full ticket 42 remains open. Existing `.DS_Store` and other worktrees were preserved; nothing was pushed.

### 2026-10-14 — Bounded store acquisition after independent review

The storage reviewer found that POSIX lock acquisition could wait indefinitely and the Windows blocking CRT call could wait about ten seconds. A public process holding the actual OS lock reproduced a constructor blocked past a two-second deadline. Acquisition now uses one shared one-second deadline for the reentrant thread lock and nonblocking OS contention attempts. Timeout raises a visible busy error; unrelated I/O errors propagate. The last-good metadata/log test passes after timeout and subsequent retry. This bounds acquisition only, not an already-running transaction; ticket 55 owns verified orphan-child reconciliation before store initialization. `SessionStore.default_locations()` resolves the same operator paths without constructing a store, enabling that ordering; its actual environment/process test failed before the helper and now passes without creating directories. The global lock does not replace ticket 44's separate tag/fsync transaction correction, which its author owns.

After bounded-acquisition correction: full train 530 passed, no skips, 72.53 seconds, process 0, two existing Torch warnings. The later path-only helper is covered by combined storage/worker/policy/replay/runtime 99 passed in 15.34 seconds, process 0; with Live physically absent, 99 passed in 15.42 seconds, process 0. Live/train were restored. That helper was not present in the 530-test run. Imports 2 kept, schema, lock, scoped F821 and diff checks passed. UI source is unchanged; prior 35 UI/type/build evidence applies. Full ticket 42 and Windows/native-cause qualification remain open.

### 2026-10-14 — Shared core/child store race correction

The real two- and eight-process constructor regression failed with `table replay_cache already exists`, readonly-database and disk-I/O errors. Every constructor reused and unlinked `index.rebuild.sqlite3` while another SQLite connection could still be building it. Private temporary databases removed that collision. A per-root reentrant thread/OS lock now serializes existing guarded lifecycle writes, cache/review publication and SQLite reads/rebuilds, so an older build cannot publish after a newer authoritative transaction. Connections close before replacement; a failed rebuild keeps the last-good index. The original eight-child fixture now reports all ten games from every child with zero failures.

A second public alternating-cache-writer test failed with `invalid event sequence`: independent instances retained stale `_next_seq` values even after another writer appended. The cache now reuses a sequence only while the known byte size remains unchanged; otherwise it rereads the committed prefix. Permanent cases cover two/eight constructors, independent writers, actual child cache publishers alongside the next-game lifecycle, and failed-source rebuild preservation. Focused storage/worker/policy/replay/runtime checks: 97 passed in 13.80 seconds, process 0; with the Live package actually absent, the same 97 passed in 13.65 seconds, process 0. Live/train were restored. Full train with pinned models/portable PowerShell: 529 passed, no skips, 69.33 seconds, process 0, two existing Torch export warnings. Imports 2 kept, schema, lock, scoped F821 and diff checks exited 0. UI source/schema did not change; prior checkpoint UI 35/type/build proof applies. No native-cause or Windows execution qualification is claimed. Windows uses the primary-documented byte-lock API; actual lock/rename execution remains ticket 49. Independent integration is pending; full ticket 42 remains open.

### 2026-10-14 — Partial producer/service checkpoint; acceptance remains open

The checkpoint exposes actual `ReviewService.job_identity`, protected summary/pages/what-if/tags, typed normal chart headers, and the receipt-only `tft-review-worker` process so tickets 44/55 can integrate against committed interfaces. Semantic replay retains every raw poll and causal timestamp while avoiding timer-only revaluation; custom Engine hooks declare their extra dependencies. The observed Line slice uses confirmed level schedules and original information/seed, and retains unavailable roll policies. The harness has worked fight/damage metrics, equal-game paired bootstrap and bounded train-only family-1 grid fitting. The strict raw-match baseline validator replaces the former shallow count/rank check. See [the partial boundary](../docs/agents/review-policy-boundary.md) for API details and the complete remaining list.

Public red/green proof includes missing section paths, missing job identity, and the missing worker module. The actual worker subprocess now handles locked/unlocked reviews, original data pins, POSIX below-normal priority, stale expected job IDs and missing historical data without private stdout or network calls. Full train with pinned CPU models and portable PowerShell: 524 passed, no skips, 90.59 seconds, process exit 0; two existing Torch export deprecation warnings. Actual Live-absent replay/policy/worker/harness/fit/baseline/observed-Line/sighting/Baseline checks: 76 passed in 27.66 seconds, process 0; Live/train restored. Imports 2 kept, schema, lock, scoped F821 and diff checks exited 0. UI 35 tests, typecheck, generated types and build exited 0. The first UI command exited 127 because this fresh worktree lacked dependencies (`tsc: command not found`); `npm ci` completed, then all UI gates passed. npm reported three uncovered dependency install scripts and zero vulnerabilities; no package/config changes were made for that warning. Bounded prose audit found zero phrase matches and preserved 25/25 constraints.

This is deliberately partial. General joint-law integration, remaining prediction metrics/baselines, functional fitting and family-2/3 computation, report-only/flip/advice-diff checks, all harness CLI workflows, complete observed-policy and domain attribution, semantic grouping, display/follow attribution, complete readable review/cross-game sections and full-game resource proof remain open. No owner credentials, API matches or run were accessed. Current production sources and actual Windows/LCU/match-ID/native-cause qualification remain separate. Independent review/integration of this checkpoint is still required.

### 2026-10-11 — Cost sign and observed Line interpretation

Preserve the specification's signed definition: `cost = Engine expected placement - player expected placement`. A worse player choice therefore has negative cost (Engine 3.1, player 4.2 gives -1.1). Top moments rank harmful deviations by ascending signed cost; close-call exclusion compares `max(0, -cost)` with the nonnegative threshold. Replay records and category totals keep the signed value. A surface displaying its negation must label it estimated placement loss. A player choice estimated better than the Engine is an improvement, not a worst-loss moment. This resolves ranking semantics without changing the cost formula.

Later observed level-ups and roll-downs identify the player's actual action schedule only. Revaluation uses the decision's original snapshot, historical data and common seed; later shops, hits, fights, HP and outcomes never enter its initial state or simulated outcomes. Label that inferred schedule as observed after the decision. If the log cannot identify the schedule or choice, retain unavailable attribution rather than fabricate a policy.

### 2026-10-11 — Replay prerequisite extracted

Ticket 52 implements frozen historical replay contexts/records, public cache safety and locked review/tag/media access through the completed 35/36/37/40 seams. It can proceed while 41 finishes. This ticket consumes those contracts for full choice/policy attribution, costs, grouping, reports, evaluation and fitting; its acceptance remains open.

### 2026-10-12 — Full-game replay resource boundary

Ticket 41's synthetic candidate benchmark emits 17,741,188 bytes of full scored Advice/Line evidence. Evaluating and copying that evidence for every repeated capture poll would multiply memory, disk and runtime without identifying new player decisions. Segment decisions semantically before expensive valuation, retain stable decision IDs and required-field fingerprints, and use shared or lazy content-addressed evidence where appropriate. Preserve every original raw snapshot, log sequence, causal information prefix, timestamp, validity annotation and scored option; resource work must not remove evidence or make a later read fresh. Full-game resource use still requires explicit verification and remains separate from the 100 ms target-device gate.

### 2026-10-14 — Independently integrated worker and producer checkpoint

Exact `449bd5ef5d2014f0de600f482c2891ee1903e84e` was independently reviewed and merged as `14c58c310ba9503bb301ac1ac7835121280d8575`. This is a partial checkpoint providing protected typed review production, stable worker/job identity, immutable historical inputs, observed Line valuation, strict baseline qualification and the implemented metric/family-1 fitting slices. It lets runtime 55 consume committed interfaces. It does not complete this ticket; remaining requirements are enumerated in `docs/agents/review-policy-boundary.md`.

The author passed 524 Python tests without skips in 90.59 seconds, process exit 0, with two existing Torch warnings; actual Live-absent public checks passed 76 cases in 27.66 seconds. UI passed 35 tests and type/generated-type/build gates. Imports, schema, lock, scoped F821 and whitespace checks passed. An initial missing-worktree-dependency typecheck failed with exit 127 before `npm ci`; the subsequent checks passed. Committed-source service/worker/observed-Line verification passed 15 cases in 7.41 seconds.

The different merger inspected worker, identity, lock, log hash, semantic replay, signed valuation, baseline and prior contracts. Its independent 44-case public suite passed in 11.44 seconds; merged-root worker/policy/baseline/replay/storage verification passed 50 cases in 8.20 seconds, process exit 0, with import and lock checks. No blocker was found for the explicitly partial checkpoint. Full general joint-law integration, remaining domains/attribution/grouping, evaluation/fitting families and final acceptance remain open; owner matches, measurement runs, production data and Windows behavior are not qualified.

### 2026-10-14 — General finite joint-law implementation handoff

The isolated `implement/joint-sighting-law` slice adds `tft_engine.joint_sighting_law`, leaving existing inference and the deterministic predictor untouched. `JointSightingLaw` binds source/citation and immutable weighted hypotheses to a data snapshot, player, round and level. Each hypothesis contains a physical Board, declared active forms and capacity inventory evidence. Trait forms/items are checked against static certificates; canonical identities count traits once while physical units retain separate slot costs. A capacity adapter reuses the shared sourced slot, inventory and geometry checks.

The public predictor normalizes declared whole-board support and scores complete visible/hidden trait counts, including observed team-slot budget when present. Missing laws remain unavailable; invalid or conflicting support is rejected. There is no uniform latent law, product of marginals or posterior-certainty substitute. Positive probability underflow preserves a finite log score; genuinely zero event mass is distinguished without nonfinite JSON values. Production law qualification and the actual consumer/prior producer remain in open 42/48.

Public red/green worked cases now pass 24 tests, and the full Engine package passes 189 tests in 9.23 seconds, process exit 0. Import, schema, frozen lock, scoped F821 and whitespace checks pass. Early synthetic capacity test used an unsupported breakpoint and was corrected before the actual unresolved-form regression; exact floating-point comparisons were corrected to numerical tolerances after stable normalization. The module still requires different review/integration and the 42 consumer adapter; this handoff does not close the ticket.

### 2026-10-14 — Joint-law independent review corrections

Different-merger review reproduced boolean/float level aliases, zero item grants and retained mutable or untyped nested unit state. The author corrected those defects through the public joint-law seam. The six nested-state cases failed before the constructor validation and passed afterward. Certain-event log scores also now remain exactly zero rather than a positive rounding residue. Empty item-grant maps remain valid; nonempty grants require positive integral counts.

Exact source `baaed9c1dcff8e82d7671642e23e55bf5af8808a` passes 34 joint-law cases and the full 199-case Engine suite in 9.79 seconds, process exit 0; scoped F821 and whitespace checks pass. Independent review continues before integration. This remains a supplied-support likelihood slice, with the production producer, consumer integration and full ticket acceptance still open.
