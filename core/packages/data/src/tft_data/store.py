"""Atomically publish content-addressed snapshots; games retain their object."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from .adapters import guides, merge_entities, statistics
from .computed import default_lines
from .config import load_patch
from .enrichment import enrichment
from .models import (
    DataError,
    DataSnapshot,
    RefreshResult,
    SourceState,
    TaggedValue,
    plain,
)
from .overrides import apply_overrides
from .serialization import load_snapshot
from .threats import derive_threats


class DataStore:
    def __init__(self, root):
        self.root = Path(root)
        self.current = None
        self.last_good_at = None
        self._source_rows = {}
        self._source_guides = {}
        self._source_enrichment = {}
        self._pending = None
        self.restore_warning = None
        pointer = self.root / "current.json"
        if pointer.exists():
            try:
                saved = json.loads(pointer.read_text())
                (
                    self.current,
                    self._source_rows,
                    self._source_guides,
                    self._source_enrichment,
                ) = load_snapshot(self.root, saved["snapshot_id"])
                self.last_good_at = datetime.fromisoformat(saved["last_good_at"])
            except (DataError, OSError, ValueError, KeyError) as exc:
                self.restore_warning = f"Last-good snapshot unavailable: {exc}"

    def get(self, snapshot_id):
        """Read the exact data a recorded game used, without changing current."""
        return load_snapshot(self.root, snapshot_id)[0]

    def refresh(
        self,
        patch_dir,
        *,
        now=None,
        in_game=False,
        trigger="startup",
        entity_adapters=(),
        sources=(),
        fallback=None,
        overrides=None,
        computations=None,
        can_publish=None,
        defer_publication=False,
    ):
        now = now or datetime.now(UTC)
        if (
            in_game
            or (can_publish is not None and not can_publish())
            or trigger not in {"startup", "Lobby", "end-of-game"}
        ):
            return RefreshResult(self.current, deferred=True)
        try:
            patch, set_number, static, tunables, entities, changed_ids = load_patch(
                patch_dir
            )
            adapter_warnings = []
            for adapter in entity_adapters:
                entities = merge_entities(entities, adapter.entities())
                adapter_warnings.extend(getattr(adapter, "warnings", ()))
            for e in entities.values():
                if e.kind == "wisp" and e.id not in static["wisps"].value:
                    raise DataError(f"New Wisp {e.id} needs a static effect entry")
            keywords = static["threat_keywords"].value
            entities = derive_threats(entities, keywords)
            warnings = [
                f"Low confidence: {name} uses {v.source}"
                for name, v in static.items()
                if v.source in {"default", "carried"}
            ]
            warnings.extend(adapter_warnings)
            states = dict(self.current.sources) if self.current else {}
            source_rows = dict(self._source_rows)
            source_guides = dict(self._source_guides)
            source_enrichment = dict(self._source_enrichment)
            failed_sources = set()
            for source in sources:
                try:
                    metadata = source.metadata()
                    old = states.get(source.name)
                    age = (
                        3600
                        if source.kind in {"statistics", "enrichment"}
                        else 21600
                        if source.kind == "guides"
                        else 0
                    )
                    changed = (
                        old is None
                        or metadata.patch != old.patch
                        or metadata.updated_at > old.updated_at
                    )
                    if (
                        not changed
                        or old
                        and (now - old.fetched_at).total_seconds() < age
                    ):
                        continue
                    if source.kind == "static" and old and metadata.patch == old.patch:
                        continue
                    raw = source.fetch()
                    if source.kind == "statistics":
                        parsed = statistics(
                            raw,
                            getattr(source, "provider", source.name),
                            metadata.patch,
                            entities,
                        )
                        source_rows[source.name] = parsed
                    elif source.kind == "guides":
                        source_guides[source.name] = guides(raw, entities)
                    elif source.kind == "enrichment":
                        source_enrichment[source.name] = enrichment(raw)
                    else:
                        raise DataError(f"Unsupported source kind: {source.kind}")
                    states[source.name] = SourceState(
                        source.name,
                        metadata.patch,
                        metadata.updated_at,
                        now,
                        source.kind,
                        metadata.filters,
                    )
                except (DataError, OSError, ValueError, TypeError) as exc:
                    since = (
                        states[source.name].fetched_at.isoformat()
                        if source.name in states
                        else "unavailable"
                    )
                    warnings.append(f"{source.name} data stale since {since}: {exc}")
                    failed_sources.add(source.name)
                    if source.kind == "statistics" and fallback:
                        try:
                            metadata = fallback.metadata()
                            source_rows[source.name] = statistics(
                                fallback.fetch(),
                                getattr(fallback, "provider", fallback.name),
                                metadata.patch,
                                entities,
                            )
                            failed_sources.discard(source.name)
                            states[fallback.name] = SourceState(
                                fallback.name,
                                metadata.patch,
                                metadata.updated_at,
                                now,
                                "statistics",
                                metadata.filters,
                            )
                        except (
                            DataError,
                            OSError,
                            ValueError,
                            TypeError,
                        ) as fallback_error:
                            warnings.append(
                                f"{fallback.name} fallback unavailable: {fallback_error}"
                            )
            rows = []
            previous = (
                {
                    (
                        r.kind,
                        r.entity_id,
                        r.unit_star,
                        r.item_id,
                        r.comp_id,
                        r.breakpoint,
                        r.source,
                    ): r
                    for r in self.current.statistics
                }
                if self.current
                else {}
            )
            seen = set()
            for source_name, candidates in source_rows.items():
                for row in candidates:
                    key = (
                        row.kind,
                        row.entity_id,
                        row.unit_star,
                        row.item_id,
                        row.comp_id,
                        row.breakpoint,
                        row.source,
                    )
                    if key in seen:
                        continue
                    if row.patch == patch and row.sample_count < 500:
                        old = previous.get(key)
                        if old:
                            row = replace(
                                old, stale=True, changed=row.entity_id in changed_ids
                            )
                        else:
                            # Thin new-patch samples do not invent a previous-patch prior.
                            continue
                    seen.add(key)
                    rows.append(
                        replace(
                            row,
                            stale=row.stale
                            or row.patch != patch
                            or source_name in failed_sources,
                            changed=row.entity_id in changed_ids,
                        )
                    )
            guide_rows = {
                id: g for data in source_guides.values() for id, g in data.items()
            }
            positions = {
                id: value
                for extra in source_enrichment.values()
                for id, value in extra["positioning"].items()
            }
            tiers = {
                id: value
                for extra in source_enrichment.values()
                for id, value in extra["augment_tiers"].items()
            }
            comp_tiers = {
                id: value
                for extra in source_enrichment.values()
                for id, value in extra["comp_augment_tiers"].items()
            }
            for id, guide in list(guide_rows.items()):
                if id in comp_tiers:
                    guide_rows[id] = replace(
                        guide, augment_tiers={**guide.augment_tiers, **comp_tiers[id]}
                    )
            entities, guide_rows, tunables, override_warnings = apply_overrides(
                overrides, patch, entities, guide_rows, tunables, changed_ids
            )
            warnings.extend(override_warnings)
            if tunables["default_lines_by_carry_cost"].source != "owner":
                tunables["default_lines_by_carry_cost"] = default_lines(
                    guide_rows, entities
                )
            for name, compute in (computations or {}).items():
                if name not in {"opponent_growth_curve", "default_lines_by_carry_cost"}:
                    raise DataError(f"Unknown computed tunable: {name}")
                if tunables[name].source == "owner":
                    continue
                provisional = DataSnapshot(
                    "pending",
                    patch,
                    set_number,
                    static,
                    tunables,
                    entities,
                    tuple(rows),
                    guide_rows,
                    states,
                    tuple(warnings),
                    changed_ids,
                    static["lobby_top4_rate"].value,
                )
                try:
                    value = compute(provisional)
                    tunables[name] = (
                        value
                        if isinstance(value, TaggedValue)
                        else TaggedValue(
                            value,
                            tunables[name].source,
                            citation="Recomputed from this refresh by the Engine.",
                            family="computed",
                        )
                    )
                except (DataError, ValueError, TypeError, KeyError) as exc:
                    warnings.append(
                        f"Computed {name} unavailable; last supplied table retained: {exc}"
                    )
            payload = {
                "warnings": warnings,
                "source_enrichment": source_enrichment,
                "positioning": positions,
                "augment_tiers": tiers,
                "comp_augment_tiers": comp_tiers,
                "source_rows": {
                    source: [vars(row) for row in values]
                    for source, values in source_rows.items()
                },
                "source_guides": {
                    source: {id: vars(row) for id, row in values.items()}
                    for source, values in source_guides.items()
                },
                "lobby_top4_rate": static["lobby_top4_rate"].value,
                "patch": patch,
                "set_number": set_number,
                "static": {k: vars(v) for k, v in static.items()},
                "tunables": {k: vars(v) for k, v in tunables.items()},
                "entities": {k: vars(v) for k, v in entities.items()},
                "changed_ids": changed_ids,
                "statistics": [vars(r) for r in rows],
                "guides": {id: vars(g) for id, g in guide_rows.items()},
                "sources": {k: vars(v) for k, v in states.items()},
            }
            content = json.dumps(
                plain(payload),
                sort_keys=True,
                default=lambda o: (
                    o.isoformat() if isinstance(o, datetime) else plain(vars(o))
                ),
            ).encode()
            id = hashlib.sha256(content).hexdigest()
            if self.current and self.current.snapshot_id == id:
                return RefreshResult(self.current, warnings=tuple(warnings))
            candidate = DataSnapshot(
                id,
                patch,
                set_number,
                static,
                tunables,
                entities,
                tuple(rows),
                guides=guide_rows,
                sources=states,
                warnings=tuple(warnings),
                changed_ids=changed_ids,
                lobby_top4_rate=static["lobby_top4_rate"].value,
                positioning=positions,
                augment_tiers=tiers,
                comp_augment_tiers=comp_tiers,
            )
            pending = (
                candidate,
                content,
                source_rows,
                source_guides,
                source_enrichment,
                now,
            )
            if defer_publication or (can_publish is not None and not can_publish()):
                self._pending = pending
                return RefreshResult(
                    self.current, warnings=tuple(warnings), deferred=True
                )
            return self._publish(pending)
        except (DataError, OSError, TypeError, ValueError) as exc:
            since = (
                self.last_good_at.isoformat() if self.last_good_at else "unavailable"
            )
            return RefreshResult(
                self.current,
                warnings=tuple(
                    filter(
                        None, (self.restore_warning, f"Data stale since {since}: {exc}")
                    )
                ),
                error=str(exc),
            )

    def publish_pending(self, *, in_game=False):
        """Publish a completed background refresh at the next allowed boundary."""
        if in_game:
            return RefreshResult(self.current, deferred=True)
        if self._pending is None:
            return RefreshResult(self.current)
        pending = self._pending
        self._pending = None
        return self._publish(pending)

    def _publish(self, pending):
        snapshot, content, source_rows, source_guides, source_enrichment, now = pending
        self.root.mkdir(parents=True, exist_ok=True)
        destination = self.root / snapshot.snapshot_id
        if not destination.exists():
            with tempfile.TemporaryDirectory(dir=self.root) as temp:
                folder = Path(temp) / snapshot.snapshot_id
                folder.mkdir()
                (folder / "snapshot.json").write_bytes(content)
                os.replace(folder, destination)
        with tempfile.NamedTemporaryFile(
            mode="w", dir=self.root, delete=False
        ) as pointer_file:
            json.dump(
                {"snapshot_id": snapshot.snapshot_id, "last_good_at": now.isoformat()},
                pointer_file,
            )
            temporary_pointer = pointer_file.name
        try:
            os.replace(temporary_pointer, self.root / "current.json")
        finally:
            Path(temporary_pointer).unlink(missing_ok=True)
        self.current = snapshot
        self._source_rows = source_rows
        self._source_guides = source_guides
        self._source_enrichment = source_enrichment
        self.last_good_at = now
        return RefreshResult(snapshot, True, snapshot.warnings)
