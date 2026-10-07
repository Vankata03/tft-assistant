"""Sources implement metadata checks separately from payload downloads."""

import json
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from .models import DataError, freeze


@dataclass(frozen=True)
class SourceMetadata:
    patch: str
    updated_at: datetime
    filters: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.patch or self.updated_at.tzinfo is None:
            raise DataError(
                "Source metadata requires patch and timezone-aware timestamp"
            )
        object.__setattr__(self, "filters", freeze(self.filters))


class Source(Protocol):
    name: str
    kind: str

    def metadata(self) -> SourceMetadata: ...
    def fetch(self) -> Any: ...


@dataclass
class MemorySource:
    """External-service fixture boundary, also useful for checked offline payloads."""

    name: str
    kind: str
    patch: str
    updated_at: datetime
    payload: Any

    def metadata(self):
        return SourceMetadata(self.patch, self.updated_at)

    def fetch(self):
        return self.payload


class HTTPSource:
    """Configured versioned endpoints with mandatory patch/update metadata.

    Undocumented endpoints must be explicitly configured and rechecked when their
    schema changes. Missing timestamps never become invented freshness.
    """

    def __init__(
        self,
        name,
        kind,
        url,
        metadata_url=None,
        *,
        headers=None,
        timeout=15,
        provider=None,
        query=None,
        expected_filters=None,
    ):
        from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

        self.provider = provider or name

        def queried(value):
            if not query:
                return value
            parts = urlsplit(value)
            return urlunsplit(
                (
                    parts.scheme,
                    parts.netloc,
                    parts.path,
                    urlencode({**dict(parse_qsl(parts.query)), **query}),
                    parts.fragment,
                )
            )

        url = queried(url)
        metadata_url = queried(metadata_url) if metadata_url else None
        self.expected_filters = expected_filters or {}
        self.name, self.kind, self.url = name, kind, url
        self.metadata_url = metadata_url or url
        self.headers = {
            "User-Agent": "TFTAssistant/0.1 (+personal TFT coach)",
            **(headers or {}),
        }
        self.timeout = timeout
        self._checked_payload = None

    def _get(self, url):
        if not url.startswith("https://"):
            raise DataError("Source URLs must use HTTPS")
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=self.headers), timeout=self.timeout
            ) as r:
                body = r.read(32 * 1024 * 1024 + 1)
            if len(body) > 32 * 1024 * 1024:
                raise DataError("Source response exceeds 32 MiB")
            return json.loads(body)
        except (OSError, ValueError) as exc:
            raise DataError(f"{self.name} unavailable: {type(exc).__name__}") from None

    def metadata(self):
        raw = self._get(self.metadata_url)
        if self.metadata_url == self.url:
            self._checked_payload = raw
        try:
            if self.provider == "metatft":
                patch = (
                    raw.get("patch")
                    or raw["region_patch_adjustment"]["global_patch"]["patch"]
                )
                updated = datetime.fromtimestamp(raw["updated"] / 1000, timezone.utc)
            else:
                patch = raw["patch"]
                updated = datetime.fromisoformat(
                    raw["updated_at"].replace("Z", "+00:00")
                )
            if updated.tzinfo is None:
                raise ValueError("timestamp needs timezone")
            filters = raw.get("filters", raw.get("aperture", {}))
            for key, value in self.expected_filters.items():
                if filters.get(key) != value:
                    raise DataError(
                        f"{self.name} did not confirm requested filter {key}={value}"
                    )
            return SourceMetadata(str(patch), updated, filters)
        except (KeyError, ValueError, TypeError) as exc:
            raise DataError(
                f"{self.name} missing patch/update metadata: {exc}"
            ) from None

    def fetch(self):
        if self._checked_payload is not None:
            payload = self._checked_payload
            self._checked_payload = None
            return payload
        return self._get(self.url)


def embedded_academy(html):
    """Read the inert Svelte data literal; never execute website JavaScript."""
    import re

    import json5

    try:
        patch = re.search(r'data:\{patch:"([^"\n]+)"', html)[1]
        stamp = re.search(r'lastUpdated:"([^"\n]+)"', html)[1]
        start = html.index("guides:[") + len("guides:")
        depth = 0
        quote = None
        escaped = False
        end = None
        for index in range(start, len(html)):
            char = html[index]
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                continue
            if char in ('"', "'"):
                quote = char
            elif char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end is None:
            raise DataError("TFT Academy Guide literal is truncated")
        return {
            "patch": patch,
            "updated_at": stamp,
            "guides": json5.loads(html[start:end]),
        }
    except (TypeError, ValueError, IndexError) as exc:
        raise DataError(f"TFT Academy embedded schema changed: {exc}") from None


class AcademySource(HTTPSource):
    def __init__(self, url="https://tftacademy.com/tierlist/comps", **kwargs):
        super().__init__("tftacademy", "guides", url, **kwargs)

    def _get(self, url):
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=self.headers), timeout=self.timeout
            ) as r:
                html = r.read(32 * 1024 * 1024 + 1).decode()
            if len(html) > 32 * 1024 * 1024:
                raise DataError("TFT Academy response exceeds 32 MiB")
            return embedded_academy(html)
        except (OSError, ValueError) as exc:
            raise DataError(f"TFT Academy unavailable: {type(exc).__name__}") from None


class TacticsSource(HTTPSource):
    """Checked /units page exposes update time and aggregate unit/trait/item rows."""

    def __init__(self, url="https://tactics.tools/units", **kwargs):
        super().__init__("tactics.tools", "statistics", url, **kwargs)

    def _get(self, url):
        import html
        import re

        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=self.headers), timeout=self.timeout
            ) as response:
                page = response.read(32 * 1024 * 1024 + 1).decode()
            if len(page) > 32 * 1024 * 1024:
                raise DataError("tactics.tools response exceeds 32 MiB")
            match = re.search(
                r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.DOTALL
            )
            raw = json.loads(match[1])
            data = raw["props"]["pageProps"]["statsData"]
            title = html.unescape(
                re.search(r"<title>(.*?)</title>", page, re.DOTALL)[1]
            )
            patch = re.search(r"Patch\s+([0-9]+\.[0-9]+[a-z]?)", title)[1]
            return {
                "patch": patch,
                "updated_at": datetime.fromtimestamp(
                    data["lastUpdated"], timezone.utc
                ).isoformat(),
                "statsData": data,
                "aperture": raw["props"]["pageProps"]["aperture"],
            }
        except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
            raise DataError(
                f"tactics.tools unavailable or schema changed: {type(exc).__name__}"
            ) from None
