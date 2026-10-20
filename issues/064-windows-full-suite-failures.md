---
id: 64
title: Full Python suite failures on Windows
labels: [implementation:task, bug]
status: open
assignee:
parent: 34
blocked_by: []
---

# Full Python suite failures on Windows

## Run

`cd core; uv run pytest -q -rfE` on Windows 11 at `implement/mvp` `678bed7`, with ticket 63's uncommitted `test_outcomes.py` changes in the working tree: 5 failed, 1098 passed, 23 skipped in 43 minutes. The owner was not playing during most of the run, but other agent sessions shared the machine.

## Failures and status

- `test_harness_tunables_io.py::test_reference_separates_file_commit_blob_and_code_and_preserves_public_tags`, `test_harness_cli.py::test_eval_cli_reads_committed_tunables_and_writes_private_aggregate_report` and `test_harness_fit.py::test_functional_family1_fit_optimizes_training_log_loss_and_freezes_holdout`: `latest_committed_tunables` compared `str(Path(path))`, which uses backslashes on Windows, with `data/<patch>/tunables.toml`, so an explicit path never matched and it raised "No committed patch tunables at HEAD". Fixed in `0ac6f60` with `as_posix()`. All three pass on rerun.
- `test_storage_processes.py::test_default_locations_resolve_operator_paths_without_opening_a_store`: `SessionStore.default_locations` called `Path.home()` even when both override variables were set. The test's child environment has no `USERPROFILE`, so Windows raised "Could not determine home directory." Fixed by resolving home only when a default location is needed.
- `test_review_attribution.py::test_shop_bundle_display_must_precede_first_purchase_to_attribute_following[2-0.3-True-True]` and `packages/engine/tests/test_engine.py::test_exact_inference_handles_many_trait_identical_candidates_within_bounded_cpu_time`: both passed when rerun alone. They look timing-sensitive under machine load. Not diagnosed.
- `test_outcomes.py`: the five Windows failures are ticket 63; they passed in this run with its changes.

## Acceptance

- A full Windows run without `-x` passes, or each remaining failure has its own diagnosed ticket.
- The two load-sensitive tests are either shown to be stable on an idle machine or given budgets that state the Windows cost they cover.
