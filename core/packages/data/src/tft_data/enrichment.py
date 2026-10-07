"""Curated tiers and cell histograms are not placement statistics."""

import math
from collections.abc import Mapping

from .models import DataError, freeze


def enrichment(raw):
    tiers = dict(raw.get("global_augment_tiers", {}))
    if "content" in raw:
        try:
            for tier in raw["content"]["content"]["tierList"]:
                for entry in tier["content"]:
                    if entry["type"] == "augment":
                        tiers[entry["id"]] = tier["label"]
        except (KeyError, TypeError) as exc:
            raise DataError(f"Curated augment tier schema changed: {exc}") from None
    comp_tiers = raw.get("comp_augment_tiers", {})
    if any(tier not in {"S", "A", "B", "C", "D", "Guide"} for tier in tiers.values()):
        raise DataError("Unknown curated augment tier")
    if not isinstance(comp_tiers, Mapping) or any(
        not isinstance(rows, Mapping)
        or any(tier not in {"S", "A", "B", "C", "D", "Guide"} for tier in rows.values())
        for rows in comp_tiers.values()
    ):
        raise DataError("Invalid per-comp augment tiers")
    positions = {}
    for id, values in raw.get("positioning", {}).items():
        if isinstance(values, Mapping):
            values = [values.get(str(i), 0) for i in range(28)]
        if (
            not isinstance(values, (tuple, list))
            or len(values) != 28
            or any(
                isinstance(v, bool)
                or not isinstance(v, (int, float))
                or not math.isfinite(v)
                or v < 0
                for v in values
            )
        ):
            raise DataError(f"Invalid positioning histogram for {id}")
        positions[id] = tuple(values)
    if not any(
        key in raw
        for key in (
            "content",
            "global_augment_tiers",
            "comp_augment_tiers",
            "positioning",
        )
    ):
        raise DataError("Enrichment schema has no recognized tables")
    return freeze(
        {
            "augment_tiers": tiers,
            "comp_augment_tiers": comp_tiers,
            "positioning": positions,
        }
    )
