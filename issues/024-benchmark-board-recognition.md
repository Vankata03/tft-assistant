---
id: 24
title: "Benchmark open-source board recognition on probe frames"
labels: [wayfinder:task]
status: open
assignee:
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
