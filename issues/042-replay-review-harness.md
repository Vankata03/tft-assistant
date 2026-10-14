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
