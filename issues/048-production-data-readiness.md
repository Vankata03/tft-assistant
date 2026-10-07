---
id: 48
title: Prepare and qualify the first sourced patch-data candidate
labels: [implementation:task, qualification:data]
status: open
assignee:
parent: 34
blocked_by: [36, 40, 41]
---

# Prepare and qualify the first sourced patch-data candidate

This ticket extracts the production data preparation and qualification left explicit by ticket 36. Adapter and immutable-refresh software is complete; a fresh installation still needs a valid patch directory before it can produce game advice.

## Acceptance

Prepare a concrete first-patch candidate using the implemented bootstrap workflow and checked primary Dragon payloads. Supply source-tagged static and tunable files, preserve citations and uncertainty, validate the complete candidate, and provide its patch diff for review. Defaults and carried values must remain visibly qualified. Unknown mechanic effects must suppress dependent advice; they must not become fabricated current-game values.

Include current economy, pool, shop, round and sell rules; Wisp, encounter and augment effects and pools; trait variants and item recipes; level/item schedules and lobby rate. Check configured statistics cohorts and enrichment payloads, including per-comp augment tiers and positioning where the provider supplies them. Document source gaps precisely.

Fitted coefficients require actual data and the harness acceptance gate. An initial default is not a statistical fit. The EUNE patch calendar requires an owner-confirmed live boundary; a League bundle version or a patch-note publication time is insufficient. Do not call the owner's API, start their measurement run or claim human-played games without their corresponding instruction.

Keep software checks separate from owner review, external-service qualification and live-game evidence. If owner information or unavailable observations remain necessary, prepare every independent artifact first and record the exact unresolved fields rather than closing this ticket.

## Context

See ticket 36's first-install bootstrap command and qualification record. Checked source payloads are cached read-only under ignored `worktrees/references/cdragon/`; `data/sources.toml` contains the source manifest. Current source observations are dated in ticket 36. The canonical software specification remains `docs/spec/data.md`, `patch-workflow.md` and `tunables.md`.
