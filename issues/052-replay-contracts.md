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
