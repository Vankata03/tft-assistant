---
id: 25
title: "Stack and runtime"
labels: [wayfinder:grilling]
status: open
assignee:
parent: 1
blocked_by: []
---

## Question

What language, runtime and packaging does the coach use, and how do capture, the Engine, the game log and the surfaces talk to each other? Constraints already settled: capture is screen capture of the "TFT" window plus the League client API ("Game-state capture route"); OCR and an onnxruntime vision model run on the CPU on changed regions at about 4 Hz; the Engine is a deterministic pure function on the CPU with a 100 ms budget per snapshot ("Advice engine architecture"); the surfaces are an overlay, a second-screen window and voice; the Live advisor must be a separable component that a public build can omit ("Policy stance and feature modes"); data is refreshed between games ("Data source strategy"). Decide the process layout (one process or several), the message format between components, how the overlay draws over a borderless game window, and how the pieces are packaged and started for the owner's Windows 11 PC.
