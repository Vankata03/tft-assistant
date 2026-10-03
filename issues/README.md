# Issue tracker (local markdown)

This repository tracks its work as Markdown files in `issues/`, one file per issue. There is no hosted tracker yet.

## File format

Each issue is `issues/NNN-<slug>.md`. The number is the issue id and never changes. Front matter:

```yaml
---
id: 7
title: Prior art for TFT decision engines and the train-vs-LLM question
labels: [wayfinder:research]
status: open            # open | closed
assignee:               # empty = unclaimed
parent: 1               # map id, for child tickets
blocked_by: []          # ids of issues that block this one
---
```

The body follows the front matter. Comments are appended under a `## Comments` heading, newest last, each starting with `### YYYY-MM-DD — <author>`.

## Wayfinding operations

- **Map**: the issue labelled `wayfinder:map` (currently [TFT Assistant MVP spec](001-map-tft-assistant-mvp-spec.md)).
- **Child ticket**: an issue whose `parent` is the map id.
- **Blocking**: the `blocked_by` list. This tracker has no native dependency view, so the list is the source of truth.
- **Claim**: set `assignee` to the dev driving the map before any work.
- **Unblocked**: every id in `blocked_by` has `status: closed`.
- **Frontier**: open, unblocked, unassigned children of the map. List it with:

```bash
bash issues/frontier.sh
```

- **Resolve**: append the answer as a resolution comment, set `status: closed`, and add a one-line context pointer to the map's *Decisions so far*.
- **Research findings**: committed on a throwaway `research/<slug>` branch as `research/<slug>.md`; the ticket links the branch and file.
