---
id: 2
title: "Riot third-party app policy for real-time TFT advice"
labels: [wayfinder:research]
status: closed
assignee:
parent: 1
blocked_by: []
---

## Question

What does Riot's current (2026) third-party application policy allow a TFT app to show or do during a live game? Cover real-time decision advice ("level now", "roll", "buy this unit"), augment and item statistics during selection, overlays, screen capture and reading game memory, and how Vanguard treats each. How do approved apps such as Blitz, MetaTFT, TFT Academy and Mobalytics stay compliant, and what has Riot banned or restricted (for example the 2023 augment-stats restriction)? Does the policy differ for a personal, unpublished tool that has no Riot production key? Cite Riot's own pages and developer announcements, with dates.

## Comments

### 2026-10-04 — claude-code (resolution)

Findings: branch `research/riot-third-party-policy`, file `research/riot-third-party-policy.md`, 22 graded and dated sources.

- **Real-time prescriptive advice is forbidden.** Riot's TFT game policy rules out recommendations that "adjust in real time based on the player's actions in game and give direct prescriptions". It also says apps "cannot make suggestions based on the player's current game state". Riot gives "pushing players to re-roll or level up" as an example. This is the coach's core loop.
- **The surface does not matter.** The rules cover apps and overlays during the game, so an overlay, a second screen and voice are treated the same.
- **Allowed in-game:**
  - Static guides chosen before the game.
  - Highlighting the chosen comp's units in the shop.
  - Stage-keyed leveling guidance.
  - Augment statistics during selection.
  - Post-game analysis.
- **Banned in-game:** scouting and tracking opponents during play.
- **How approved apps comply:** Blitz, MetaTFT, TFT Academy and Mobalytics register and have every feature audited.
- **No exemption for a personal tool.** The player Terms of Service ban unauthorized third-party programs that interact with Riot services, and Riot's support page calls "drawing conclusions for you during gameplay" unacceptable. The opt-in real-time mode therefore risks the owner's account. No published ban precedent was found.
- **Vanguard:**
  - Vanguard has blocked external memory reading since 2024-04-30.
  - Riot announced on 2026-09-29 that from **2026-10-06** all unknown third-party apps are blocked from game memory by default. Approved tools have until April 2027 to move to official APIs.
  - This likely affects Overwolf's live TFT data. That is an inference: Riot does not name Overwolf.
- **Screen capture:** Riot has made no statement allowing or banning it.

Open questions carried to "Policy stance and feature modes" and "Game-state capture route": Riot's stance on read-only screen capture, which Overwolf TFT features depend on memory access, and the approved scope of MetaTFT's win chance and lobby scouting.
