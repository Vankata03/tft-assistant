---
id: 24
title: "Benchmark open-source board recognition on probe frames"
labels: [wayfinder:task]
status: closed
assignee: Ivan Terziev
parent: 1
blocked_by: []
---

## Question

How accurately and how fast does an existing open-source board reader recognise units, star levels and items on this owner's Set 18 frames? "Game-state capture route" uses a reused vision model alongside purchase tracking only if this benchmark shows it is good enough; otherwise v1 reads the board by purchase tracking alone and scouted opponents give traits only.

This is an AFK task. Run [TFT-COACH](https://github.com/mallangmallang0619/TFT-COACH) (MIT) over the local probe frames in `probe/out/2026-10-04_140538/` (1,185 PNG frames at 2560×1440 from the Unreal client, gitignored). Do not use TFT-Copilot (PolyForm Noncommercial) or wbLoki/tft-coach (no licence) code. TFT-COACH targets a `TFT.exe` window, while this client is `TFTClient-Win64-Shipping.exe` with window title "TFT"; the benchmark works on saved frames, so only its screen regions may need adapting to 2560×1440.

Measure, separately for the own board, the bench and scouted opponent boards:

- Unit identity accuracy per hex.
- Star-level accuracy.
- Item accuracy (equipped items and the item bench).
- CPU latency per board pass with onnxruntime on the Ryzen 7 7800X3D, and whether DirectML on the RX 6800 is needed at all.

Ground truth without hand-labelling every frame:

- The final board of the probe game from `tft-match-v1` (personal key, see "Register a Riot personal API key"): units, star levels and items.
- Per-frame agreement between the traits implied by the recognised units and the trait panel read by OCR.
- A spot check of about 30 crops that the owner confirms, if the two automatic checks disagree.

Suggested targets for the owner to judge against: unit identity and star level at least 95 % on the own board and bench, items at least 90 %, and one board pass under 100 ms on the CPU. Record the measured numbers, the regions used, and the code location (a throwaway branch, not `main`).

## Comments

### 2026-10-04 — claude-code

Progress, not a resolution. Claimed and started; the benchmark itself has not run yet.

- **TFT-COACH** (commit `bf22ac9`, 2026-09-10, MIT) already targets Set 18 on the Unreal client at 2560×1440. It accepts `TFTClient-Win64-Shipping.exe` as the game process, and its regions in `backend/config.py` are calibrated on 2560×1440 Unreal frames, so no region changes are expected for the probe frames.
- **Pipeline**: board units are found by their green health bars (`backend/board_crops.py`), cropped and classified in one batch with an EfficientNet-B0 ONNX model (192 px input, 11,506 training crops, reported validation accuracy 99.6 %). Star levels come from a MobileNetV3-small ONNX model (96 px, only 443 training crops). Equipped items are matched per icon slot against Riot item artwork; no item model is trained. Bench slot 9 is skipped as unsafe (the arena portal animates behind it).
- **Gaps found so far**: component templates are not bundled (`assets/templates/components/` is empty and `backend/fetch_templates.py` fills it from CommunityDragon), so item-bench components cannot be matched out of the box. Trait-panel OCR needs Tesseract, which is not installed on the owner's PC. Health-bar detection keys on green bars, so scouted opponent boards may need a different colour range.
- **Blocked**: running the cloned TFT-COACH code needs the owner's approval in this session, and the development API key in `$HOME\.config\tft-assistant\riot-api-key` now returns 403, so the probe game's final board cannot be fetched until the key is regenerated.

### 2026-10-04 — claude-code (resolution)

Resolved. TFT-COACH (commit `bf22ac9`, MIT) ran unchanged over the 1,112 in-game probe frames. Its regions already fit the 2560×1440 Unreal client. Findings and scripts are on the throwaway branch `research/board-recognition-benchmark` in [`research/board-recognition-benchmark.md`](../research/board-recognition-benchmark.md) (commit `9920874`). Ground truth was the probe game's final board from `tft-match-v1`, plus a trait-panel consistency check read by eye on five planning frames (2-3 to 6-3). The owner skipped Tesseract.

**Measured**

- **Latency**: one board, bench, star and item pass takes 24 ms median and 52 ms p95 on the CPU (onnxruntime, 4 threads). DirectML on the RX 6800 is not needed.
- **Own-board identity**: every accepted read was right. All 349 late-game reads named a unit on the final board, and all five trait-checked frames agree with the trait panel. Recall falls late in the game: every unit was read in the three checked frames before stage 5, 8 of 9 at 5-3, and 6.0 of 10 on average across 58 stage-6 frames.
- **Late-game misses**: there are three, each with a specific cause.
  - **Maokai** is never cropped, because his health bar sits above the bar search window. This is geometry, not the model: he was read at 0.86 where his bar fell inside the window.
  - **Lux's Avatar form** in this game is missing from training. Lux is not in the top 3 predictions.
  - **Ashe** scores 0.48–0.57 on the board against the 0.55 floor, but 0.87 on the bench, so board views of her are under-represented in training.

  TFT-COACH trains on crops hand-sorted from its author's own games, so thin 5-cost data is the likely cause for Lux and Ashe. That is an inference; per-class counts are not published.
- **Star level**: all accepted late-game reads match the final star levels.
- **Equipped items**: 171 of 177 read, none wrong. All misses are Tactician's Cape, which has no template. Item moves made with an Item Remover were tracked correctly.
- **Item bench**: not measured. TFT-COACH ships no component templates; they would be fetched from CommunityDragon.
- **Bench**: plausible and consistent with later boards in three frames, but slot 9 is never read (it is skipped because the arena portal animates behind it). There is no ground truth for the bench.
- **Scouted boards**: TFT-COACH does not read opponents. It searches green bars on the player's half only, and enemy units carry red bars. An ad-hoc test of red-bar crops from combat frames gave a confident, plausible label for about half of the real opponent units. No planning-phase scout frame was found in the probe.
- **Riot API**: `tft-match-v1` returns HTTP 403 with `error code: 1010` when Python's default `urllib` User-Agent is sent. That is Cloudflare rejecting the client, not a bad key, so any API client must set its own User-Agent.

**Owner's verdict**: v1 uses TFT-COACH's board reader with fixes, alongside purchase tracking. Purchase tracking fills any hex the reader leaves empty and flags any disagreement between them. Neither source is trusted alone.

Build fixes the reader needs:

- Widen the bar search upward, using per-champion foot offsets (Maokai first).
- Retrain on crops from the owner's own game logs, labelled by purchase tracking, to cover Lux's Avatar forms and board views of 5-costs.
- Add a Tactician's Cape template and fetch the component templates.
- Read bench slot 9.

Scouted opponent boards give traits only in v1. Reading opponent units would need its own bar detector and geometry, validated on planning-phase scout frames.
