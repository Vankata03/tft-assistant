---
id: 7
title: "Prior art for TFT decision engines and the train-vs-LLM question"
labels: [wayfinder:research]
status: closed
assignee:
parent: 1
blocked_by: []
---

## Question

Do we need to train a model, and if so what kind? Survey prior art: academic and open-source work on TFT agents (reinforcement learning, imitation learning, search), LLM-based TFT assistants, and the recommendation features of existing coach apps. For each, report the method, the data it needed, how well it played, and whether code or data are public. Then assess three engine options for this coach: a deterministic solver plus statistics, a local LLM, and a trained model. For the local LLM, check inference speed on an AMD Radeon RX 6800 (16 GB VRAM, Windows, ROCm or Vulkan via llama.cpp or Ollama) while the game also uses the GPU.

## Comments

### 2026-10-04 — claude-code (resolution)

Findings: branch `research/decision-engine-prior-art`, file `research/decision-engine-prior-art.md`.

No trained decision model is needed for the MVP. Recommendation, at medium-high confidence: a deterministic engine built on rules, game maths and statistics. A local LLM is optional and only phrases and explains the engine's advice.

- **Reinforcement learning is out of reach.** Only Riot has shown a strong TFT agent, built on an in-house simulator. Open attempts such as TFTMuZeroAgent and TFT_GOAT never beat scripted bots.
- **Imitation learning has no data.** The Riot API records only final boards and placements, with no per-round actions.
- **LLMs are weak decision-makers on their own.** They do well only when wrapped around search or tools (PokéChamp, TFT-Copilot).
- **Existing coach apps** (MetaTFT, Blitz, Mobalytics, TFT Academy) use statistics plus expert curation. None uses a reinforcement-learning or LLM engine.
- **Local LLM on the RX 6800 works only through Vulkan.** ROCm on Windows does not support this card. A 7B 4-bit model runs at about 96 tokens per second with the GPU to itself. Estimates are 3–4 s per advice call for an 8B model and 6–7 s for 14B. That fits a roughly 30 s planning phase only with short outputs. CPU-only is too slow.
- **Possible later addition:** a small board-strength model trained on API final boards. It cannot advise on level or roll timing, and it inherits survival bias.
- **Where training is actually needed:** screen-capture recognition of champions, items and augments, if that capture route is chosen.

Open questions carried forward: frame-rate cost of llama.cpp beside the live game (see "Benchmark local LLM inference beside a live TFT game"), and how far hand-written rules get on transitions, pivots and positioning (evaluation harness).
