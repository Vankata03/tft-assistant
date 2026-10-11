---
id: 42
title: Replay, post-game review and evaluation harness
labels: [implementation:task]
status: open
assignee:
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

### 2026-10-11 — Cost sign and observed Line interpretation

Preserve the specification's signed definition: `cost = Engine expected placement - player expected placement`. A worse player choice therefore has negative cost (Engine 3.1, player 4.2 gives -1.1). Top moments rank harmful deviations by ascending signed cost; close-call exclusion compares `max(0, -cost)` with the nonnegative threshold. Replay records and category totals keep the signed value. A surface displaying its negation must label it estimated placement loss. A player choice estimated better than the Engine is an improvement, not a worst-loss moment. This resolves ranking semantics without changing the cost formula.

Later observed level-ups and roll-downs identify the player's actual action schedule only. Revaluation uses the decision's original snapshot, historical data and common seed; later shops, hits, fights, HP and outcomes never enter its initial state or simulated outcomes. Label that inferred schedule as observed after the decision. If the log cannot identify the schedule or choice, retain unavailable attribution rather than fabricate a policy.

### 2026-10-11 — Replay prerequisite extracted

Ticket 52 implements frozen historical replay contexts/records, public cache safety and locked review/tag/media access through the completed 35/36/37/40 seams. It can proceed while 41 finishes. This ticket consumes those contracts for full choice/policy attribution, costs, grouping, reports, evaluation and fitting; its acceptance remains open.

### 2026-10-12 — Full-game replay resource boundary

Ticket 41's synthetic candidate benchmark emits 17,741,188 bytes of full scored Advice/Line evidence. Evaluating and copying that evidence for every repeated capture poll would multiply memory, disk and runtime without identifying new player decisions. Segment decisions semantically before expensive valuation, retain stable decision IDs and required-field fingerprints, and use shared or lazy content-addressed evidence where appropriate. Preserve every original raw snapshot, log sequence, causal information prefix, timestamp, validity annotation and scored option; resource work must not remove evidence or make a later read fresh. Full-game resource use still requires explicit verification and remains separate from the 100 ms target-device gate.
