"""Configurable external source routes; unsupported cohorts fail visibly."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .models import DataError
from .sources import AcademySource, HTTPSource, TacticsSource


@dataclass(frozen=True)
class SourceConfiguration:
    sources: tuple
    fallback: object | None
    minimum_rank: str
    regions: str

    @classmethod
    def load(cls, path):
        try:
            raw = tomllib.loads(Path(path).read_text())
            if raw.get("schema_version") != 1:
                raise DataError("Unknown source configuration version")
            sources = []
            lookup = {}
            for name, row in raw["sources"].items():
                provider = row["provider"]
                kind = row["kind"]
                kwargs = {
                    "timeout": row.get("timeout", 15),
                    "query": row.get("query"),
                    "expected_filters": row.get("expected_filters"),
                }
                if provider == "tftacademy":
                    source = AcademySource(row["url"], **kwargs)
                elif provider == "tactics.tools":
                    source = TacticsSource(row["url"], **kwargs)
                else:
                    source = HTTPSource(
                        name,
                        kind,
                        row["url"],
                        row.get("metadata_url"),
                        provider=provider,
                        **kwargs,
                    )
                source.name = name
                source.kind = kind
                lookup[name] = source
            for name in raw["refresh"]["sources"]:
                sources.append(lookup[name])
            fallback = lookup.get(raw["refresh"].get("fallback"))
            cohort = raw["statistics"]
            return cls(
                tuple(sources), fallback, cohort["minimum_rank"], cohort["regions"]
            )
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise DataError(f"Invalid source configuration: {exc}") from None
