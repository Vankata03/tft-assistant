"""Rate-limited Riot client, scoped to the authenticated owner's own matches."""

from __future__ import annotations

import json
import time
from math import isfinite
import re
import secrets
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .models import DataError


@dataclass(frozen=True)
class HTTPResponse:
    status: int
    headers: dict[str, str]
    body: object


def http_transport(url, headers):
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=20) as response:
            body = response.read(16 * 1024 * 1024 + 1)
            if len(body) > 16 * 1024 * 1024:
                raise DataError("Riot response exceeds 16 MiB")
            return HTTPResponse(
                response.status, dict(response.headers), json.loads(body)
            )
    except HTTPError as exc:
        # An API error body is never surfaced: it may include account identifiers.
        return HTTPResponse(exc.code, dict(exc.headers), None)
    except OSError, ValueError:
        raise DataError(
            "Riot API unavailable; check connectivity and local key status"
        ) from None


class RiotClient:
    def __init__(
        self,
        *,
        key_path=None,
        region="europe",
        platform="eun1",
        transport=http_transport,
        clock=time.monotonic,
        sleep=time.sleep,
        pacing_path=None,
    ):
        self.key_path = Path(
            key_path or Path.home() / ".config/tft-assistant/riot-api-key"
        )
        self.region, self.platform = region, platform
        if region not in {"americas", "asia", "europe", "sea"} or platform not in {
            "br1",
            "eun1",
            "euw1",
            "jp1",
            "kr",
            "la1",
            "la2",
            "na1",
            "oc1",
            "tr1",
            "ru",
            "ph2",
            "sg2",
            "th2",
            "tw2",
            "vn2",
        }:
            raise DataError("Invalid Riot routing value")
        self.transport, self.clock, self.sleep = transport, clock, sleep
        self._history = defaultdict(deque)
        self._limits = defaultdict(lambda: ((20, 1), (100, 120)))
        self._method_history = defaultdict(deque)
        self._method_limits = {}
        self._cooldowns = {}
        self._allowed_matches = set()
        self.owner_puuid = None
        # A caller using this checkpoint must serialize the entire API operation
        # across processes. Outcome collection holds its own OS mutex for that.
        self.pacing_path = Path(pacing_path) if pacing_path is not None else None
        self._restore_pacing()

    def _restore_pacing(self):
        if self.pacing_path is None or not self.pacing_path.exists():
            return
        try:
            raw = self.pacing_path.read_bytes()
            if len(raw) > 262144:
                raise ValueError()
            state = json.loads(raw)
            saved, now = state['saved_at'], self.clock()
            if (type(state['schema_version']) is not int or state['schema_version'] != 1 or type(saved) not in (int, float)
                or not isfinite(saved) or saved < 0 or not isfinite(now) or now < 0):
                raise ValueError()
            cooldowns = state.get('cooldowns', {})
            if (not isinstance(cooldowns, dict) or len(cooldowns) > 128
                or any(not isinstance(route, str) or not re.fullmatch('[a-z0-9]+', route)
                    or type(deadline) not in (int, float) or not isfinite(deadline) or deadline < saved
                    for route, deadline in cooldowns.items())):
                raise ValueError()
            self._cooldowns = {route: deadline if now >= saved else now + (deadline - saved)
                for route, deadline in cooldowns.items()}
            rows = state['rows']
            if not isinstance(rows, list) or len(rows) > 128:
                raise ValueError()
            seen = set()
            for row in rows:
                routing, method = row['routing'], row['method']
                if (not isinstance(routing, str) or not re.fullmatch('[a-z0-9]+', routing)
                    or (method is not None and (not isinstance(method, str) or not re.fullmatch('[a-z-]+', method)))):
                    raise ValueError()
                identity = (routing, method)
                if identity in seen:
                    raise ValueError()
                seen.add(identity)
                limits, history = row['limits'], row['history']
                if limits is not None:
                    if (not isinstance(limits, list) or not limits or len(limits) > 64
                        or any(not isinstance(pair, list) or len(pair) != 2
                            or type(pair[0]) is not int or pair[0] <= 0
                            or type(pair[1]) not in (int, float) or not isfinite(pair[1]) or pair[1] <= 0
                            for pair in limits)):
                        raise ValueError()
                elif method is None:
                    raise ValueError()
                if (not isinstance(history, list) or len(history) > 10000
                    or any(type(stamp) not in (int, float) or not isfinite(stamp)
                           or stamp < 0 or stamp > saved for stamp in history)
                    or history != sorted(history)):
                    raise ValueError()
                # A reboot/clock rollback gives no trustworthy elapsed time.
                # Retain requests as current against the saved server windows.
                history = deque(history if now >= saved else [now] * len(history))
                if method is None:
                    self._limits[routing] = tuple(map(tuple, limits))
                    self._history[routing] = history
                else:
                    if limits is not None:
                        self._method_limits[identity] = tuple(map(tuple, limits))
                    self._method_history[identity] = history
        except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
            raise DataError('Riot pacing checkpoint invalid; preserve it and review before retrying') from None

    def _save_pacing(self):
        if self.pacing_path is None:
            return
        now, rows = self.clock(), []
        for routing, history in self._history.items():
            limits = self._limits[routing]
            window = max(seconds for _, seconds in limits)
            rows.append({'routing': routing, 'method': None, 'limits': limits,
                'history': [stamp for stamp in history if now - stamp < window]})
        for (routing, method), history in self._method_history.items():
            limits = self._method_limits.get((routing, method))
            window = max(seconds for _, seconds in (limits or self._limits[routing]))
            rows.append({'routing': routing, 'method': method, 'limits': limits,
                'history': [stamp for stamp in history if now - stamp < window]})
        raw = json.dumps({'schema_version': 1, 'saved_at': now, 'rows': rows,
            'cooldowns': {route: deadline for route, deadline in self._cooldowns.items() if deadline > now}}, allow_nan=False)
        if len(raw.encode()) > 262144:
            raise DataError('Riot pacing checkpoint exceeds its byte budget')
        self.pacing_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.pacing_path.with_name(self.pacing_path.name + '.' + secrets.token_hex(8) + '.tmp')
        try:
            temporary.write_text(raw)
            temporary.replace(self.pacing_path)
        finally:
            temporary.unlink(missing_ok=True)

    def _pace(self, routing, method):
        now = self.clock()
        histories = [(self._history[routing], self._limits[routing])]
        if (routing, method) in self._method_limits:
            histories.append(
                (
                    self._method_history[(routing, method)],
                    self._method_limits[(routing, method)],
                )
            )
        delay = max(0.0, self._cooldowns.get(routing, 0) - now)
        for history, limits in histories:
            longest = max(window for _, window in limits)
            while history and now - history[0] >= longest:
                history.popleft()
            for count, window in limits:
                recent = [stamp for stamp in history if now - stamp < window]
                if len(recent) >= count:
                    delay = max(delay, recent[-count] + window - now)
        if delay > 0:
            self.sleep(delay + 0.01)
        timestamp = self.clock()
        self._history[routing].append(timestamp)
        self._method_history[(routing, method)].append(timestamp)
        # Persist the dispatched request before HTTP: termination during a call
        # must not make a replacement child forget that request.
        self._save_pacing()

    def _request(self, routing, path, method):
        self._restore_pacing()
        try:
            key = self.key_path.read_text().strip()
        except OSError:
            raise DataError(
                "Riot key unavailable; place the key in the configured local key file"
            ) from None
        if not key or "\n" in key or "\r" in key:
            raise DataError("Riot key file must contain exactly one nonempty line")
        headers = {
            "X-Riot-Token": key,
            "User-Agent": "TFTAssistant/0.1 (+personal owner match review)",
        }
        for attempt in range(3):
            self._pace(routing, method)
            response = self.transport(
                f"https://{routing}.api.riotgames.com{path}", headers
            )
            response_headers = {k.lower(): v for k, v in response.headers.items()}
            for header, destination in [
                ("x-app-rate-limit", None),
                ("x-method-rate-limit", method),
            ]:
                if header not in response_headers:
                    continue
                try:
                    limits = tuple(
                        (int(a), float(b))
                        for a, b in (
                            part.split(":")
                            for part in response_headers[header].split(",")
                        )
                    )
                    if not limits or any(
                        count <= 0 or not isfinite(window) or window <= 0 for count, window in limits
                    ):
                        raise ValueError()
                    if destination is None:
                        self._limits[routing] = limits
                    else:
                        self._method_limits[(routing, method)] = limits
                except ValueError:
                    raise DataError(
                        "Riot returned malformed rate-limit headers"
                    ) from None
            self._save_pacing()
            if response.status == 200:
                return response.body
            if response.status == 429:
                try:
                    delay = float(response_headers.get("retry-after", "1.25"))
                    if not isfinite(delay):
                        raise ValueError()
                except ValueError:
                    delay = 1.25
                delay = max(delay, 0)
                self._cooldowns[routing] = max(self._cooldowns.get(routing, 0), self.clock() + delay)
                # Preserve server cooldown before a cancellable wait, including
                # the final failed attempt and replacement collection children.
                self._save_pacing()
                if attempt < 2:
                    self.sleep(delay)
                    continue
            if response.status in {502, 503, 504} and attempt < 2:
                self.sleep(1.25 * (attempt + 1))
                continue
            if response.status in {401, 403}:
                raise DataError(
                    "Riot authentication failed; refresh the local API key or check approval"
                )
            raise DataError(
                f"Riot API HTTP {response.status}; previous owner data remains available"
            )
        raise DataError("Riot API retries exhausted")

    def account(self, game_name, tag_line):
        raw = self._request(
            self.region,
            f"/riot/account/v1/accounts/by-riot-id/{quote(game_name, safe='')}/{quote(tag_line, safe='')}",
            "account",
        )
        if not isinstance(raw, dict) or not isinstance(raw.get("puuid"), str):
            raise DataError("Riot account schema changed")
        self.owner_puuid = raw["puuid"]
        return raw

    def rank(self):
        self._owner()
        raw = self._request(
            self.platform,
            f"/tft/league/v1/entries/by-puuid/{quote(self.owner_puuid, safe='')}",
            "league",
        )
        if not isinstance(raw, list) or any(
            not isinstance(row, dict)
            or not {"queueType", "tier", "rank", "leaguePoints"} <= row.keys()
            for row in raw
        ):
            raise DataError("Riot rank schema changed")
        return raw

    def summoner(self):
        self._owner()
        raw = self._request(
            self.platform,
            f"/tft/summoner/v1/summoners/by-puuid/{quote(self.owner_puuid, safe='')}",
            "summoner",
        )
        if not isinstance(raw, dict) or raw.get("puuid") != self.owner_puuid:
            raise DataError("Riot summoner schema changed")
        return raw

    def _owner(self):
        if not self.owner_puuid:
            raise DataError("Resolve the owner Riot ID before requesting match data")

    def match_ids(self, *, start=0, count=100):
        self._owner()
        if not isinstance(start, int) or start < 0 or not 1 <= count <= 100:
            raise DataError("Match ids require start >=0 and count in [1,100]")
        query = urlencode({"start": start, "count": count})
        raw = self._request(
            self.region,
            f"/tft/match/v1/matches/by-puuid/{quote(self.owner_puuid, safe='')}/ids?{query}",
            "match-ids",
        )
        if not isinstance(raw, list) or any(not isinstance(id, str) for id in raw):
            raise DataError("Riot match-id schema changed")
        self._allowed_matches.update(raw)
        return tuple(raw)

    def match(self, match_id):
        self._owner()
        if match_id not in self._allowed_matches:
            raise DataError("Only matches returned for the owner may be fetched")
        raw = self._request(
            self.region, f"/tft/match/v1/matches/{quote(match_id, safe='')}", "match"
        )
        try:
            info = raw["info"]
            participants = info["participants"]
            own = [row for row in participants if row["puuid"] == self.owner_puuid]
            if len(own) != 1 or not 1 <= own[0]["placement"] <= 8:
                raise ValueError()
            for field in ("queue_id", "tft_set_number", "game_datetime"):
                if not isinstance(info[field], int):
                    raise TypeError()
            if any("units" not in row or "traits" not in row for row in participants):
                raise ValueError()
        except KeyError, TypeError, ValueError:
            raise DataError("Riot match schema changed or owner absent") from None
        return raw

    def own_matches(self, *, set_number, queue=1100, max_matches=200):
        if not isinstance(max_matches, int) or not 1 <= max_matches <= 1000:
            raise DataError("Own-match limit must be in [1,1000]")
        result = []
        for start in range(0, max_matches, 100):
            ids = self.match_ids(start=start, count=min(100, max_matches - start))
            for id in ids:
                self.sleep(1.25)
                match = self.match(id)
                if (
                    match["info"]["tft_set_number"] == set_number
                    and match["info"]["queue_id"] == queue
                ):
                    result.append(match)
            if len(ids) < min(100, max_matches - start):
                break
        return tuple(
            sorted(result, key=lambda m: m["info"]["game_datetime"], reverse=True)
        )
