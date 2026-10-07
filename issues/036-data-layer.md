---
id: 36
title: Validated patch data and immutable refresh snapshots
labels: [implementation:task]
status: open
assignee: codex-data-layer
parent: 34
blocked_by: []
---

# Validated patch data and immutable refresh snapshots

## Sources

- [docs/spec/data.md](../docs/spec/data.md)
- [docs/spec/patch-workflow.md](../docs/spec/patch-workflow.md)
- [docs/spec/tunables.md](../docs/spec/tunables.md)

## Acceptance

Named and typed data contracts, source-tagged TOML static/tunables/overrides, name/icon lists, statistics and Guide adapters with schema failure fallback, immutable snapshots and per-source age/patch checks, patch calendar, threat tags, new-patch CLI and Riot client.

Implement all referenced requirements. Verify through the approved public seams in [implementation contract](../docs/agents/implementation.md). Record platform checks separately; keep unmet acceptance explicit.

## Comments

### 2026-10-07 — codex (primary-source bootstrap verification)

Riot's [18.4 patch notes](https://teamfighttactics.leagueoflegends.com/en-gb/news/game-updates/teamfight-tactics-patch-18-4/) are published. The normal CommunityDragon URL uses the League data version, not the TFT patch label: `https://raw.communitydragon.org/18.4/cdragon/tft/en_us.json` returns 404, while `latest/cdragon/tft/en_us.json` returns current data. Its set 18 record has a stale `Set10` display name, shared NPC entries, and 74 current `DA_*` roster entries with the `TFTSet18` mutator. Validate stable roster IDs and mutator instead of selecting the first champion or trusting the display name.

Data Dragon `16.20.1` currently supplies 74 `DA_*` champion entries and 36 `DA_18_*` trait entries. TFT patch identity and EUNE live time still require their own mapping; the League bundle version does not establish either. A Tactics Tools browser check shows patch 18.4, Diamond+ selection with rank-group value 1, and patch enum 16200. These are dated provider observations, not permanent API guarantees.

Primary payloads are cached read-only under the ignored `worktrees/references/cdragon/`. Current statistical fits and owner-reviewed per-patch static tables remain separate from adapter fixture evidence.

### 2026-10-07 — codex-data-layer (software implementation and verification)

The `tft_data` workspace package now provides frozen entity, statistic, Guide and snapshot contracts; validated source-tagged static tables and tunable families; Dragon name/icon adapters; statistics, Guide, positioning and augment-tier adapters; owner overrides; threat tags; owner-confirmed patch boundaries; and patch/bootstrap/new-set CLIs. `DataStore.refresh()` publishes a content-addressed immutable snapshot, restores it across process restarts, retains last-good data after schema/provider failures, and records source age, patch, cohort and stale/changed state. `RefreshCoordinator` returns a background task and pins the active game's snapshot until publication is allowed between games. Riot requests use the local key file, owner PUUID filtering, ranked/set filtering, pagination, application/method limits and bounded retry handling. No owner API requests were made.

The public contracts are in `core/packages/data/src/tft_data/models.py`; `DataStore` and `RefreshCoordinator` are exported from `tft_data`. Statistics retain explicit `top4_rate`, `play_rate`, `unit_star`, `breakpoint`, `item_id`, `comp_id` and positioning data. Average placement is never converted into a top-four proxy. Guides retain carry/key IDs, early items, alternative builds and an optional explicit `cluster_id`. A verified cluster mapping must come from the source or an owner override; the adapter does not guess Academy-to-MetaTFT clusters. Optional Engine computation hooks accept the provisional `DataSnapshot`; `tft-data refresh --engine-computed` calls the public Engine growth-curve function.

The current cached CommunityDragon payload verifies 65 independent playable units, nine Lux form entities, 17 shared NPC/non-shop entities and 36 traits. NPCs have `kind="npc"`; forms have `kind="unit_form"` and `values.pool_id.value="DA_Lux18_Base"`. Both Lux ID conventions, `DA_Lux18_*` and `DA_18_Lux_*`, are covered by public refresh regression tests. Consumers must normalize form sightings and pool counts through `pool_id`, and use each form's actual traits or explicit `trait_rules` when evaluating alternatives. The data layer preserves those traits; it does not invent grants.

Verification on macOS: all 122 core/package tests pass, including 18 data/CLI public-seam tests; both import contracts are kept; Ruff checks and formatting pass for the data package. These results cover fixtures, persistence, failure recovery, CLIs and checked provider payload parsing. They do not qualify Windows capture, live gameplay, OCR accuracy, actual owner Riot access or statistical fits.

#### First-install bootstrap and remaining qualification

No production patch directory is committed. A first installation without `static.toml`, `tunables.toml` and `entities.json` returns an explicit unavailable refresh result, and the CLI exits with status 2. It does not publish fixture rules as current game data. Supply reviewed files before preparing the first candidate, from `core/`:

```sh
uv run tft-data bootstrap 18.4 \
  --data-dir ../data \
  --static-file /path/to/reviewed/static.toml \
  --tunables-file /path/to/reviewed/tunables.toml \
  --cdragon-file /path/to/checked/en_us.json \
  --ddragon-file /path/to/checked/ddragon-bundle.json \
  --dragon-version 16.20.1
uv run tft-data validate ../data/18.4
uv run tft-data refresh ../data/18.4 --sources ../data/sources.toml
```

Both TOML files must name the requested patch; static also requires `set_number`. Each `[fields.<name>]` contains `value`, `source` and, where available, `citation`; tunables also contain the required `family`. `config.py` defines all 24 required static fields, their table schemas and the named tunable families. The optional Dragon bundle is a JSON object keyed by `champion`, `item` and `trait`, with each value containing the corresponding checked Data Dragon response. Bootstrap validates all rules before publishing the candidate directory and writes `patch-diff.md` for review. The example bundle version is a dated League asset observation, not a TFT patch or EUNE live-date assertion.

The checked-in `data/sources.toml` is the source manifest: `schema_version`, requested statistics cohort, refresh source keys/fallback, and provider tables with `provider`, `kind`, HTTPS `url`, optional separate `metadata_url`, timeout, query and expected-filter fields. Provider schema changes produce warnings and preserve the last-good snapshot. Tactics Tools rank-group 1 is checked against the response aperture; MetaTFT cohort coverage still requires provider qualification.

Production qualification remains: reviewed current economy/pool/shop/round/sell rules; Wisp, encounter and augment effects/pools; trait variants and item recipes; level/item schedules and lobby rate; source-tagged tunable values with actual fit evidence; and an owner-confirmed EUNE live boundary in `data/patches.toml`. Tactics aggregate and verified three-star summary rows are supported; the inconsistent one-/two-star detail responses remain unqualified. Per-comp augment tiers and 28-cell positioning histograms have validated adapters but require checked production payloads. These source/configuration requirements remain explicit rather than being replaced with fabricated values. Windows/live-game qualification belongs to the downstream device checks.
