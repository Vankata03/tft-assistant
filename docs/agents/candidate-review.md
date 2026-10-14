# First-patch candidate review

`tft-data prepare-review` prepares offline review inputs from explicit cached CommunityDragon and Data Dragon files. It does not fetch providers, publish a production patch, write an immutable snapshot or change the patch calendar. The destination is required and must not already exist.

Run from `core/`, substituting the paths of the checked files:

```sh
uv run tft-data prepare-review 18.4b --set 18 \
  --review-dir /absolute/path/to/isolated-review \
  --cdragon-file /absolute/path/to/cdragon.json \
  --ddragon-file /absolute/path/to/ddragon-bundle.json \
  --entity-overlay-file /absolute/path/to/reviewed-entity-overlay.json
```

The optional overlay uses the existing [capacity metadata contract](capacity-contracts.md#reviewed-entity-input). It changes tagged values on existing canonical IDs and preserves their citations and before/after diff. It cannot add aliases or change identity fields. Missing slot certificates remain unavailable; a supplied malformed certificate fails before the review directory is published. A declaration is a review input, not an independently qualified game rule.

The output contains the canonical catalog, recipes, item and Wisp coverage, per-unit slot coverage, required static/tunable templates, consumer dependencies and a patch diff. Unknown values stay null in JSON; the command emits no static or tunables TOML. The manifest hashes every input and output, the shared Data consumers and available repository contract files. Missing packaged contract files have null hashes. Repeat into a second explicit destination and compare complete bytes to check deterministic preparation.

Reconcile the [decision](decision-contracts.md), [capacity](capacity-contracts.md), [capture](capture-boundary.md) and [Engine](engine-contracts.md) contracts before materializing a patch. The required configuration currently has 25 static fields and 59 Set-18 tunables. Source rules, declared heuristics, carried values, fitted parameters and observed completeness are separate evidence. Guide targets cannot resolve captured variable unit forms; partial rosters or inventory cannot certify missing entities. A schedule date and patch-note publication time cannot supply an exact EUNE deployment instant.

Once complete reviewed static and tunable files exist, `bootstrap` accepts the same optional entity overlay and validates before publishing its isolated patch directory. Validation must use an explicit isolated `--snapshots` destination. A refresh also needs explicit isolated source/override paths; `--offline` prevents provider fetches. Never let a candidate review use the default owner configuration directory. The positive bootstrap/new-set tests use declared synthetic certificates and qualify the software path only. Actual patch readiness, sources, fits, HUD counters and deployment times remain ticket 48/49 requirements.
