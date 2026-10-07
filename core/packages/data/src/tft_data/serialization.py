"""Validated disk round-trip for immutable data snapshots."""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from .config import validate_static
from .models import (
    DataError,
    DataSnapshot,
    Entity,
    Guide,
    SourceState,
    Statistic,
    TaggedValue,
)


def decode_tags(values):
    return {key: TaggedValue(**raw) for key, raw in values.items()}


def decode_entities(values):
    return {
        id: Entity(**{**raw, "values": decode_tags(raw["values"])})
        for id, raw in values.items()
    }


def load_snapshot(root, id):
    if not re.fullmatch(r"[0-9a-f]{64}", id):
        raise DataError("Invalid snapshot id")
    try:
        content = (Path(root) / id / "snapshot.json").read_bytes()
        if hashlib.sha256(content).hexdigest() != id:
            raise DataError("Snapshot content hash mismatch")
        raw = json.loads(content)
        static = decode_tags(raw["static"])
        validate_static(static)
        sources = {
            key: SourceState(
                **{
                    **value,
                    "updated_at": datetime.fromisoformat(value["updated_at"]),
                    "fetched_at": datetime.fromisoformat(value["fetched_at"]),
                }
            )
            for key, value in raw["sources"].items()
        }
        snapshot = DataSnapshot(
            id,
            raw["patch"],
            raw["set_number"],
            static,
            decode_tags(raw["tunables"]),
            decode_entities(raw["entities"]),
            tuple(Statistic(**row) for row in raw["statistics"]),
            {key: Guide(**value) for key, value in raw.get("guides", {}).items()},
            sources,
            tuple(raw.get("warnings", [])),
            tuple(raw["changed_ids"]),
            raw.get("lobby_top4_rate"),
            raw.get("positioning", {}),
            raw.get("augment_tiers", {}),
            raw.get("comp_augment_tiers", {}),
        )
        rows = {
            source: tuple(Statistic(**row) for row in values)
            for source, values in raw.get("source_rows", {}).items()
        }
        guides = {
            source: {id: Guide(**row) for id, row in values.items()}
            for source, values in raw.get("source_guides", {}).items()
        }
        return snapshot, rows, guides, raw.get("source_enrichment", {})
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise DataError(f"Cannot restore snapshot: {exc}") from None
