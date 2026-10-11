---
id: 51
title: Preserve source-owned publication and cohort provenance
labels: [implementation:task, bug]
status: closed
assignee: codex-source-provenance
parent: 34
blocked_by: [36]
---

# Preserve source-owned publication and cohort provenance

## Sources and reproduced contract gap

Ticket 48's checked source preflight is `/tmp/tft-assistant-48-preflight.md`; its canonical evidence is in [48](048-production-data-readiness.md). The configured global augment-tier endpoint publishes its own timestamp and Set 18 identity but no patch, rank or region. `data/sources.toml` points its metadata route at unit statistics. `HTTPSource.metadata()` currently attributes that donor's patch and freshness to the tier payload. `SourceConfiguration` also stores Diamond+/all-region goals without enforcing them for every statistics provider. These configuration goals are not observed source facts.

## Acceptance

- Preserve publication timestamps and identity from the payload they describe. Separate any donor patch/revision hint from confirmed patch identity; never manufacture a tier patch or cohort from another endpoint.
- Represent unknown provenance explicitly through the public source/refresh boundary. Dependent enrichment or statistics remain unavailable/unqualified, or retain a qualified last-good value with a visible warning. Unknown metadata cannot become newly qualified by passing validation or by using a fixture with a fabricated patch.
- Enforce configured statistical cohort requirements against actual provider evidence, retaining unknown rank/region as unknown. Do not equate absent filters with Diamond+ or all regions, or normalize provider enums without a checked mapping.
- Preserve immutable snapshot persistence/round trips, source-specific refresh ages, last-good behavior, and existing interfaces where compatibility is possible. Expose the qualification reason in the CLI/status output and relevant snapshot provenance; recorded metadata must survive reload.
- Add red/green public source/refresh/CLI regressions using real cached response shapes or external-service fixtures. Cover differing payload/donor timestamps, missing patch/cohort, qualified metadata, last-good retention and persisted provenance. Do not call owner APIs or publish a production candidate.

This extracts the source-provenance software prerequisite from 48. It does not qualify a current patch, complete static tables, provider coverage, fitted parameters or the owner's live calendar.

## Comments

### 2026-10-11 — codex

Claimed from clean integration `c3a3dd7`. Implement in a separate worktree based on the current integration branch, using the previously approved immutable-refresh/source/CLI test seams. Coordinate additive statistic fields with ticket 41; its optional pick-stage and deduplication changes must be retained during integration.

### 2026-10-11 — codex-source-provenance

Implemented the software boundary on `implement/ticket-51`, including integration `38bf661`. The source adapter now reads the payload's own publication and identity; a separate endpoint provides only a donor hint. Unknown patch labels and cohorts are explicit. Requested cohort requirements apply to primary and fallback statistics. Rejected updates retain qualified last-good data with unchanged accepted timestamps and a separate persisted `last_attempt`; an offline CLI refresh preserves the rejection warning. Legacy or newly disqualified cached rows cannot supply thin-sample priors. Checked offline provider bodies cannot borrow a fabricated patch or freshness from a fixture envelope, and opaque patch enums are preserved without a guessed label.

Red/green public source, refresh and CLI slices reproduced donor timestamp attribution, unqualified tier/cohort installation, fallback qualification and age bypasses, cached-cohort grandfathering, lost rejection metadata/warnings, an unqualified thin-sample prior, fabricated offline metadata, opaque patch labels and invalid cohort goals. The existing statistics parser fixture now states its synthetic publication explicitly. No owner API calls or production publication were made.

Verification from `core/`: frozen train sync, `TFT_READER_TEST_MODELS=<ignored pinned-model directory> uv run --no-sync pytest -q` **281 passed, no skips, 16.20 seconds, process exit 0**; data-only **37 passed**. Import contracts **2 kept**, schema check, lock check, scoped Ruff F821 and diff checks all exited 0. The full suite emitted two existing Torch ONNX deprecation warnings; sync emitted the existing uv/build-backend version-range warning. The new [source provenance contract](../docs/agents/source-provenance.md) passed its scoped Unslop no-op preservation check, **19/19 constraints**. No UI code or message schema changed.

Software acceptance is ready for independent merger review; this ticket remains open until integration is verified. Current-patch source coverage, all-region/provider cohort evidence, static tables, fitted parameters and the owner's live calendar remain ticket 48's qualification work. These favorable process exits do not establish the initiating cause of the historical native abort tracked in 50. Ticket 41's additive pick-stage fields and row keys remain owned by its implementer and must be preserved when merging.

### 2026-10-11 — Independent integration and software closure

The different merger reviewed the full diff and merged exact `3e8a8de` as `91465f1`. Public source/refresh/CLI plus complete-capture/pipeline checks passed 103 tests in 4.14 s, process exit 0. Both import contracts, schema, lock and diff checks passed.

The integration root then passed all 281 Python tests in 14.61 s, no skips, process exit 0, with the same two existing Torch ONNX export deprecation warnings. Root import/schema/lock checks passed. No UI or message schema changed; earlier UI verification was not rerun for this data-only change.

Ticket 51 is closed for the provenance software boundary. Unknown source patch/cohort stays unavailable or retains qualified last-good data with an explicit persisted reason. Current provider coverage, reviewed production data and fits remain ticket 48; the historical native abort cause remains ticket 50. This does not qualify a production patch or close the parent specification.
