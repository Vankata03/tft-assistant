---
id: 14
title: "Benchmark local LLM inference beside a live TFT game"
labels: [wayfinder:task]
status: closed
assignee:
parent: 1
blocked_by: []
---

## Question

How fast is local LLM inference on the owner's PC, and what does it cost the game? Run `llama-bench` (llama.cpp, Vulkan build) with 8B and 14B 4-bit models, once with the GPU idle and once during a live TFT game. Record tokens per second, time to first token, VRAM use, and the game's frame rate with and without inference. Also run an 8B model on the CPU only. The agent runs the benchmarks; the owner plays the game for the second run.

Results inform "Advice engine architecture": whether the optional LLM phrasing layer is viable.

## Comments

### 2026-10-04 — claude-code (out of scope)

Closed as out of scope. "Advice engine architecture" ruled that v1 uses no language model: live advice and post-game review prose both come from templates. The benchmark only informed an optional LLM phrasing layer, which is now beyond the destination. Revisit after v1 if LLM phrasing returns as a fresh effort.
