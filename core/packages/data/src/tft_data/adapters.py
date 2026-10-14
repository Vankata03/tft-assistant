"""External source schemas; unknown versions fail instead of producing advice."""

from dataclasses import replace

from .models import DataError, Entity, TaggedValue


class CommunityDragon:
    def __init__(self, payload: dict, set_number: int, *, expected_unit_ids=None):
        self.payload = payload
        self.set_number = set_number
        self.expected_unit_ids = tuple(
            expected_unit_ids
            if expected_unit_ids is not None
            else ("DA_18_Ornn", "DA_18_Sivir")
            if set_number == 18
            else ()
        )
        self.warnings = []

    def entities(self) -> dict[str, Entity]:
        try:
            sets = self.payload["setData"]
            matching = [s for s in sets if s["number"] == self.set_number]
            if not matching:
                raise DataError(f"CommunityDragon has no set {self.set_number}")
            entities = {}
            current_items = set()
            has_item_scope = False
            for dataset in matching:
                if (
                    dataset.get("mutator")
                    and dataset["mutator"] != f"TFTSet{self.set_number}"
                ):
                    raise DataError(
                        "CommunityDragon set mutator does not match requested set"
                    )
                roster = {row["apiName"] for row in dataset["champions"]}
                if not set(self.expected_unit_ids) <= roster:
                    raise DataError(
                        "CommunityDragon roster identity does not match expected stable unit IDs"
                    )
                if (
                    self.set_number == 18
                    and dataset.get("name")
                    and dataset["name"] not in {"Set18", "Enchanted Wilds"}
                ):
                    self.warnings.append(
                        f"CommunityDragon display set label {dataset['name']!r} is inconsistent; mutator and stable roster IDs verified as Set18"
                    )
                if "items" in dataset and "augments" in dataset:
                    has_item_scope = True
                    current_items.update(dataset["items"])
                    current_items.update(dataset["augments"])
                for kind, rows in [
                    ("unit", dataset["champions"]),
                    ("trait", dataset["traits"]),
                ]:
                    for row in rows:
                        id = row["apiName"]
                        if not isinstance(row.get("name"), str) or not row["name"]:
                            self.warnings.append(
                                f"Unnamed non-display entity omitted: {id}"
                            )
                            continue
                        text = (
                            row.get("ability", {}).get("desc", row.get("desc", ""))
                            or ""
                        )
                        cost = row.get("cost", 0)
                        values = {
                            k: TaggedValue(v, "cdragon")
                            for k, v in {
                                "name": row["name"],
                                "cost": cost,
                                "text": text,
                                "ability": row.get("ability", {}),
                                "effects": row.get("effects", []),
                                "breakpoints": tuple(
                                    effect["minUnits"]
                                    for effect in row.get("effects", [])
                                    if "minUnits" in effect
                                ),
                            }.items()
                        }
                        entity_kind = (
                            "npc"
                            if kind == "unit"
                            and self.set_number == 18
                            and id.startswith("TFT")
                            else kind
                        )
                        if (
                            kind == "unit"
                            and id.startswith(("DA_Lux18_", "DA_18_Lux_"))
                            and id != "DA_Lux18_Base"
                        ):
                            entity_kind = "unit_form"
                        canonical = (
                            "DA_Lux18_Base" if entity_kind == "unit_form" else id
                        )
                        values["canonical_id"] = TaggedValue(canonical, "cdragon")
                        values["pool_id"] = TaggedValue(canonical, "cdragon")
                        values["playable"] = TaggedValue(
                            entity_kind == "unit", "cdragon"
                        )
                        entities[id] = Entity(
                            id,
                            entity_kind,
                            row["name"],
                            cost,
                            tuple(row.get("traits", [])),
                            text,
                            icon_url(row.get("squareIcon", row.get("icon", ""))),
                            values,
                        )
            for row in self.payload["items"]:
                id = row["apiName"]
                if has_item_scope and id not in current_items:
                    continue
                if not isinstance(row.get("name"), str) or not row["name"]:
                    self.warnings.append(f"Unnamed non-display entity omitted: {id}")
                    continue
                kind = (
                    "augment"
                    if row.get("isAugment", "Augment" in id)
                    else "wisp"
                    if "Wisp" in id or "set18_mechanicicon" in row.get("icon", "")
                    else "item"
                )
                values = {
                    k: TaggedValue(v, "cdragon")
                    for k, v in {
                        "name": row["name"],
                        "text": row.get("desc", ""),
                        "effects": row.get("effects", {}),
                        "recipe": row.get("composition") or row.get("from") or [],
                    }.items()
                }
                entities[id] = Entity(
                    id,
                    kind,
                    row["name"],
                    text=row.get("desc", ""),
                    icon=icon_url(row.get("icon", "")),
                    values=values,
                )
            if not entities:
                raise DataError("CommunityDragon has no entities")
            aliases = {}
            for entity in entities.values():
                aliases.setdefault(entity.name.casefold(), []).append(entity.id)

            def normalize(value, kind):
                if value in entities and entities[value].kind == kind:
                    return value
                matches = [
                    id
                    for id in aliases.get(str(value).casefold(), [])
                    if entities[id].kind == kind
                ]
                if len(matches) != 1:
                    raise DataError(f"Unknown or ambiguous {kind} reference: {value}")
                return matches[0]

            for id, entity in list(entities.items()):
                if entity.kind in {"unit", "unit_form"}:
                    entities[id] = replace(
                        entity,
                        traits=tuple(
                            normalize(trait, "trait") for trait in entity.traits
                        ),
                    )
                if entity.kind == "item" and entity.values["recipe"].value:
                    entities[id] = replace(
                        entity,
                        values={
                            **entity.values,
                            "recipe": TaggedValue(
                                tuple(
                                    normalize(item, "item")
                                    for item in entity.values["recipe"].value
                                ),
                                "cdragon",
                            ),
                        },
                    )
            return entities
        except (KeyError, TypeError, ValueError) as exc:
            raise DataError(f"CommunityDragon schema changed: {exc}") from None


def dragon_bundle(payload):
    """Validate the bundle boundary before adapters access object fields."""
    if not isinstance(payload, dict) or any(
        not isinstance(body, dict) or not isinstance(body.get('data'), dict)
        or any(not isinstance(row, dict) for row in body['data'].values())
        for body in payload.values()
    ):
        raise DataError('Data Dragon bundle must map kinds to data objects')
    return payload


class DataDragon:
    def __init__(self, payload: dict, version: str, kind: str, *, allowed_ids=None):
        self.payload, self.version, self.kind = payload, version, kind
        self.allowed_ids = allowed_ids

    def entities(self) -> dict[str, Entity]:
        try:
            result = {}
            for key, row in self.payload["data"].items():
                id = row.get("id", key)
                if self.allowed_ids is not None and id not in self.allowed_ids:
                    continue
                icon = f"https://ddragon.leagueoflegends.com/cdn/{self.version}/img/tft-{self.kind}/{row['image']['full']}"
                values = {
                    "name": TaggedValue(row["name"], "ddragon"),
                    "icon": TaggedValue(icon, "ddragon"),
                }
                cost = row.get("tier", 0)
                if cost:
                    values["cost"] = TaggedValue(cost, "ddragon")
                result[id] = Entity(
                    id,
                    "unit" if self.kind == "champion" else self.kind,
                    row["name"],
                    cost,
                    icon=icon,
                    values=values,
                )
            if not result:
                raise DataError("Data Dragon has no entities")
            return result
        except (KeyError, TypeError, ValueError) as exc:
            raise DataError(f"Data Dragon schema changed: {exc}") from None


def merge_entities(
    current: dict[str, Entity], incoming: dict[str, Entity]
) -> dict[str, Entity]:
    result = dict(current)
    for id, new in incoming.items():
        old = result.get(id)
        if old:
            new = replace(
                old,
                kind=old.kind
                if old.kind in {"npc", "unit_form"}
                or new.kind == "item"
                and old.kind in {"augment", "wisp"}
                else new.kind,
                name=new.name,
                cost=new.cost or old.cost,
                icon=new.icon or old.icon,
                text=new.text or old.text,
                traits=new.traits or old.traits,
                values={**old.values, **new.values},
            )
        result[id] = new
    return result


def icon_url(asset):
    if not asset or asset.startswith("https://"):
        return asset
    return f"https://raw.communitydragon.org/latest/game/{asset.lower().removesuffix('.tex')}.png"


def statistics(payload: dict, source: str, patch: str, entities=None):
    """Canonical rows plus checked MetaTFT unit/item and tactics comp shapes."""
    from .models import Statistic

    try:
        if "rows" in payload:
            rows = payload["rows"]
        elif source == "metatft":
            rows = []
            for table, kind in [("units", "unit"), ("itemNames", "item")]:
                for id, row in payload.get(table, {}).items():
                    rows.append(
                        {
                            "id": id,
                            "kind": kind,
                            "avg": row["avg"],
                            "count": row["count"],
                        }
                    )
            if not rows:
                raise DataError("MetaTFT statistics schema has no usable rows")
        elif source == "tactics.tools":
            initial = (
                payload.get("props", {})
                .get("pageProps", {})
                .get("initialData", payload)
            )
            rows = []
            page = payload.get("props", {}).get("pageProps", payload)
            if "statsData" in page:
                data = page["statsData"]
                total = data["totalEntries"]
                if not isinstance(total, int) or total <= 0:
                    raise DataError("tactics.tools totalEntries must be positive")
                for id, row in data["units"].items():
                    rows.append(
                        {
                            "id": id,
                            "kind": "unit",
                            "avg": row["place"],
                            "count": row["count"],
                            "top4_rate": row["top4"] / 100,
                            "play_rate": row["count"] / total,
                        }
                    )
                    # The checked UI labels these exact summary fields 3* Rate / 3★ Place.
                    if row.get("starCount", 0) > 0:
                        rows.append(
                            {
                                "id": id,
                                "kind": "unit",
                                "unit_star": 3,
                                "avg": row["starPlace"],
                                "count": row["starCount"],
                                "top4_rate": row["starTop4"] / 100,
                            }
                        )
                for key, row in data["traits"].items():
                    id, tier = key.rsplit("__", 1)
                    entity = (entities or {}).get(id)
                    points = entity.values.get("breakpoints") if entity else None
                    if (
                        not points
                        or not tier.isdigit()
                        or not 1 <= int(tier) <= len(points.value)
                    ):
                        continue
                    rows.append(
                        {
                            "id": id,
                            "kind": "trait",
                            "avg": row["place"],
                            "count": row["count"],
                            "top4_rate": row["top4"] / 100,
                            "breakpoint": points.value[int(tier) - 1],
                        }
                    )
                for row in data["items"]:
                    rows.append(
                        {
                            "id": row["itemId"],
                            "kind": "item",
                            "avg": row["place"],
                            "count": row["count"],
                            "top4_rate": row["top4"] / 100,
                        }
                    )
            for group in initial.get("groups", []):
                for row in group["full"]["comps"]:
                    rows.append(
                        {
                            "id": "|".join(sorted(row["units"])),
                            "kind": "comp",
                            "avg": row["place"],
                            "count": row["count"],
                        }
                    )
        else:
            raise DataError(f"No statistics schema for {source}")
        result = []
        for row in rows:
            count = row["count"]
            avg = row["avg"]
            pick_stage = row.get("pick_stage")
            if source == "metatft" and row["kind"] == "augment" and "order" in row:
                order = row["order"]
                if not isinstance(order, int) or isinstance(order, bool) or order not in (0, 1, 2):
                    raise DataError("MetaTFT augment order must be 0, 1 or 2")
                if pick_stage is not None and pick_stage != order + 1:
                    raise DataError("Conflicting augment pick_stage and MetaTFT order")
                pick_stage = order + 1
            if (
                not isinstance(count, int)
                or count < 0
                or isinstance(avg, bool)
                or not 1 <= avg <= 8
            ):
                raise DataError(
                    "Statistics require nonnegative board samples and placement in [1,8]"
                )
            result.append(
                Statistic(
                    str(row["id"]),
                    row["kind"],
                    float(avg),
                    count,
                    patch,
                    source,
                    unit_star=row.get("unit_star"),
                    item_id=row.get("item_id"),
                    comp_id=row.get("comp_id"),
                    variance=row.get("variance"),
                    top4_rate=row.get("top4_rate"),
                    play_rate=row.get("play_rate"),
                    breakpoint=row.get("breakpoint"),
                    positioning=tuple(row.get("positioning", ())),
                    pick_stage=pick_stage,
                )
            )
        return tuple(result)
    except (KeyError, TypeError, ValueError) as exc:
        raise DataError(f"{source} statistics schema changed: {exc}") from None


def guides(payload, entities):
    from .models import Guide

    by_name = {}
    for entity in entities.values():
        by_name.setdefault(entity.name.casefold(), []).append(entity.id)

    def normalize(value):
        if isinstance(value, dict):
            value = value["apiName"]
        if value in entities:
            return value
        ids = by_name.get(value.casefold(), [])
        if len(ids) != 1:
            raise DataError(f"Unknown or ambiguous Guide entity: {value}")
        return ids[0]

    try:
        records = payload["guides"]
        result = {}
        for row in records:
            final = row["finalComp"]
            early = row["earlyComp"]
            positions = {}
            items = {}
            for unit in final:
                id = normalize(unit["apiName"])
                if unit.get("boardIndex") is not None:
                    if (
                        not isinstance(unit["boardIndex"], int)
                        or not 0 <= unit["boardIndex"] < 28
                    ):
                        raise DataError("Guide position outside 0..27")
                    positions[id] = unit["boardIndex"]
                items[id] = tuple(normalize(item) for item in unit.get("items", []))
            result[row["id"]] = Guide(
                row["id"],
                row["tier"],
                tuple(normalize(u) for u in final),
                tuple(normalize(u) for u in early),
                (normalize(row["mainChampion"]),),
                items,
                positions,
                {tip["stage"]: tip["tip"] for tip in row["tips"]},
                {
                    normalize(a): "Guide"
                    for a in row["augments"]
                    if not a.get("disabled", False)
                },
                tuple(normalize(i) for i in row["carousel"]),
                tuple(a["id"] for a in row["altBuilds"] if "id" in a),
                tuple(row.get("line", [])),
                key_ids=tuple(normalize(value) for value in row.get("keyUnits", [])),
                early_items={
                    normalize(u["apiName"]): tuple(
                        normalize(item) for item in u.get("items", [])
                    )
                    for u in early
                },
                alternative_builds=tuple(row["altBuilds"]),
                cluster_id=row.get("cluster_id"),
            )
        return result
    except (KeyError, ValueError, TypeError) as exc:
        raise DataError(f"TFT Academy schema changed: {exc}") from None
