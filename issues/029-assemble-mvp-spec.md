---
id: 29
title: "Assemble the MVP spec"
labels: [wayfinder:task]
status: open
assignee:
parent: 1
blocked_by: []
---

## Question

Write the MVP spec that the map's Destination calls for: one document, ready to hand to build sessions, compiled from the closed tickets listed in the map's *Decisions so far*. This ticket makes no new decisions. Every statement in the spec traces to a closed ticket, and each section links the tickets it draws on.

Do:

- **Location and shape.** Write the spec as `docs/spec.md`, split into linked files under `docs/spec/` only if one file grows past easy reading. Suggested sections: purpose and success measure; modes and policy; game-state capture; data sources and refresh; the Engine and each sub-engine (econ, level and roll Lines; board and lobby strength; transitions and pivots; items; augments; shop, Wisp and carousel; positioning); advice surfaces; game log, post-game review and evaluation harness; stack, runtime and repository layout; patch-day and new-set workflow; tunables index (every tunable, its owning sub-engine and its family); out of scope; open items.
- **Terms.** Use the glossary in `CONTEXT.md` exactly, and link to it rather than redefining terms.
- **Build order.** Propose an order of build slices that gets silent games logging early, since silent games feed the pre-coach baseline and the evaluation harness. Present it as a proposal for the owner to accept, not a decision.
- **Gaps and contradictions.** Where two tickets disagree, or the spec needs a decision no ticket made, do not decide it. List it under the spec's open items and raise it on the map as a new ticket.
- **Open items.** Carry the map's *Not yet specified* fog (the dedicated TFT client re-check) and the open build facts the tickets name, for example whether MetaTFT's `comp_augment_tiers` holds per-comp augment statistics.
- **Prose pass.** The spec is a human-facing project document, so finish with an `unslop` cleanup pass and its preservation check against the draft.

Resolved when `docs/spec.md` is committed, the owner has read it, and every gap it found is either a new ticket on the map or answered by an existing one.
