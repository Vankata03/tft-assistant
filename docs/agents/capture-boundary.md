# Capture boundary and reader integration

Ticket 47 supplies transport, OCR, conservative shop transitions, freshness and durable logs. Ticket 38 implements the injected visual reader. Ticket 37 integrates all required visual fields and complete tracking. The production lifecycle owner in ticket 45 starts and stops capture; it supplies the current game ID, pinned data catalog, client configuration and owner identity.

## Running capture

Create `HudLayout.from_config(game_cfg_path)` to read `[HUD] GlobalScale` and `[General] WindowMode`. The fallback `HudLayout()` uses the committed 2560×1440 probe geometry and explicitly records `scale_source="probe-reference"`; it is not a successful calibration claim. Regions use fractions of the game client rectangle. Central, side and bottom anchors scale with client height and UI scale. `CapturePipeline(..., regions={name: (x0, y0, x1, y1)})` accepts explicit fractional calibration overrides.

Construct `CapturePipeline(game_id, ocr=reader, sink=session_store, layout=layout, catalog=catalog, visual_reader=vision, own_player_name=owner_name)`. Start the same game in `SessionStore` first. `CaptureRunner(WindowsCaptureSource(), pipeline).run(on_snapshot=callback)` belongs on a dedicated CPU thread. Call `stop()` and join that thread before ending the game log. Capture uses no input automation or process-memory access. The source rescans visible windows on each tick, rejects ambiguous or minimized windows, uses borderless WGC first, and falls back to a BitBlt client-area crop. Source changes, failed spans and replaced windows produce durable events. The caller must surface capture status from the log callback.

The callback receives JSON-compatible snapshots. `GameSnapshot.from_dict(snapshot)` restores the immutable Engine contract. Additional root metadata consists of `stale_fields`, `capture_layout` and `roll_down`. Each observed field has `value`, a timezone-bearing ISO `read_at`, `source` and `confidence`. Snapshot IDs include a capture-instance nonce so restarting capture in the same game cannot collide with old IDs. Failed frames or reads retain original values and timestamps. Successfully captured unchanged regions advance `read_at` while retaining recognition provenance and confidence. Missing values remain missing.

Normal change checks request a 250 ms interval. Two confirmed paid rolls within two seconds, or `pipeline.start_roll_down(gold_floor=..., timestamp=...)`, request a 1/15 second interval for shop and gold between normal checks. Other regions retain their regular checks. Roll-down ends after three seconds without a confirmed roll or a freshly read gold floor. The runner subtracts processing time from the wait; this scheduling policy does not prove the Windows latency budget. The lifecycle owner calls `finish_calibration_round()` after the first round, including a round with no readable HUD. It records an actionable `calibration_status` when nothing was read. That hook requires runtime wiring in ticket 45.

## OCR adapters

`TextLine(text, confidence, box)` uses a normalized `(x0, y0, x1, y1)` box within its OCR crop. `NameCatalog` accepts `{kind: {entity_id: localized_name}}` for units, traits and Wisps. Supply the pinned client-locale names from the data snapshot. Unknown or closely competing matches return no identity.

`DigitTemplates.from_directory(path)` requires calibrated `0.png` through `9.png`, `minus.png` and `slash.png`. Genuine game-font assets remain to be prepared; the synthetic glyph test establishes matcher behavior only. `RapidOCRReader` requires explicit local detector and recognizer models, plus a dictionary when the recognizer does not embed one. `from_bundled_models()` selects the verified small ONNX models shipped in RapidOCR 3.9.2. All execution providers are CPU-only. `WindowsOCRReader(locale)` requires the installed Windows language pack. Its confidence is a configured policy value because Windows OCR provides no scores. `HybridOCR(digits, names, fallback=...)` selects numeric templates before text OCR and records the actual selected source. No adapter downloads assets during capture.

## Visual reader contract

The public protocol is `tft_capture.vision.VisualReader`. Implement:

```python
read(image: PIL.Image.Image, *,
     regions: dict[str, tuple[int, int, int, int]],
     own_view: bool | None) -> VisionRead
```

`image` is an RGB PIL image of the current game client. Pixel regions are `(left, top, right, bottom)` within that image; right and bottom are exclusive. Standard region names are `board`, `cards`, `shop`, `traits`, `players`, `scouted` and the numeric HUD names. Explicit calibration can add `bench` and `carousel`. During fast shop sampling the region map can contain only `shop` and `gold`. Readers must not emit fields from absent regions. The pipeline avoids repeated visual reads when its supplied visual regions and own-view state are unchanged; a reader may also cache individual changed regions internally.

`own_view=True` requires the owner name to match a label successfully read or confirmed on this same frame. `False` means another player is positively identified. `None` means identity is unavailable. The pipeline updates identity before invoking the reader and rejects own board, bench and inventory values unless `own_view=True`. The reader must never emit opponent units, items, stars or positions. Trait sightings are captured separately and require a known owner identity and a freshly confirmed opponent label, level, round, trait rows and hidden-row count.

Return `VisionRead(fields, source, confidence, inventory_complete=False)`. Every supplied field must be a positively observed JSON value. An absent key means unreadable; an empty list means positively observed empty. An unreadable result must omit that field rather than repeat its previous value. Exceptions and empty results stay retryable without advancing timestamps. `confidence` is between zero and one. `inventory_complete` states whether the own inventory was completely observed; the pipeline records it beside successful own board/bench fields. It is false by default and must remain false for partial observations.

The existing own board shape is:

```json
{"board":{"units":[{"unit_id":"shen","stars":1,"items":[],"position":0}],
          "bench":[],"trait_counts":null}}
```

A separate `bench` field, if supplied, is a list of the same unit objects. `position=null` represents unknown position. Missing equipped item identities must not be claimed as an empty item list unless emptiness was observed. Complete reader reconciliation belongs to tickets 37 and 38.

`shop_empty_slots` is a list of zero-based positions in the five-slot shop strip. Supply it only when a slot is positively observed empty. Failed name OCR alone is insufficient. The pipeline combines this evidence with same-round shop transitions and a matching gold delta to log a unique purchase. A gold delta alone, multiple empty slots or conflicting evidence cannot establish a unique purchase. The tracker records confirmed acquisitions, not a complete initial inventory. Ticket 38 adds conservative reader reconciliation; ticket 37 adds complete ownership, sells, gifts and copy totals.

A positively observed `planning_phase` boolean can also be returned; capture never defaults an unread phase to planning. Carousel and augment/choice fields can be returned independently of `own_view`. Their final entity shapes must be agreed with the planning engine before ticket 37 integration. OCR cannot identify 3D carousel units or equipped item icons.

## Evidence and pending qualification

MacOS seam tests use the real `SessionStore` and recorded external OCR/window/visual outputs. They verify timestamps, failed spans, durable snapshots, keyframes, conservative purchases, roll-down cadence, calibration status and own-view transitions. A CPU RapidOCR test reads the known gold value 28 from the committed `02-shop-with-wisp-2-3.jpg`. That single field does not establish full-field recognition accuracy or runtime speed.

Primary binding and package references were checked for the Python 3.14 Windows AMD64 target: [Windows Capture API](https://github.com/NiiightmareXD/windows-capture/blob/main/windows-capture-python/windows_capture/__init__.py), [Windows Capture package](https://pypi.org/project/windows-capture/), [RapidOCR implementation](https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/main.py), and [Windows OCR API](https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr.ocrengine.recognizeasync?view=winrt-28000). Windows Capture 2.0.1 has a CPython stable-ABI AMD64 wheel; RapidOCR 3.9.2 is universal; ONNX Runtime 1.30.0 and the WinRT 3.2.1 packages provide CPython 3.14 Windows AMD64 wheels. This is package availability evidence, not installed Windows execution.

Actual WGC, BitBlt, mixed-DPI and window-mode behavior, overlay exclusion, locale packs, full HUD calibration, recognition accuracy and roll-down latency remain unqualified. The full historical benchmark dataset is absent. Production capture wiring, visual choices, complete player rows, carousel identities, item fields, sells, picks, gifts, fight outcomes and video sampling remain outside this prerequisite and explicit in tickets 37, 38 and 45.

## Own-board reader and model assets

`BoardReader.from_version(cache, data=pinned_data_snapshot, templates=bank, foot_offsets=calibration_path)` loads the six local assets selected by `tft_capture/models.json` and verifies their SHA-256 values. Prepare that cache explicitly with `uv run tft-train prepare-models --cache <models-directory>` before capture. On Windows, use the application models directory under `%LOCALAPPDATA%\tft-assistant\models\`. Capture performs no asset downloads. A missing, corrupt or wrong-set model raises `ReaderUnavailable` with a preparation instruction; the lifecycle owner must surface that status and retain previous field timestamps.

The adapted geometry and preprocessing in `_coach.py` retain the full upstream MIT notice and pin commit `bf22ac92010aef321b9e67d6f125bb2109c41cf4`. Both classifiers explicitly use `CPUExecutionProvider`. Reader and OCR constructors disable ONNX Runtime telemetry before creating sessions. Training dependencies remain in the explicit `train` group and are imported only when fine-tuning runs.

`BoardReader.from_data(model_directory, data_snapshot, ...)` maps English visual classes through stable current-set IDs when client names are localized. Lux forms share the base visual identity until a separate positive observation establishes the active form. The reader does not infer a chosen Origin or its traits. Full capture must retain visible own traits and Origin evidence separately. `board_reader_identity_min` comes from the pinned data snapshot; its default is 0.55.

The widened health-bar search retains tall candidates before classification. Reviewed foot-offset calibration maps each champion's health bar to its foot coordinate. Maokai without a reviewed offset has `position=null`; no measured Maokai value is bundled. All nine bench slots are examined. The reader respects supplied pixel boundaries; an explicit `bench` region can override the bench area contained in the broader `board` region. These are the pinned probe geometry and software policies, not qualified geometry for every UI scale or aspect ratio.

`board_observations` contains crop bounds, bar coordinates, zone, slot/hex, raw classifier label, current unit ID, identity confidence, stars, star confidence, equipped items and positive partial item sightings. Unknown stars or items remain `null`. A calibrated `_empty` item template is required to establish empty equipped slots; an unmatched icon does not establish emptiness. `TemplateBank.load(icon_cache)` verifies prepared icon hashes. `uv run tft-train templates --source <cdragon-json> --patch <patch> --cache <icon-directory>` prepares templates before capture and groups identical icon URLs under a canonical ID with stable aliases. Cape and legacy Ring artwork therefore do not compete as separate classes. Supply a calibrated `item_bench` pixel region to obtain positive `item_bench_observations`; its `complete` flag remains false. Full inventory geometry and accuracy require ticket 49 evidence.

Pass the same game's committed events through `CapturePipeline(..., tracking_events=events)` when resuming. An independent `ownership` event has `{"copies":{"unit-id":3},"complete":true}`. Confirmed purchases add copies; they do not establish a complete initial inventory. Reconciliation preserves reader geometry and details, prefers the reader above the identity threshold, and substitutes tracking only when complete ownership leaves a unique possible identity. Conflicting evidence produces `reader_disagreement` events and keyframes. Remaining tracked units have unknown positions and items in `tracked_units`; incomplete fields cannot become fabricated Engine units. Changed observations produce `board_read` events with model version and label map, followed by lossless `own_board` keyframes. Session storage applies its existing media retention policy.

## Offline crop and training commands

Run these commands from `core/`; use a new candidate directory for each training run:

```text
uv run tft-train crops --log <game/events.jsonl> --output <crop-directory>
uv run tft-train split --dataset <crop-directory/crops.json> --output <split.json>
uv run --group train tft-train train --current <current-model-directory> --split <split.json> --output <candidate-directory>
uv run tft-train compare --current <current-model-directory> --candidate <candidate-directory> --split <split.json> --report <report.json>
uv run tft-train accept --current <current-model-directory> --candidate <candidate-directory> --split <split.json> --report <report.json> --pointer packages/capture/src/tft_capture/models.json --cache <models-directory>
uv run tft-train calibrate --samples <reviewed-foot-samples.json> --output <foot-offsets.json>
```

Crop harvesting pairs a keyframe only with a board read at its exact timestamp. Labels require complete independent ownership and matching copy counts. A unique remaining identity can label the final unread crop and derive its stars from one, three or nine copies. Ambiguous crops remain unlabelled. Every crop records its game, keyframe, image hash, bounds, label source and reader version. Reviewed foot samples include `champion`, `bar=[x,y,width,height]`, `foot_y`, `source` and `game_id`; calibration records per-champion medians and sample counts.

The split keeps whole games together and groups games sharing identical crop bytes. It verifies image hashes, game separation and split fingerprints. The classifier reconstructs the actual current EfficientNet-B0 parameters from ONNX, including folded normalization, and checks initial logit parity before training. Fine-tuning and ONNX export run on CPU. Export parity must pass before the complete candidate bundle is published. The candidate retains every current class; training does not change the accepted pointer.

Comparison evaluates current and candidate on the same immutable held-out split and deduplicates identical pixels. Every current class needs at least 20 distinct labelled crops across five held-out games. Reports include exact counts, per-class correct predictions, descriptive Wilson intervals and paired whole-game regression probabilities. Absent classes are unqualified. Acceptance requires retained label coverage, qualified ownership/review labels, candidate overall accuracy at least equal to current, and no class regression beyond the one-sided 0.05 paired-game threshold. This gate qualifies the unit classifier; candidate star weights and metadata must remain identical to current until a separate star gate exists. Promotion reruns comparison rather than trusting an edited report and verifies and caches all six files before atomically replacing the portable pointer. It hashes both bundles before inference and checks those hashes after comparison and copying and before pointer publication. A rejected candidate leaves the last-good pointer unchanged and removes any new cache version created by that attempt. Commit a changed pointer only after reviewing its report; weights remain outside Git.

The nine committed JPEGs and synthetic fixtures do not qualify actual retraining. Full owner-labelled class coverage, Lux-form and five-cost crops, measured Maokai offsets, Windows accuracy and target-device latency remain in ticket 49. Ticket 37 still owns visual choices, complete event inference, full inventory fields and runtime capture integration.
