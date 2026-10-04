"""The Engine functions Baseline features may call during a game.

Baseline features import this module and nothing else from the Engine; an
import-linter contract in core/pyproject.toml enforces it. The allowlist is
own-board board power, `win_probability` and the opponent growth curve lookup
(docs/spec/engine.md, "Mode separation"). Build stage 5 fills it in.
"""
