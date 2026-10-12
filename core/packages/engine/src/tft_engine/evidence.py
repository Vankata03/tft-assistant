"""Lossless finite JSON evidence with authenticated, shared records.

Each record hashes its encoded shape and child references. Resolving a member
verifies the root-to-member path without expanding unrelated distributions.
Resolving the root reconstructs and verifies the complete original JSON value.
"""

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from types import MappingProxyType


IDENTITY = re.compile(r"sha256:[0-9a-f]{64}\Z")


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def content_id(value):
    return "sha256:" + sha256(canonical_bytes(value)).hexdigest()


def _has_reference(value):
    if isinstance(value, dict):
        return set(value) == {"$evidence"} or any(_has_reference(child) for child in value.values())
    return isinstance(value, list) and any(_has_reference(child) for child in value)


@dataclass(frozen=True)
class EvidenceGraph:
    root_id: str
    objects: object

    def __post_init__(self):
        records = dict(self.objects)
        if not isinstance(self.root_id, str) or not IDENTITY.fullmatch(self.root_id):
            raise ValueError("Invalid evidence root identity")
        if any(not isinstance(key, str) or not IDENTITY.fullmatch(key)
               or not isinstance(body, bytes) for key, body in records.items()):
            raise ValueError("Invalid evidence record")
        object.__setattr__(self, "objects", MappingProxyType(records))

    @classmethod
    def factor(cls, value, *, threshold=1024):
        if type(threshold) is not int or threshold < 1:
            raise ValueError("Evidence threshold must be positive")
        value = json.loads(canonical_bytes(value))
        objects = {}

        def encode(row, force=False):
            if isinstance(row, dict):
                result = {key: encode(child) for key, child in row.items()}
                if set(result) in ({"$evidence"}, {"$literal"}):
                    result = {"$literal": result}
            elif isinstance(row, list):
                result = [encode(child) for child in row]
            else:
                result = row
            body = canonical_bytes({"v": 1, "value": result})
            if force or len(body) >= threshold:
                identity = "sha256:" + sha256(body).hexdigest()
                objects[identity] = body
                return {"$evidence": identity}
            return result

        return cls(encode(value, True)["$evidence"], objects)

    def _record(self, identity):
        if not isinstance(identity, str) or identity not in self.objects:
            raise ValueError("Evidence reference unavailable")
        body = self.objects[identity]
        if "sha256:" + sha256(body).hexdigest() != identity:
            raise ValueError("Evidence bytes do not match their content identity")
        value = json.loads(body)
        if not isinstance(value, dict) or type(value.get("v")) is not int or value["v"] != 1 or set(value) != {"v", "value"}:
            raise ValueError("Unsupported evidence record")
        # This also rejects non-finite JSON accepted by Python's decoder.
        if canonical_bytes(value) != body:
            raise ValueError("Evidence record is not canonical finite JSON")
        return value["value"]

    def _container(self, row):
        active = set()
        while isinstance(row, dict) and set(row) == {"$evidence"}:
            identity = row["$evidence"]
            if identity in active:
                raise ValueError("Cyclic evidence reference")
            active.add(identity)
            row = self._record(identity)
        if isinstance(row, dict) and set(row) == {"$literal"}:
            literal = row["$literal"]
            if not isinstance(literal, dict):
                raise ValueError("Invalid literal evidence map")
            return literal
        return row

    def _select(self, path):
        if not isinstance(path, (tuple, list)) or len(path) > 64:
            raise ValueError("Invalid evidence path")
        row = {"$evidence": self.root_id}
        for key in path:
            row = self._container(row)
            if isinstance(row, dict) and isinstance(key, str) and key in row:
                row = row[key]
            elif isinstance(row, list) and type(key) is int and 0 <= key < len(row):
                row = row[key]
            else:
                raise ValueError("Evidence path is not a member of this delivery")
        return row

    def resolve(self, *, path=()):
        """Restore an authenticated root member, or all evidence for offline use."""
        active = set()

        def expand(row):
            if isinstance(row, dict):
                if set(row) == {"$evidence"}:
                    identity = row["$evidence"]
                    if identity in active:
                        raise ValueError("Cyclic evidence reference")
                    active.add(identity)
                    try:
                        return expand(self._record(identity))
                    finally:
                        active.remove(identity)
                if set(row) == {"$literal"}:
                    row = row["$literal"]
                    if not isinstance(row, dict):
                        raise ValueError("Invalid literal evidence map")
                return {key: expand(value) for key, value in row.items()}
            if isinstance(row, list):
                return [expand(value) for value in row]
            return row

        return expand(self._select(path))

    def page(self, *, path=(), cursor=0, limit=32, max_bytes=65536):
        """Return a bounded member page; large children retain exact path references."""
        if type(cursor) is not int or cursor < 0 or type(limit) is not int or not 1 <= limit <= 128 or type(max_bytes) is not int or max_bytes < 512:
            raise ValueError("Invalid evidence page bounds")
        selected = self._container(self._select(path))
        if isinstance(selected, dict):
            members = list(selected.items())
            kind = "object"
        elif isinstance(selected, list):
            members = list(enumerate(selected))
            kind = "array"
        elif isinstance(selected, str):
            chunk_size = max(1, min(128, (max_bytes - 384) // 6))
            members = [(offset, selected[offset:offset + chunk_size])
                       for offset in range(0, len(selected), chunk_size)]
            kind = "string"
        else:
            members = [(None, selected)]
            kind = "value"
        if cursor > len(members):
            raise ValueError("Evidence cursor exceeds member count")
        result = {"evidence_id": self.root_id, "path": list(path), "kind": kind,
                  "total": len(members), "cursor": cursor, "next_cursor": None,
                  "items": []}
        for key, encoded in members[cursor:cursor + limit]:
            member_path = list(path) + ([] if key is None or kind == "string" else [key])
            # Encoded size is a cheap upper bound only for inline nodes. A linked
            # child remains a reference, even when its decoded value is enormous.
            if kind == "string":
                item = {"path": member_path, "offset": key, "value": encoded}
            elif _has_reference(encoded) or len(canonical_bytes(encoded)) > 1024:
                child = self._container(encoded)
                item = {"path": member_path, "reference": True,
                        "kind": "object" if isinstance(child, dict) else "array" if isinstance(child, list) else "value"}
            else:
                item = {"path": member_path, "value": self.resolve(path=member_path)}
            result["items"].append(item)
            result["next_cursor"] = cursor + len(result["items"])
            if len(canonical_bytes(result)) > max_bytes:
                result["items"].pop()
                if not result["items"]:
                    raise ValueError("Evidence page metadata exceeds its byte budget")
                result["next_cursor"] = cursor + len(result["items"])
                break
        if result["next_cursor"] == len(members):
            result["next_cursor"] = None
        if len(canonical_bytes(result)) > max_bytes:
            raise ValueError("Evidence page metadata exceeds its byte budget")
        return result

    def to_dict(self):
        return {"v": 1, "root_id": self.root_id,
                "objects": {identity: json.loads(body) for identity, body in self.objects.items()}}

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or type(value.get("v")) is not int or value["v"] != 1 or set(value) != {"v", "root_id", "objects"} or not isinstance(value["objects"], dict):
            raise ValueError("Unsupported evidence graph")
        return cls(value["root_id"], {identity: canonical_bytes(body)
                                    for identity, body in value["objects"].items()})
