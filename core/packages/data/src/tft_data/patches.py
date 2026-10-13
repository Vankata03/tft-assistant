"""Prepare reviewable patch candidates; the owner commits accepted game values."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import tomllib
import urllib.request
from datetime import datetime
from pathlib import Path

import tomli_w

from .adapters import CommunityDragon, DataDragon, merge_entities
from .config import load_patch
from .models import DataError, plain
from .entity_overlay import apply_entity_overlay, entities_payload, render


def download_json(url):
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "TFTAssistant/0.1"}),
            timeout=30,
        ) as response:
            return json.load(response)
    except (OSError, ValueError) as exc:
        raise DataError(f"Dragon refresh unavailable: {type(exc).__name__}") from None


def new_patch(
    data_dir,
    patch,
    previous,
    live_at,
    *,
    set_number=None,
    cdragon=None,
    ddragon=None,
    dragon_version=None,
    offline=False,
    overrides=None,
):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", patch):
        raise DataError("Patch label must be a plain directory name")
    data_dir = Path(data_dir)
    old = data_dir / previous
    target = data_dir / patch
    if target.exists():
        raise DataError(f"Patch already exists: {target}")
    when = datetime.fromisoformat(live_at)
    if when.tzinfo is None:
        raise DataError("Confirmed live date needs EUNE timezone offset")
    _old_patch, old_set, _, _, old_entities, _ = load_patch(old)
    set_number = set_number or old_set
    new_set = set_number != old_set
    if new_set:
        raise DataError(
            "A new set requires a fresh reviewed static file; patch carry is not valid"
        )
    if not offline:
        cdragon = cdragon or download_json(
            "https://raw.communitydragon.org/latest/cdragon/tft/en_us.json"
        )
        if ddragon is None:
            dragon_version = (
                dragon_version
                or download_json(
                    "https://ddragon.leagueoflegends.com/api/versions.json"
                )[0]
            )
            ddragon = {}
            for kind in ("champion", "item", "trait"):
                ddragon[kind] = download_json(
                    f"https://ddragon.leagueoflegends.com/cdn/{dragon_version}/data/en_US/tft-{kind}.json"
                )
    static = tomllib.loads((old / "static.toml").read_text())
    tunables = tomllib.loads((old / "tunables.toml").read_text())
    static["patch"] = patch
    tunables["patch"] = patch
    for value in static["fields"].values():
        value["source"] = "carried"
    entities = dict(old_entities)
    if cdragon:
        entities = merge_entities(
            entities, CommunityDragon(cdragon, set_number).entities()
        )
    if ddragon:
        for kind, payload in ddragon.items():
            entities = merge_entities(
                entities,
                DataDragon(
                    payload, dragon_version or patch, kind, allowed_ids=set(entities)
                ).entities(),
            )
    # Current external IDs define removals when a complete CommunityDragon feed is supplied.
    if cdragon:
        current = CommunityDragon(cdragon, set_number).entities()
        entities = {id: e for id, e in entities.items() if id in current}
    report = [
        f"# Patch {patch} candidate",
        f"Confirmed EUNE live time: {when.isoformat()}.",
        "Review every carried field named in the patch notes before committing this candidate.",
    ]
    if offline:
        report.append(
            "External names, icons and values were not refreshed because --offline was requested."
        )
    for id in sorted(set(entities) - set(old_entities)):
        report.append(f"Added entity: {id}.")
    for id in sorted(set(old_entities) - set(entities)):
        report.append(f"Removed entity: {id}.")
    for id in sorted(set(old_entities) & set(entities)):
        before = plain(vars(old_entities[id]))
        after = plain(vars(entities[id]))
        for key in after:
            if before.get(key) != after[key]:
                report.append(
                    f"Changed {id}.{key}: {before.get(key)!r} -> {after[key]!r}."
                )
    keywords = static["fields"]["threat_keywords"]["value"]
    for id, e in entities.items():
        matches = {
            tag: [phrase for phrase in phrases if phrase.lower() in e.text.lower()]
            for tag, phrases in keywords.items()
        }
        tags = [tag for tag, phrases in matches.items() if phrases]
        old_tags = list(old_entities[id].threat_tags) if id in old_entities else []
        if tags != old_tags:
            report.append(
                f"Threat tags {id}: {old_tags} -> {tags}; matched phrases {matches}."
            )
        if e.kind == "wisp" and id not in static["fields"]["wisps"]["value"]:
            report.append(
                f"BLOCKED: New Wisp {id} requires effect kind and values from patch notes. Validation will reject this candidate."
            )
    static["changed_ids"] = sorted(
        id
        for id, e in entities.items()
        if id not in old_entities or plain(vars(e)) != plain(vars(old_entities[id]))
    )
    calendar_path = data_dir / "patches.toml"
    calendar = (
        tomllib.loads(calendar_path.read_text())
        if calendar_path.exists()
        else {"patches": {}}
    )
    calendar.setdefault("patches", {})[patch] = when.isoformat()
    data_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=data_dir) as temp:
        folder = Path(temp) / patch
        folder.mkdir()
        (folder / "static.toml").write_text(tomli_w.dumps(static))
        (folder / "tunables.toml").write_text(tomli_w.dumps(tunables))
        (folder / "entities.json").write_text(
            json.dumps(
                {
                    "entities": [
                        {
                            **plain(vars(e)),
                            "values": {k: plain(vars(v)) for k, v in e.values.items()},
                        }
                        for e in entities.values()
                    ]
                },
                indent=2,
            )
        )
        (folder / "patch-diff.md").write_text("\n\n".join(report) + "\n")
        os.replace(folder, target)
        temp_calendar = Path(temp) / "patches.toml"
        temp_calendar.write_text(tomli_w.dumps(calendar))
        os.replace(temp_calendar, calendar_path)
    return target


def bootstrap_patch(
    data_dir,
    patch,
    static_file,
    tunables_file,
    *,
    cdragon=None,
    ddragon=None,
    dragon_version=None,
    entity_overlay_file=None,
):
    """Materialize a candidate from reviewed rule files and checked primary payloads."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", patch):
        raise DataError("Invalid patch label")
    static = tomllib.loads(Path(static_file).read_text())
    tunables = tomllib.loads(Path(tunables_file).read_text())
    if static.get("patch") != patch or tunables.get("patch") != patch:
        raise DataError("Bootstrap files must name the requested patch")
    cdragon = cdragon or download_json(
        "https://raw.communitydragon.org/latest/cdragon/tft/en_us.json"
    )
    adapter = CommunityDragon(cdragon, static["set_number"])
    entities = adapter.entities()
    for kind, payload in (ddragon or {}).items():
        entities = merge_entities(
            entities,
            DataDragon(
                payload,
                dragon_version or payload.get("version", patch),
                kind,
                allowed_ids=set(entities),
            ).entities(),
        )
    entities, overlay_report=apply_entity_overlay(entities,entity_overlay_file,patch,static['set_number'])
    parent = Path(data_dir)
    target = parent / patch
    if target.exists():
        raise DataError(f"Patch already exists: {target}")
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=parent) as temp:
        candidate = Path(temp) / patch
        candidate.mkdir()
        (candidate / "static.toml").write_text(tomli_w.dumps(static))
        (candidate / "tunables.toml").write_text(tomli_w.dumps(tunables))
        (candidate / "entities.json").write_text(render(entities_payload(entities)))
        # Validation fails before any target is published when the rules are incomplete.
        load_patch(candidate)
        report = [
            "# Bootstrap candidate",
            "Review and commit the source-tagged static, tunables and entity files before using this candidate in a Live session.",
            "The candidate contains no fitted-parameter or live-game qualification claim.",
            *adapter.warnings,
            *overlay_report,
        ]
        (candidate / "patch-diff.md").write_text("\n\n".join(report) + "\n")
        os.replace(candidate, target)
    return target


def prepare_new_set(
    data_dir,
    patch,
    previous,
    static_file,
    tunables_file,
    live_at,
    *,
    cdragon=None,
    ddragon=None,
    dragon_version=None,
    entity_overlay_file=None,
    overrides=None,
):
    """Use fresh rules, carry non-set tunables and archive old owner overrides."""
    if overrides and Path(overrides).exists():
        old_static = tomllib.loads(
            (Path(data_dir) / previous / "static.toml").read_text()
        )
        archive = Path(overrides).with_name(
            f"overrides-set{old_static['set_number']}.toml"
        )
        if archive.exists():
            raise DataError(f"Override archive already exists: {archive}")
    previous = Path(data_dir) / previous
    old = tomllib.loads((previous / "static.toml").read_text())
    fresh = tomllib.loads(Path(static_file).read_text())
    if fresh["set_number"] == old["set_number"]:
        raise DataError("New-set workflow requires a different set number")
    tunables = tomllib.loads(Path(tunables_file).read_text())
    tunables["fields"].pop("wisp_buy_margin", None)
    for row in tunables["fields"].values():
        if row.get("family") == "3":
            row["source"] = "carried"
    when = datetime.fromisoformat(live_at)
    if when.tzinfo is None:
        raise DataError("Confirmed EUNE live time needs a timezone offset")
    with tempfile.TemporaryDirectory() as temporary:
        file = Path(temporary) / "tunables.toml"
        file.write_text(tomli_w.dumps(tunables))
        target = bootstrap_patch(
            data_dir,
            patch,
            static_file,
            file,
            cdragon=cdragon,
            ddragon=ddragon,
            dragon_version=dragon_version,
            entity_overlay_file=entity_overlay_file,
        )
    if overrides and Path(overrides).exists():
        owner_file = Path(overrides)
        archive = owner_file.with_name(f"overrides-set{old['set_number']}.toml")
        if archive.exists():
            raise DataError(f"Override archive already exists: {archive}")
        shutil.copy2(owner_file, archive)
        owner_file.write_text("[entities]\n\n[guides]\n\n[tunables]\n")
    calendar = Path(data_dir) / "patches.toml"
    content = (
        tomllib.loads(calendar.read_text()) if calendar.exists() else {"patches": {}}
    )
    content.setdefault("patches", {})[patch] = when.isoformat()
    calendar.write_text(tomli_w.dumps(content))
    with (target / "patch-diff.md").open("a") as report:
        report.write(
            "\n\nNew-set repair order: validate fresh rules and threat keywords; refresh names and icons; recheck Guides and statistics; retrain recognition; replace the set-mechanic plug-in. Fitted tunables must be refitted after the first ten games.\n"
        )
    return target
