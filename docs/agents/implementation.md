# MVP implementation contract

Integration branch: `implement/mvp`, base `c521630`. Canonical specification: `docs/spec.md` and `docs/spec/`; detailed planning tickets win where more specific. Implementation task graph: `issues/034-implement-mvp.md`.

## Approved verification seams

The owner approved these boundaries on 2026-10-06: capture produces snapshots and game logs; data refresh produces validated immutable snapshots; the Engine returns advice; replay/review/harness consume logs; WebSocket and UI enforce modes and render surfaces; CLIs exercise workflows. Use red/green vertical slices at these public boundaries. Platform and external-service fixtures are acceptable; do not mock internal collaborators. Windows capture, OCR model accuracy and live-game performance need separate runtime evidence. Never present a fixture result as a live result.

## Worktree workflow

Read `/Users/vankata/.agents/skills/tdd/SKILL.md` in full before implementation. Each ticket runs on its own branch and worktree under the ignored root `worktrees/`. Confirm its merge base includes the integration tip before starting. Preserve the original checkout and other work. Before reporting completion, merge the current integration tip into the ticket branch, run relevant checks, inspect the diff, and commit. A merger agent integrates verified commits.

Keep communications sparse and cite paths/commits. Record a concise implementation/testing result in the ticket. Do not close requirements that remain missing. Do not fabricate live-game fields, current game data, statistical fits, model files or training results. Missing external assets must produce an actionable status and preserve last-good data, never invented advice.

## Tools

Python 3.14 is installed. A local uv tool environment is at `worktrees/tooling/bin/uv`; use its absolute path if uv is absent from PATH. UI commands run in `ui/`. Keep generated message schemas/types synchronized. All file deliverables use complete normal prose.
