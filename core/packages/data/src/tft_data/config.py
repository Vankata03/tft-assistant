"""Fail-closed, source-tagged TOML contracts; no invented patch defaults."""

import json
import tomllib
from pathlib import Path

from .models import DataError, Entity, TaggedValue

# The accepted thin-sample policy is an application threshold, not an observed
# provider metadata field or a fitted value.
STATISTICS_MIN_SAMPLES = 500

REQUIRED_STATIC = (
    "team_capacity",
    "xp_table",
    "gold_by_round",
    "streak_gold",
    "interest",
    "player_damage",
    "shop_odds",
    "pool_sizes",
    "rules_flags",
    "wisps",
    "combat_buff_power",
    "wisp_round_cap",
    "opening_encounters",
    "econ_augments",
    "augment_pools",
    "threat_keywords",
    "bench_size",
    "item_recipes",
    "trait_rules",
    "stage_items",
    "level_calendar",
    "lobby_top4_rate",
    "round_order",
    "round_types",
    "sell_values",
)
TUNABLE_FAMILIES = {
    **dict.fromkeys(
        (
            "unit_weight",
            "trait_weight",
            "item_weight",
            "fight_scale",
            "win_scale_by_stage",
            "survivor_scale_by_stage",
            "terminal_hp_weight",
            "terminal_gold_weight",
            "opponent_star_mix",
            "opponent_growth_correction_by_stage",
            "emblem_count_prior",
            "size_level_prior",
            "sighting_persistence_weight",
            "sighting_full_weight_rounds",
            "sighting_half_life_rounds",
        ),
        "1",
    ),
    **dict.fromkeys(
        (
            "pivot_margin_by_stage",
            "pivot_reraise_extra",
            "transition_tolerance",
            "line_margin",
            "comp_defining_margin",
            "board_power_buy_min",
            "wisp_buy_margin",
            "threat_share_on",
            "threat_share_off",
            "review_min_cost",
        ),
        "2",
    ),
    **dict.fromkeys(
        (
            "cost_star_baseline",
            "unit_prior_strength",
            "trait_prior_strength",
            "item_class_prior",
            "item_prior_strength",
            "augment_prior_strength",
            "augment_flag_prior_multiplier",
        ),
        "3",
    ),
    **dict.fromkeys(
        (
            "open_candidate_count",
            "commit_latest_round",
            "rollouts_full",
            "rollouts_reroll",
            "line_candidate_cap",
            "challengers_simulated",
            "gold_floors",
            "all_in_rounds_left",
            "stabilize_rounds_left",
            "item_values",
            "classifier_weights",
            "classifier_threshold",
            "emblem_slack_max",
            "opponent_inference_state_cap",
            "capacity_transition_state_cap",
            "component_income_by_stage",
            "component_discount_by_stage",
            "slam_candidate_cap",
            "open_candidate_temperature",
            "augment_tier_delta",
            "board_settle_seconds",
            "confidence_show_min",
            "confidence_medium_min",
            "confidence_high_min",
            "board_reader_identity_min",
            "field_max_age_seconds",
        ),
        "hand-set",
    ),
    "opponent_growth_curve": "computed",
    "default_lines_by_carry_cost": "computed",
}


def tagged(raw, label, *, families=None):
    if not isinstance(raw, dict):
        raise DataError(f"{label} must be a table")
    result = {}
    for key, item in raw.items():
        if not isinstance(item, dict) or "value" not in item or "source" not in item:
            raise DataError(f"{label}.{key} requires value and source")
        if families and item.get("family") != families.get(key):
            raise DataError(f"{label}.{key} requires family {families.get(key)}")
        result[key] = TaggedValue(
            item["value"],
            item["source"],
            item.get("citation", ""),
            item.get("family", ""),
        )
    return result


def load_patch(path):
    path = Path(path)
    try:
        static = tomllib.loads((path / "static.toml").read_text())
        tunables = tomllib.loads((path / "tunables.toml").read_text())
        entities = json.loads((path / "entities.json").read_text())["entities"]
    except (OSError, ValueError, KeyError) as exc:
        raise DataError(f"Missing or invalid patch files in {path}: {exc}") from None
    if not isinstance(static.get("patch"), str) or not isinstance(
        static.get("set_number"), int
    ):
        raise DataError("Static file requires patch and set_number")
    if tunables.get("patch") != static["patch"]:
        raise DataError("Static and tunables patch labels differ")
    fields = tagged(static.get("fields"), "static")
    missing = set(REQUIRED_STATIC) - fields.keys()
    if missing:
        raise DataError(f"Missing static fields: {sorted(missing)}")
    validate_static(fields)
    families = {
        name: family
        for name, family in TUNABLE_FAMILIES.items()
        if static["set_number"] == 18 or name != "wisp_buy_margin"
    }
    values = tagged(tunables.get("fields"), "tunables", families=families)
    # Historical snapshots predate this optional neutral family-1 correction.
    missing = set(families) - values.keys() - {"opponent_growth_correction_by_stage"}
    if missing:
        raise DataError(f"Missing tunables: {sorted(missing)}")
    parsed = {}
    for item in entities:
        try:
            e = Entity(
                item["id"],
                item["kind"],
                item["name"],
                item.get("cost", 0),
                tuple(item.get("traits", [])),
                item.get("text", ""),
                item.get("icon", ""),
                tagged(item.get("values", {}), "entity"),
            )
        except (KeyError, TypeError) as exc:
            raise DataError(f"Invalid entity schema: {exc}") from None
        if e.id in parsed or not e.id or not e.name:
            raise DataError(f"Duplicate or empty entity: {e.id}")
        if e.kind == "wisp" and e.id not in fields["wisps"].value:
            raise DataError(f"New Wisp {e.id} needs a static effect entry")
        parsed[e.id] = e
    from .capacity import validate_capacity, unit_slot_cost, integral
    validate_capacity(fields,parsed)
    integral(values['capacity_transition_state_cap'].value,'capacity transition search budget',1)
    for entity in parsed.values():
        if entity.kind in ('unit','unit_form'):
            unit_slot_cost(parsed,entity.id)
    return (
        static["patch"],
        static["set_number"],
        fields,
        values,
        parsed,
        tuple(static.get("changed_ids", [])),
    )


def validate_static(fields):
    """Validate complete table shapes before any Engine can consume them."""
    import math
    from collections.abc import Mapping

    def number(value, minimum=0, *, integer=False):
        return (
            not isinstance(value, bool)
            and isinstance(value, int if integer else (int, float))
            and math.isfinite(value)
            and value >= minimum
        )

    def require(ok, name, detail):
        if not ok:
            raise DataError(f"Invalid static {name}: {detail}")

    def table(name, keys=()):
        value = fields[name].value
        require(isinstance(value, Mapping), name, "expected table")
        require(
            all(key in value for key in keys),
            name,
            f"missing entries {sorted(set(keys) - set(value))}",
        )
        return value

    xp = table("xp_table", [str(i) for i in range(1, 10)])
    require(
        all(number(v, 1, integer=True) for v in xp.values()),
        "xp_table",
        "XP values must be positive integers",
    )
    income = table("gold_by_round", ["default"])
    require(
        all(number(v, integer=True) for v in income.values()),
        "gold_by_round",
        "income must be nonnegative gold",
    )
    streak = table("streak_gold")
    require(
        bool(streak)
        and all(
            k.isdigit() and int(k) >= 2 and number(v, integer=True)
            for k, v in streak.items()
        ),
        "streak_gold",
        "requires positive streak thresholds and nonnegative gold",
    )
    interest = table("interest", ["gold_per_tick", "gold_per_interest", "cap"])
    require(
        number(interest["gold_per_tick"], 1, integer=True)
        and number(interest["gold_per_interest"], 1, integer=True)
        and number(interest["cap"], integer=True),
        "interest",
        "invalid interest step or cap",
    )
    damage = table("player_damage", ["stage_base", "per_survivor"])
    require(
        isinstance(damage["stage_base"], Mapping)
        and all(str(i) in damage["stage_base"] for i in range(1, 9)),
        "player_damage",
        "stage_base must cover stages 1..8",
    )
    require(
        all(number(v) for v in damage["stage_base"].values())
        and number(damage["per_survivor"]),
        "player_damage",
        "damage must be nonnegative",
    )
    odds = table("shop_odds", [str(i) for i in range(1, 11)])
    require(
        all(
            isinstance(v, (tuple, list))
            and len(v) == 5
            and all(number(p) and p <= 1 for p in v)
            and abs(sum(v) - 1) < 1e-6
            for v in odds.values()
        ),
        "shop_odds",
        "each level requires five probabilities summing to one",
    )
    pools = table("pool_sizes", [str(i) for i in range(1, 6)])
    require(
        all(number(v, 1, integer=True) for v in pools.values()),
        "pool_sizes",
        "pool copies must be positive integers",
    )
    flags = table(
        "rules_flags",
        [
            "pve_preserves_streak",
            "passive_xp",
            "xp_buy_cost",
            "xp_buy_amount",
            "roll_cost",
            "combat_win_gold",
            "champion_slots_max",
            "unknown_wisp_slots",
            "pve_orb_gold",
        ],
    )
    require(
        isinstance(flags["pve_preserves_streak"], bool),
        "rules_flags",
        "pve_preserves_streak must be boolean",
    )
    for key in ("passive_xp", "xp_buy_cost", "xp_buy_amount", "roll_cost"):
        require(
            number(flags[key], 0 if key == "passive_xp" else 1, integer=True),
            "rules_flags",
            f"invalid {key}",
        )
    require(
        number(flags["unknown_wisp_slots"], 1) and flags["unknown_wisp_slots"] <= 5,
        "rules_flags",
        "unknown Wisp slots must be in [1,5]",
    )
    require(
        isinstance(flags["pve_orb_gold"], Mapping)
        and bool(flags["pve_orb_gold"])
        and all(number(v) for v in flags["pve_orb_gold"].values()),
        "rules_flags",
        "PvE gold needs explicit per-round values",
    )
    kinds = {
        "gold",
        "xp",
        "rolls",
        "shop",
        "combat_buff",
        "unit_grant",
        "polymorph",
        "duplicator",
        "item_grant",
        "sale_modifier",
        "risky",
        "unmodelled",
    }
    for name in ("wisps", "econ_augments", "opening_encounters"):
        for id, effect in table(name).items():
            require(
                isinstance(effect, Mapping)
                and effect.get("effect_kind") in kinds
                and isinstance(effect.get("values"), Mapping),
                name,
                f"{id} requires effect_kind and values",
            )
            if name == "wisps":
                require(
                    number(effect.get("cost"), integer=True)
                    and isinstance(effect.get("offer_stages"), (tuple, list))
                    and bool(effect["offer_stages"]),
                    name,
                    f"{id} requires price and offer stages",
                )
    buffs = table("combat_buff_power")
    require(
        all(number(v) for v in buffs.values()),
        "combat_buff_power",
        "bonuses must be nonnegative",
    )
    cap = table("wisp_round_cap", ["default", "trait_overrides"])
    require(
        number(cap["default"], 1, integer=True)
        and isinstance(cap["trait_overrides"], Mapping)
        and all(number(v, 1, integer=True) for v in cap["trait_overrides"].values()),
        "wisp_round_cap",
        "caps must be positive integers",
    )
    augments = table("augment_pools", ["silver", "gold", "prismatic"])
    require(
        all(
            isinstance(v, (tuple, list)) and all(isinstance(id, str) and id for id in v)
            for v in augments.values()
        ),
        "augment_pools",
        "tier pools require stable IDs",
    )
    words = table("threat_keywords", ["backline_access", "aoe"])
    require(
        all(
            isinstance(v, (tuple, list))
            and bool(v)
            and all(isinstance(word, str) and word for word in v)
            for v in words.values()
        ),
        "threat_keywords",
        "each threat needs nonempty phrases",
    )
    require(
        number(fields["bench_size"].value, 1, integer=True),
        "bench_size",
        "bench size must be positive integer",
    )
    recipes = table("item_recipes")
    require(
        all(
            isinstance(v, (tuple, list))
            and len(v) == 2
            and all(isinstance(id, str) and id for id in v)
            for v in recipes.values()
        ),
        "item_recipes",
        "recipes require exactly two component IDs",
    )

    trait_rules = table("trait_rules")
    for id, rule in trait_rules.items():
        require(isinstance(rule, Mapping), "trait_rules", f"{id} requires a table")
        require(
            set(rule) <= {"replace", "counts", "choose_one", "optional_traits"},
            "trait_rules",
            f"{id} has an unknown grant rule",
        )
        for name in ("replace", "choose_one"):
            if name in rule:
                require(
                    isinstance(rule[name], (list, tuple))
                    and all(
                        isinstance(choice, Mapping)
                        and all(number(v, integer=True) for v in choice.values())
                        for choice in rule[name]
                    ),
                    "trait_rules",
                    f"{id}.{name} must be trait-count maps",
                )
        if "counts" in rule:
            require(
                isinstance(rule["counts"], Mapping)
                and all(number(v, integer=True) for v in rule["counts"].values()),
                "trait_rules",
                f"{id}.counts requires nonnegative trait counts",
            )
    items = table("stage_items", [str(i) for i in range(1, 9)])
    require(
        all(
            isinstance(row, Mapping)
            and {"finished", "component", "high_cost_finished"} <= row.keys()
            and all(number(v) for v in row.values())
            for row in items.values()
        ),
        "stage_items",
        "stage item terms require nonnegative finished/component/high_cost_finished values",
    )
    levels = table("level_calendar")
    require(
        bool(levels)
        and all(number(v, 1, integer=True) and v <= 10 for v in levels.values()),
        "level_calendar",
        "round targets must be levels 1..10",
    )
    require(
        number(fields["lobby_top4_rate"].value)
        and 0 < fields["lobby_top4_rate"].value < 1,
        "lobby_top4_rate",
        "observed lobby rate must be strictly between zero and one",
    )

    rounds = fields["round_order"].value
    require(
        isinstance(rounds, (tuple, list))
        and bool(rounds)
        and len(set(rounds)) == len(rounds),
        "round_order",
        "requires unique ordered round IDs",
    )
    round_types = table("round_types", rounds)
    require(
        all(role in {"combat", "pve", "carousel"} for role in round_types.values()),
        "round_types",
        "unknown round role",
    )
    require(
        all(round in rounds for round in levels),
        "level_calendar",
        "target round is absent from round_order",
    )
    sells = table("sell_values", [str(i) for i in range(1, 6)])
    require(
        all(
            isinstance(row, Mapping)
            and {"1", "2", "3"} <= row.keys()
            and all(number(value, integer=True) for value in row.values())
            for row in sells.values()
        ),
        "sell_values",
        "each cost requires nonnegative gold for stars 1..3",
    )
    require(
        number(flags.get("combat_win_gold"), integer=True),
        "rules_flags",
        "combat_win_gold must be explicit nonnegative gold",
    )
    require(
        number(flags.get("champion_slots_max"), 1, integer=True),
        "rules_flags",
        "champion_slots_max must be explicit positive integer",
    )
