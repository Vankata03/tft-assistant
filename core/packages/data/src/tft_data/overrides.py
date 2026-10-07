"""Owner overrides survive patches; stale IDs are warnings, never load failures."""

import re
import tomllib
from dataclasses import replace
from pathlib import Path

from .models import DataError, TaggedValue


def patch_key(value):
    return tuple(
        int(v) if v.isdigit() else v for v in re.findall(r"\d+|[a-z]+", value.lower())
    )


def apply_overrides(path, patch, entities, guides, tunables, changed_ids):
    warnings = []
    if path is None or not Path(path).exists():
        return entities, guides, tunables, warnings
    try:
        raw = tomllib.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise DataError(f"Invalid owner overrides: {exc}") from None
    entities, guides, tunables = dict(entities), dict(guides), dict(tunables)
    for section, destination in [("entities", entities), ("guides", guides)]:
        for id, override in raw.get(section, {}).items():
            if id not in destination:
                warnings.append(f"Stale owner override ignored: {id}")
                continue
            if override.get("until_patch") and patch_key(patch) > patch_key(
                override["until_patch"]
            ):
                warnings.append(f"Expired owner override ignored: {id}")
                continue
            if id in changed_ids:
                warnings.append(f"Review owner override changed this patch: {id}")
            fields = {k: v for k, v in override.items() if k != "until_patch"}
            if section == "entities":
                fields["values"] = {
                    **destination[id].values,
                    **{k: TaggedValue(v, "owner") for k, v in fields.items()},
                }
                for name in ("traits", "threat_tags"):
                    if name in fields:
                        fields[name] = tuple(fields[name])
            try:
                destination[id] = replace(destination[id], **fields)
            except TypeError as exc:
                raise DataError(f"Unknown override field {id}: {exc}") from None
    for id, tags in raw.get("threat_tags", {}).items():
        if id not in entities:
            warnings.append(f"Stale threat-tag override ignored: {id}")
            continue
        if not isinstance(tags, list) or any(
            tag not in {"aoe", "backline_access"} for tag in tags
        ):
            raise DataError(f"Invalid threat-tag override for {id}")
        if id in changed_ids:
            warnings.append(
                f"Review owner threat-tag override changed this patch: {id}"
            )
        entities[id] = replace(
            entities[id],
            threat_tags=tuple(tags),
            values={**entities[id].values, "threat_tags": TaggedValue(tags, "owner")},
        )
    for name, value in raw.get("tunables", {}).items():
        if name not in tunables:
            warnings.append(f"Stale tunable override ignored: {name}")
            continue
        tunables[name] = TaggedValue(
            value.get("value", value) if isinstance(value, dict) else value,
            "owner",
            family=tunables[name].family,
        )
    return entities, guides, tunables, warnings
