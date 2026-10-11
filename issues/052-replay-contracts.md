---
id: 52
title: Frozen replay contexts, records and safe review access
labels: [implementation:task]
status: open
assignee: codex-replay-contracts
parent: 34
blocked_by: [35, 36, 37, 40]
---

# Frozen replay contexts, records and safe review access

This extracts the log/context/cache/access prerequisite from ticket 42 so it can proceed before the complete decision-hook implementation in 41. All dependencies are independently closed software boundaries. Full review, policy reconstruction, signed costs, metrics and fitting remain in 42.

## Sources

- [Replay, review and harness specification](../docs/spec/review-and-harness.md)
- [Ticket 42](042-replay-review-harness.md), including cost sign and observed-policy interpretation.
- [Approved implementation seams](../docs/agents/implementation.md).
- Read-only preparation: `/tmp/tft-assistant-42-preflight.md` and `/tmp/tft-assistant-44-implementation-notes.md`.

## Acceptance

- Define versioned immutable JSON-safe replay context/record contracts retaining game, decision, original snapshot, Engine/data/model identities, historical information prefix, scored options and explicit unavailable reasons. Optional placement, paired uncertainty, observed-choice and shown-attribution values remain absent when unavailable; no guessed zeros or shown status.
- A public log-consuming producer resolves the game's exact historical immutable data snapshot and evaluates the shared Engine in review mode using only information available at that snapshot. It accepts the final decision-hook registry through the existing Engine interface, without importing Live or duplicating decision math. Future snapshots, sightings, shop draws, HP and outcomes cannot leak into an earlier evaluation. Missing/corrupt data or malformed committed records fail visibly. Positioning remains available as its explicitly non-costed domain.
- Preserve snapshot freshness and capture gap boundaries, game-start metadata and each record's authoritative log sequence. Cache provenance events cannot become game observations or recursively change the log fingerprint. Repeated identical polls retain sufficient semantic context for final 42 decision segmentation.
- Extend the public cache workflow with actual Engine commit plus relevant tracked/untracked dirty detection, tunables/data/log/schema/hook identity and complete/active-game policy. Dirty, changed or active logs cannot reuse stale records. A clean identical finished log can reuse its exact records.
- Public review access, tags and media enforce the stored game's review lock. Reject unknown decision IDs and invalid tags; accepted agree/disagree/unsure tags remain separate from regenerated content. Aggregate harness reporting can consume locked-game records internally without exposing detailed review or media through public routes.
- Verify through real temporary SessionStore logs and validated immutable DataStore snapshots: future-information exclusion, historical-data selection, gap/malformed/missing-data handling, JSON roundtrip, repeated polls, clean cache reuse and dirty/untracked/change invalidation, active-game behavior, locked access and unknown/valid tags. Use the actual merged Engine; external fixture inputs are allowed, internal collaborators are not mocked.
- Keep dependency direction compatible with the existing optional Live and Baseline import contracts. Coordinate the final consumer API with the ticket-42 implementer. Merge current integration before the final committed result and obtain a different merger agent.

## Scope remaining in ticket 42

Ticket 42 adds actual player policy/choice reconstruction and frozen same-seed valuation, signed paired costs, moment grouping and close calls, delivery/display matching, the complete review and replay CLI, all evaluation baselines and game-bootstrap gates, chronological fits and tunable-family restrictions. Ticket 44 owns transport and rendered review surfaces; 45 owns supervised jobs. This prerequisite does not close those requirements, qualification or the parent MVP.

## Implementation evidence

### 2026-10-11 — codex-replay-contracts

Implemented the scoped software boundary on `implement/ticket-52`, including integration `d3af392`. The public [replay contract](../docs/agents/replay-boundary.md) documents frozen contexts and records, actual historical Engine evaluation, causal history reconstruction, retrospective capture validity, cache identity and the locked review facade. The original snapshot and explicit seed are retained independently of the Engine's decision ID. Historical DataStore snapshots are restored by their original content ID without refresh or replacement.

Public regressions use real temporary SessionStore logs, validated DataStore snapshots, the actual merged Engine and temporary detached Git worktrees with matching runtime sources. Red/green slices reproduced future/sequence leaks, absent gap handling, malformed and mismatched records, untracked-source cache bypass, unchecked cached bytes, unlocked tags, changed-log publication and JSON version booleans. A later backdated capture-gap regression confirmed that retrospective validity must remain separate from the earlier Engine information prefix. The resulting annotations can exclude corrupted capture points without adding later game facts to earlier history. Non-costed positioning and repeated polls remain available for ticket 42's final reconstruction.

Cache reuse requires a clean matching source checkout, unchanged finished log, historical data/tunables, schema and hook identity. Cache provenance never becomes an observation or changes the observation fingerprint. Source/log inputs are checked again after evaluation and cache reads; publication checks the log under the storage lock. Cached bytes have a checked logged hash. Review reads, known-ID tags and logged media references respect the stored review lock. Low-level raw media reads remain available for capture and offline training. Accepted tags survive regeneration in their separate file.

Verification from `core/`: frozen train sync and full train-group tests **308 passed, no skips, 19.28 seconds, process exit 0**; replay/storage tests **34 passed, 3.96 seconds, exit 0**. Import contracts **2 kept**, schema check, lock check, scoped Ruff F821 and diff checks exited 0. The full suite emitted two existing Torch ONNX export deprecation warnings; sync emitted the existing uv/build-backend version-range warning. The scoped documentation pass made no editorial change and preserved **22/22 constraints**. No UI code or message schema changed.

This ticket remains open for independent integration review. Ticket 42 still owns player policy, signed paired costs, grouping, display attribution, metrics, fits and replay/review/harness CLIs; ticket 44 owns rendered surfaces and 45 owns review jobs. Owner data, Windows accuracy/cadence and actual model calibration remain separate qualification work. These clean process exits do not establish the initiating cause of the historical native abort in ticket 50. No owner data, API token, Live import, push, PR or Vault write was used.
