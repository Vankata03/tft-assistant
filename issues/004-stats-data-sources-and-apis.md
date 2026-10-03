---
id: 4
title: "TFT stats data sources and their APIs"
labels: [wayfinder:research]
status: closed
assignee:
parent: 1
blocked_by: []
---

## Question

Which sources can supply comp, unit, item and augment statistics plus curated comp guides, and on what terms? Check the Riot API (TFT match, league and summoner endpoints, personal versus production keys, rate limits), Community Dragon and Data Dragon static data, and the stats and guide sites: tactics.tools, MetaTFT, TFT Academy, Blitz, Mobalytics, lolchess and any other major one. For each site: is there a public or partner API, what data it exposes, what its terms say about automated access, and how fresh the data is after a patch. Estimate what self-aggregation from the Riot API would cost in matches and time per patch to reach useful sample sizes.

## Comments

### 2026-10-04 — claude-code (resolution)

Findings: branch `research/stats-data-sources-and-apis`, file `research/stats-data-sources-and-apis.md`.

Only Riot has a documented API.

- **Riot API, personal key**: 20 requests per second and 100 per 2 minutes, per region. The key does not expire but cannot power a public product. A production key needs a working prototype and Riot approval.
- **Riot match records** hold placement, level, gold left, augments picked, traits, and units with items. They do not hold board positions, round-by-round econ or rolls, or augment offers.
- **Static data**: Data Dragon and CommunityDragon cover Set 18. Both are free and need no key.
- **MetaTFT and tactics.tools**: both serve undocumented JSON that needs no key. MetaTFT's comps, augments and items data updates within minutes, from about 30 million records per patch week. tactics.tools updates at least hourly. Neither site licenses reuse.
- **TFT Academy**: embeds structured records for 65 curated Set 18 comps, updated daily. Each record covers the early and final board, carousel, augments, stage tips and alternatives. Its terms say nothing about reuse.
- **lolchess**: forbids copying its data without consent.
- **Mobalytics, OP.GG and METAsrc**: forbid automated access.
- **Blitz**: terms unread, because its robots.txt blocks AI agents.

Self-aggregation from the Riot API needs about 12,500 matches (around 5 hours) for comp, unit and item statistics. Typical augment statistics need about 25,000 matches. Rare augments need about 125,000, which means pulling Diamond-and-above games from several regions for about a week per patch. Positioning, econ, roll and augment-offer statistics are not available from any API.

Open questions carried to "Data source strategy": whether the sites would permit reuse, what their counts measure, the real TFT rate-limit headers on the owner's key, and Blitz's terms.
