---
id: 51
title: Preserve source-owned publication and cohort provenance
labels: [implementation:task, bug]
status: open
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
