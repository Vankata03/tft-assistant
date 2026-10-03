---
id: 7
title: "Prior art for TFT decision engines and the train-vs-LLM question"
labels: [wayfinder:research]
status: open
assignee:
parent: 1
blocked_by: []
---

## Question

Do we need to train a model, and if so what kind? Survey prior art: academic and open-source work on TFT agents (reinforcement learning, imitation learning, search), LLM-based TFT assistants, and the recommendation features of existing coach apps. For each, report the method, the data it needed, how well it played, and whether code or data are public. Then assess three engine options for this coach: a deterministic solver plus statistics, a local LLM, and a trained model. For the local LLM, check inference speed on an AMD Radeon RX 6800 (16 GB VRAM, Windows, ROCm or Vulkan via llama.cpp or Ollama) while the game also uses the GPU.
