"""Owner-confirmed EUNE patch boundaries; nearby API matches are uncertain."""

import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .models import DataError


@dataclass(frozen=True)
class PatchAssignment:
    patch: str | None
    uncertain: bool


@dataclass(frozen=True)
class PatchCalendar:
    boundaries: tuple[tuple[str, datetime], ...]

    @classmethod
    def load(cls, path):
        try:
            rows = tomllib.loads(Path(path).read_text()).get("patches", {})
            parsed = []
            for patch, date in rows.items():
                when = datetime.fromisoformat(date) if isinstance(date, str) else date
                if when.tzinfo is None:
                    raise DataError("Patch boundary must carry EUNE timezone offset")
                parsed.append((patch, when))
            if len({time for _, time in parsed}) != len(parsed):
                raise DataError("Patch boundaries must be unique")
            return cls(tuple(sorted(parsed, key=lambda p: p[1])))
        except (OSError, ValueError, TypeError) as exc:
            raise DataError(f"Invalid patch calendar: {exc}") from None

    def at(self, when):
        if isinstance(when, (int, float)):
            when = datetime.fromtimestamp(when / 1000 if when > 10**11 else when, UTC)
        if when.tzinfo is None:
            raise DataError("Match time must be timezone-aware")
        patch = None
        for label, boundary in self.boundaries:
            if boundary <= when:
                patch = label
        uncertain = patch is None or any(
            abs(when - boundary) <= timedelta(days=1) for _, boundary in self.boundaries
        )
        return PatchAssignment(patch, uncertain)
