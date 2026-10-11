---
id: 37
title: Automatic screen capture and purchase tracking
labels: [implementation:task]
status: closed
assignee: codex-capture
parent: 34
blocked_by: [47, 38]
---

# Automatic screen capture and purchase tracking

## Sources

- [docs/spec/capture.md](../docs/spec/capture.md)

## Acceptance

WGC/BitBlt capture, fractional HUD anchors and UI scale, OCR/template matching and name matching, change cadence and roll-down cadence, required captured fields, purchase/sell/pick tracking, fight events, stale values, capture gaps and core log integration.

This ticket implements and verifies the full capture software boundary. Actual HUD calibration, game-font assets, Windows behavior, recognition/cadence and target-device evidence remain in [ticket 49](049-capture-device-qualification.md). Ticket 45 owns final supervised application lifecycle wiring. A software closure here does not close those requirements or the parent specification.

Implement all referenced requirements. Verify through the approved public seams in [implementation contract](../docs/agents/implementation.md). Record platform checks separately; keep unmet acceptance explicit.

## Comments

### 2026-10-10 — codex (full capture resumed)

Reader ticket 38 is integrated and its software boundary closed. Resume full ticket 37 from the current `implement/mvp` tip; preserve the earlier clean prerequisite worktree. Capture must retain positively observed own trait counts and active Lux Origin separately from canonical shop/pool identity. Use the completed reader and the [Baseline publication contract](../docs/agents/baseline-boundary.md) rather than duplicating either. Missing visual evidence remains unavailable; runtime phase publication must use positively read phase evidence.

### 2026-10-07 — codex (dependency split)

Ticket 47 extracts the transport, OCR, tracking and reader contract. Ticket 38 depends on 47; this ticket then consumes the completed reader. This removes the former dependency cycle while keeping full automatic capture acceptance open.

### 2026-10-06 — codex (capture preflight)

The existing shell/core checks pass on macOS. Primary WGC binding documentation is at <https://github.com/NiiightmareXD/windows-capture/blob/main/windows-capture-python/README-Python.md>. `WindowsCapture(cursor_capture=False, draw_border=False, window_name="TFT")` uses event callbacks with `Frame.frame_buffer`, `on_closed`, and a capture control. Verify Python 3.14 Windows wheel availability and exact binding API during implementation. Do not use a desktop capture as proof that WGC excludes the overlay.

The committed probe JPEGs are available in `probe/screenshots/2026-10-04/`; the full 1,112-frame benchmark dataset and research branches referenced in planning tickets are absent from this checkout and origin. Keep calibration, recognition accuracy and Windows live-game checks explicit. Pinned upstream reader source was fetched read-only to the ignored `worktrees/references/tft-coach/` at commit `bf22ac92010aef321b9e67d6f125bb2109c41cf4` for ticket 38.

### 2026-10-06 — codex (freshness integration constraint)

A successful capture of an unchanged region must confirm its previously read fields as fresh without rerunning OCR. Otherwise the change-only cadence would make every unchanged field stale after two seconds. A failed or unavailable region must preserve the original read timestamp, allowing normal stale-field silence. Keep the originating OCR/reader source and confidence when confirming unchanged pixels. Test this through successive public snapshots, including a failed-frame span.

### 2026-10-07 — codex-capture (prerequisite delivered; full capture remains open)

Ticket47 supplies the tested transport/OCR/log boundary and [visual-reader contract](../docs/agents/capture-boundary.md). The generic JSON snapshot decodes into the merged Engine GameSnapshot contract. Own-view identity must be confirmed on the same frame before own units or inventory are emitted. OCR cannot identify 3D carousel units or item icons.

Still pending: ticket38 reader integration; carousel, choice and item visual fields; complete player HP and alive rows; copy/sell/pick/gift reconciliation and conflict keyframes; fight signals/outcomes; production lifecycle/calibration/video wiring in ticket45; genuine game-font templates; full HUD calibration across aspect ratios/locales/window modes; Windows WGC/BitBlt, overlay exclusion and live latency. The nine committed probe images support bounded software checks; the full historical benchmark dataset is unavailable. The transport currently supplies full in-memory RGB frames; region-only copy optimization and live budgets remain unqualified.

### 2026-10-11 — codex-capture (full software boundary delivered for integration review)

Implemented the complete public capture boundary in `CapturePipeline`, `SurfaceReader`, checked calibration profiles, `SegmentRecorder` and the `tft-capture inspect` CLI. The precise consumer fields, completeness certificates, event rules, copy accounting and lifecycle ordering are documented in [capture-boundary.md](../docs/agents/capture-boundary.md). The ticket remains open for independent integration review; this note does not close device qualification or the parent specification.

The software reads complete player rows and alive flags, positive paired phases, own traits and separate Lux Origin, augment text/tier/rerolls and held IDs, item offers and inventory categories, visual carousel unit/item options, and complete shop/Wisp fields. All missing reads retain their original timestamps and provenance. Ownership is certified only by agreement among all 28 board hexes, all nine bench slots, current unit count, positively complete own traits, known stars/items and pinned trait rules. Partial classifier observations do not establish zero opening ownership. Unknown equipped items or trait grants fail completeness. Opponent reads remain traits, hidden-row count and sighted level only.

Confirmed transitions produce purchases, sells with exact pinned refunds, picks, per-option augment rerolls, receipt-backed grants, fights/results/HP loss, recent opponents and level-up events with before/after XP and source timestamps. A gold drop does not establish an XP purchase. Long unobserved shop intervals, route gaps and conflicting ownership suppress attribution and produce ambiguity/conflict keyframes. Choice deduplication survives reconnects. Same-frame carousel/ownership overlap and a pick notification paired with an already updated held-augment HUD no longer lose or double-count acquisitions. Effect counters and Wisp purchase counts require positive observed baselines and remain unavailable otherwise; no remaining reward is inferred from static text.

The full-RGB-copy software requirement is implemented. WGC retains the owned native BGRA surface; the board reader borrows BGR pixels; requested rectangles make cached RGB crops. BitBlt uses an owned top-down BGRA DIB and flushes GDI before access. Full RGB materialization happens only for required keyframes or configured full video, with bytes and copy counts in each snapshot. Pinned Windows Capture 2.0.1 source confirms the NumPy exporter retains its mapped-frame owner. The synthetic copy test also verifies exact same-frame lossless keyframe pixels; a real CPU classifier still reads Karma in bench slot 9 from the committed probe through the native-BGR path. Native WGC/BitBlt execution and device lifetime remain unverified.

Keyframes remain lossless. The real FFmpeg path encodes timestamped variable-rate segments, records overflow gaps and visible encoder failures, and flushes final media before capture closure. Close is idempotent, records unfinished fights and terminal gaps, and still logs closure when encoding fails. Shutdown uses blocking queue operations and an encoder-thread join; it is not a nonblocking latency claim. Ticket 45 must stop and join capture, close the pipeline, surface failures and only then end the session log.

Verification on macOS: the approved snapshots/log/CLI red-green tests cover 34 full-capture cases plus 16 existing prerequisite cases. Full training-group core suite: 246 tests passed with exit 0; two existing Torch ONNX export deprecation warnings remain. Import contracts, schema check, frozen lock check and Ruff F821 pass. UI: 31 tests, typecheck, generated-type check and build pass. The first UI commands failed because the new worktree had no Node dependencies; `npm ci --ignore-scripts` installed the locked packages and all reruns exited 0. `uv run ruff` initially failed because Ruff is not a project dependency; the separate `uv tool run ruff` check exited 0. No failing command is counted as a pass.

The actual `tft-capture inspect` process, using real RapidOCR and reviewed crops from committed augment JPEGs 07 and 08, exited 0 and matched five canonical augment IDs, gold tier and observed reroll flags changing from all true to true/false/false. That bounded profile's stage crop was unreadable; it does not establish a complete game capture or live timing. Its explicit recorded timestamps and 0.25-second interval are fixture inputs. Actual FFmpeg encoding/decoding and the real CPU classifier are exercised in the software suite. Artifacts, generated logs, media and the probe profile are preserved only under ignored `worktrees/ticket-37-evidence/`; no generated game database or model weights are staged.

Remaining external qualification is explicit in ticket 49: genuine game-font templates; current full HUD and positive counter/receipt artwork; exhaustive item/carousel/slot calibration across aspect ratios, UI scale, window mode and locale; Windows WGC/BitBlt, overlay exclusion, mapped-buffer lifetime, OCR fallback and language packs; full owner-labelled accuracy, Maokai offsets, live cadence and target-device latency. The nine JPEGs and parser fixtures do not establish those results. Ticket 48 retains dated current-roster/data and asset qualification. Ticket 45 retains supervised start/end/reconnect/calibration, configured asset preparation and FFmpeg packaging. A missing panel, model, artwork or locale must expose unavailable status and leave dependent advice silent. The full historical 1,112-frame dataset and owner retraining dataset remain absent. Ticket 50 retains the unknown initiating cause of the historical native teardown abort; the current full check exited cleanly with its integrated pre-import prevention.

### 2026-10-11 — codex-capture (independent review: pinned equipped-item grants)

Independent integration review found that `CapturePipeline.from_data` did not project equipped-item trait grants. A fully observed board with an ordinary equipped item therefore remained uncertified unless a caller supplied a separate table. The projection now consumes only explicit pinned `Entity.values['trait_grants']` metadata, with an empty tagged mapping establishing a known zero contribution and a positive integer mapping establishing an emblem's contribution. Item and trait IDs must match the appropriate pinned entities; missing, untagged or invalid metadata leaves ownership uncertified. No name, recipe or category supplies a guessed zero. Board-read logs preserve each accepted item's source, citation, family, grant mapping and original data snapshot ID, and successful certificates name the pinned item-trait sources. The exact contract is documented in [capture-boundary.md](../docs/agents/capture-boundary.md). Production item-ledger qualification remains in ticket 48.

Public snapshot/log red-green cases cover ordinary empty grants, matching and conflicting emblem traits, absent and untagged metadata, unknown trait IDs, wrong entity kinds, blank item/trait IDs and boolean, zero, negative, fractional and string counts. The ordinary and emblem cases each failed before their projection was implemented; invalid cases exposed ten failures before validation was added. The corrected scoped capture suite passed 66 tests with exit 0. The full training-group suite passed 262 tests with exit 0 and the same two existing Torch ONNX export deprecation warnings. Import contracts, schemas, lock, Ruff F821 and diff checks passed. This bounded correction changes no UI code; its previous 31-test UI verification remains the earlier result, not a new run. The integration tip `9c5907f` adds only the runtime lifecycle note and was merged before final verification; root and other worktrees were not edited. Ticket status remains open for independent integration review.

### 2026-10-11 — Independent integration and software closure

The separate merger reviewed the full capture candidate and corrected equipped-item projection, then merged exact `9f0adb7` as `7963682`. Independent capture/session/process/real-reader/training checks passed 99 tests in 13.53 s, process exit 0, with the two existing Torch ONNX export deprecation warnings. Frozen training synchronization, both import contracts, schema, lock and diff checks passed.

The root then ran the complete suite on `7963682` with the actual pinned model cache: 262 tests passed in 16.23 s, no skips, process exit 0, with those same two warnings. The initial root command supplied an incorrect model-cache path and passed 257 tests with five reader checks skipped; that run did not verify those checks and was corrected before closure. Root import/schema/lock checks also passed. No UI code changed; its recorded 31-test/type/generated-type/build result remains earlier evidence.

Ticket 37 is closed for its full capture software boundary. Actual Windows/game HUD/recognition/cadence/overlay/device qualification remains in 49; production metadata and assets remain in 48; supervised application lifecycle remains in 45; the unknown historical native abort cause remains in 50. This does not close the parent MVP specification or establish end-to-end live readiness.
