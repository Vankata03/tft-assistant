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
