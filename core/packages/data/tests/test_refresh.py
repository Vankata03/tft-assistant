from datetime import UTC, datetime

import pytest
from tft_data import DataStore

NOW = datetime(2026, 10, 6, tzinfo=UTC)


def test_augment_pick_stage_survives_refresh_persistence_and_thin_sample_prior_keys(tmp_path):
    from tft_data.sources import MemorySource
    from datetime import timedelta
    path=patch_files(tmp_path/'patch')
    rows=[{'id':'augment','kind':'augment','avg':3.0+order,'count':1000,'order':order} for order in (0,1,2)]
    source=MemorySource('metatft','statistics','test.1',NOW,{'rows':rows})
    store=DataStore(tmp_path/'snapshots')
    first=store.refresh(path,sources=(source,),now=NOW).snapshot
    assert [(r.pick_stage,r.average_placement) for r in first.statistics]==[(1,3.0),(2,4.0),(3,5.0)]
    restored=DataStore(tmp_path/'snapshots').refresh(path,now=NOW+timedelta(minutes=1)).snapshot
    assert [(r.pick_stage,r.average_placement) for r in restored.statistics]==[(1,3.0),(2,4.0),(3,5.0)]
    thin=MemorySource('metatft','statistics','test.1',NOW+timedelta(hours=1),{'rows':[dict(row,avg=7.0,count=10) for row in rows]})
    carried=store.refresh(path,sources=(thin,),now=NOW+timedelta(hours=1)).snapshot
    assert [(r.pick_stage,r.average_placement,r.stale) for r in carried.statistics]==[(1,3.0,True),(2,4.0,True),(3,5.0,True)]


def test_missing_patch_does_not_invent_game_data(tmp_path):
    store = DataStore(tmp_path / "snapshots")
    result = store.refresh(tmp_path / "missing", now=NOW)
    assert result.snapshot is None
    assert "missing" in result.warnings[0].lower()


def test_unknown_tier_patch_stays_unavailable_and_its_provenance_survives_reload(
    tmp_path, monkeypatch
):
    from packages.data.tests.test_sources import (
        external_responses,
        TIERS_URL,
        DONOR_URL,
    )
    from tft_data.sources import HTTPSource

    external_responses(
        monkeypatch,
        {
            TIERS_URL: {
                "updated": 1791641438134,
                "tft_set": "TFTSet18",
                "tier_list_set": "TFTSet18",
                "queue_id": 1100,
                "content": {
                    "updated_at": "2026-10-10T05:21:29.598Z",
                    "content": {
                        "tierList": [
                            {
                                "label": "S",
                                "content": [
                                    {"type": "augment", "id": "fixture-augment"}
                                ],
                            }
                        ]
                    },
                },
            },
            DONOR_URL: {"patch": "test.1", "updated": 1791641414471},
        },
    )
    source = HTTPSource("tiers", "enrichment", TIERS_URL, DONOR_URL, provider="metatft")
    root = tmp_path / "snapshots"
    result = DataStore(root).refresh(
        patch_files(tmp_path / "patch"), now=NOW, sources=[source]
    )

    assert "confirmed patch" in "\n".join(result.warnings).lower()
    assert not result.snapshot.augment_tiers
    observed = result.snapshot.sources["tiers"]
    assert observed.patch is None and not observed.qualified
    assert observed.identity["tft_set"] == "TFTSet18"
    assert observed.donor_hint["patch"] == "test.1"
    restored = DataStore(root).get(result.snapshot.snapshot_id)
    assert restored.sources["tiers"] == observed


def test_unqualified_tier_update_retains_qualified_data_and_separate_attempt_metadata(
    tmp_path, monkeypatch
):
    from datetime import timedelta
    from packages.data.tests.test_sources import external_responses, TIERS_URL
    from tft_data.sources import HTTPSource

    body = {
        "patch": "test.1",
        "updated": 1791641438134,
        "global_augment_tiers": {"fixture-augment": "S"},
    }
    responses = {TIERS_URL: body}
    external_responses(monkeypatch, responses)
    source = HTTPSource("tiers", "enrichment", TIERS_URL, provider="metatft")
    root = tmp_path / "snapshots"
    path = patch_files(tmp_path / "patch")
    store = DataStore(root)
    checked_at = datetime(2026, 10, 10, 16, tzinfo=UTC)
    good = store.refresh(path, now=checked_at, sources=[source]).snapshot
    assert good.augment_tiers["fixture-augment"] == "S"
    responses[TIERS_URL] = {
        "updated": 1791645038134,
        "global_augment_tiers": {"fixture-augment": "D"},
    }

    result = store.refresh(path, now=checked_at + timedelta(hours=2), sources=[source])

    assert result.snapshot.augment_tiers["fixture-augment"] == "S"
    state = result.snapshot.sources["tiers"]
    assert state.qualified and state.patch == "test.1"
    assert state.updated_at == good.sources["tiers"].updated_at
    assert state.fetched_at == good.sources["tiers"].fetched_at
    assert state.last_attempt["patch"] is None
    assert state.last_attempt["qualified"] is False
    assert "confirmed patch" in "\n".join(result.warnings).lower()
    assert DataStore(root).get(result.snapshot.snapshot_id).sources["tiers"] == state
    assert good.sources["tiers"].last_attempt == {}


def test_configured_statistics_require_actual_cohort_evidence(tmp_path, monkeypatch):
    from packages.data.tests.test_sources import external_responses, DONOR_URL
    from tft_data.source_config import SourceConfiguration

    manifest = tmp_path / "sources.toml"
    manifest.write_text("""schema_version=1
[statistics]
minimum_rank="DIAMOND"
regions="all"
[refresh]
sources=["units"]
[sources.units]
provider="metatft"
kind="statistics"
url="https://example.invalid/unit_items_processed"
""")
    body = {
        "patch": "test.1",
        "updated": 1791641438134,
        "rows": [{"id": "fixture-unit", "kind": "unit", "avg": 4.2, "count": 900}],
    }
    responses = {DONOR_URL: body}
    external_responses(monkeypatch, responses)
    config = SourceConfiguration.load(manifest)
    path = patch_files(tmp_path / "patch")
    store = DataStore(tmp_path / "snapshots")
    checked_at = datetime(2026, 10, 10, 16, tzinfo=UTC)

    missing = store.refresh(path, now=checked_at, sources=config.sources)

    assert not missing.snapshot.statistics
    assert missing.snapshot.sources["units"].cohort == {
        "minimum_rank": None,
        "regions": None,
    }
    assert "minimum_rank" in "\n".join(missing.warnings)
    assert "regions" in "\n".join(missing.warnings)
    responses[DONOR_URL] = {
        **body,
        "filters": {"minimum_rank": "DIAMOND", "regions": "all"},
    }
    qualified = store.refresh(path, now=checked_at, sources=config.sources)
    assert qualified.snapshot.statistics[0].average_placement == 4.2
    assert qualified.snapshot.sources["units"].qualified
    assert qualified.snapshot.sources["units"].cohort == {
        "minimum_rank": "DIAMOND",
        "regions": "all",
    }


def patch_files(path):
    import tomli_w
    from tft_data.config import REQUIRED_STATIC, TUNABLE_FAMILIES

    path.mkdir()
    # Synthetic fixture rules, deliberately distinct from live Set 18 values.
    fixture_rules = {
        "xp_table": {str(i): i * 2 for i in range(1, 10)},
        "gold_by_round": {"default": 4, "1-1": 0},
        "streak_gold": {"2": 1, "4": 2, "6": 3},
        "interest": {"gold_per_tick": 10, "gold_per_interest": 1, "cap": 5},
        "player_damage": {
            "stage_base": {str(i): i for i in range(1, 9)},
            "per_survivor": 1,
        },
        "shop_odds": {str(i): [1.0, 0.0, 0.0, 0.0, 0.0] for i in range(1, 11)},
        "pool_sizes": {str(i): 20 for i in range(1, 6)},
        "rules_flags": {
            "pve_preserves_streak": True,
            "passive_xp": 2,
            "xp_buy_cost": 4,
            "xp_buy_amount": 4,
            "roll_cost": 2,
            "combat_win_gold": 1,
            "champion_slots_max": 5,
            "unknown_wisp_slots": 4.5,
            "pve_orb_gold": {"1-2": 0},
        },
        "wisps": {},
        "combat_buff_power": {},
        "wisp_round_cap": {"default": 1, "trait_overrides": {}},
        "opening_encounters": {},
        "econ_augments": {},
        "augment_pools": {"silver": [], "gold": [], "prismatic": []},
        "threat_keywords": {},
        "team_capacity": {"levels": {str(level): level for level in range(1,11)}, "trait_bonuses": [], "held_augment_slots": {}, "inventory_item_slots": {}, "transition_policy": {"deploy":"reserve_before","swap":"remove_then_reserve","bench":"validate_after"}},
        "bench_size": 9,
        "item_recipes": {},
        "trait_rules": {},
        "stage_items": {
            str(i): {"finished": 1, "component": 0.5, "high_cost_finished": 0}
            for i in range(1, 9)
        },
        "level_calendar": {"1-1": 1, "2-1": 4, "3-2": 6, "4-2": 8},
        "lobby_top4_rate": 0.5,
        "round_order": ["1-1", "1-2", "2-1", "3-2", "4-2"],
        "round_types": {
            "1-1": "carousel",
            "1-2": "pve",
            "2-1": "combat",
            "3-2": "combat",
            "4-2": "combat",
        },
        "sell_values": {
            str(cost): {"1": cost, "2": 3 * cost, "3": 9 * cost} for cost in range(1, 6)
        },
    }
    static = {
        name: {"value": fixture_rules[name], "source": "default"}
        for name in REQUIRED_STATIC
    }
    static["threat_keywords"]["value"] = {
        "backline_access": ["backline"],
        "aoe": ["nearby enemies"],
    }
    (path / "static.toml").write_text(
        tomli_w.dumps({"patch": "test.1", "set_number": 18, "fields": static})
    )
    tunables = {
        name: {"value": 1, "source": "default", "family": family}
        for name, family in TUNABLE_FAMILIES.items()
    }
    (path / "tunables.toml").write_text(
        tomli_w.dumps({"patch": "test.1", "fields": tunables})
    )
    (path / "entities.json").write_text(
        '{"entities":[{"id":"fixture-unit","kind":"unit","name":"Fixture unit","cost":2,"traits":[],"text":"Reaches the backline","icon":"https://example.invalid/icon.png","values":{"team_slot_cost":{"value":1,"source":"default"}}}]}'
    )
    return path


def test_refresh_publishes_immutable_snapshot_and_retains_it_on_invalid_static(
    tmp_path,
):
    path = patch_files(tmp_path / "patch")
    store = DataStore(tmp_path / "snapshots")
    first = store.refresh(path, now=NOW)
    assert first.snapshot.names["fixture-unit"] == "Fixture unit"
    with pytest.raises(TypeError):
        first.snapshot.static["shop_odds"].value["8"] = [1]
    assert first.snapshot.entities["fixture-unit"].threat_tags == ("backline_access",)
    (path / "static.toml").write_text('patch="test.1"')
    failed = store.refresh(path, now=NOW)
    assert failed.snapshot.snapshot_id == first.snapshot.snapshot_id
    assert "stale since" in failed.warnings[0]


def test_refresh_uses_cdragon_unit_names_and_ddragon_icons(tmp_path):
    path = patch_files(tmp_path / "patch")
    from tft_data.adapters import CommunityDragon, DataDragon

    cdragon = {
        "setData": [
            {
                "number": 18,
                "champions": [
                    {
                        "apiName": "fixture-unit",
                        "name": "Fixture translated",
                        "cost": 2,
                        "traits": ["Fixture trait"],
                        "ability": {"desc": "Hits nearby enemies", "variables": []},
                        "squareIcon": "ASSETS/unit.tex",
                    }
                ],
                "traits": [
                    {
                        "apiName": "fixture-trait",
                        "name": "Fixture trait",
                        "desc": "Fixture trait description",
                        "effects": [{"minUnits": 2}],
                    }
                ],
            }
        ],
        "items": [],
    }
    ddragon = {
        "data": {
            "fixture-unit": {
                "id": "fixture-unit",
                "name": "Fixture translated",
                "tier": 2,
                "image": {"full": "fixture.png"},
            }
        }
    }
    result = DataStore(tmp_path / "snapshots").refresh(
        path,
        now=NOW,
        entity_adapters=[
            CommunityDragon(cdragon, 18, expected_unit_ids=("fixture-unit",)),
            DataDragon(ddragon, "test.1", "champion"),
        ],
    )
    assert result.snapshot.entities["fixture-unit"].name == "Fixture translated"
    assert result.snapshot.icons["fixture-unit"].endswith(
        "/img/tft-champion/fixture.png"
    )
    assert result.snapshot.entities["fixture-unit"].values["cost"].source == "ddragon"


def test_statistics_refresh_respects_age_and_falls_back_without_losing_game_snapshot(
    tmp_path,
):
    from datetime import timedelta

    from tft_data.sources import MemorySource

    path = patch_files(tmp_path / "patch")
    primary = MemorySource(
        "metatft",
        "statistics",
        "test.1",
        NOW,
        {"rows": [{"id": "fixture-unit", "kind": "unit", "avg": 4.2, "count": 900}]},
    )
    backup = MemorySource(
        "tactics.tools",
        "statistics",
        "test.1",
        NOW,
        {"rows": [{"id": "fixture-unit", "kind": "unit", "avg": 4.4, "count": 800}]},
    )
    store = DataStore(tmp_path / "snapshots")
    first = store.refresh(path, now=NOW, sources=[primary], fallback=backup).snapshot
    assert first.statistics[0].average_placement == 4.2
    primary.payload = {"broken": True}
    primary.updated_at = NOW + timedelta(minutes=30)
    young = store.refresh(
        path, now=NOW + timedelta(minutes=30), sources=[primary], fallback=backup
    )
    assert young.snapshot.snapshot_id == first.snapshot_id
    later = store.refresh(
        path, now=NOW + timedelta(hours=2), sources=[primary], fallback=backup
    )
    assert later.snapshot.statistics[0].source == "tactics.tools"
    assert first.statistics[0].average_placement == 4.2
    assert "stale since" in "\n".join(later.warnings)
    during = store.refresh(
        path, now=NOW + timedelta(hours=3), sources=[primary], in_game=True
    )
    assert during.deferred


def test_new_patch_thin_samples_retain_previous_patch_statistics(tmp_path):
    from datetime import timedelta

    from tft_data.sources import MemorySource

    path = patch_files(tmp_path / "patch")
    source = MemorySource(
        "metatft",
        "statistics",
        "test.1",
        NOW,
        {
            "rows": [
                {
                    "id": "fixture-unit",
                    "kind": "unit",
                    "avg": 4.2,
                    "count": 900,
                    "top4_rate": 0.6,
                }
            ]
        },
    )
    store = DataStore(tmp_path / "snapshots")
    old = store.refresh(path, now=NOW, sources=[source]).snapshot
    for name in ("static", "tunables"):
        p = path / f"{name}.toml"
        p.write_text(p.read_text().replace("test.1", "test.2"))
    source.patch = "test.2"
    source.updated_at = NOW + timedelta(hours=2)
    source.payload["rows"][0]["count"] = 30
    result = store.refresh(path, now=NOW + timedelta(hours=2), sources=[source])
    assert result.snapshot.statistics[0].patch == "test.1"
    assert result.snapshot.statistics[0].stale
    assert old.statistics[0].stale is False


def test_guides_normalize_names_and_owner_overrides_win(tmp_path):
    import tomli_w
    from tft_data.sources import MemorySource

    path = patch_files(tmp_path / "patch")
    source = MemorySource(
        "tftacademy",
        "guides",
        "test.1",
        NOW,
        {
            "guides": [
                {
                    "id": "fixture-guide",
                    "tier": "A",
                    "earlyComp": [],
                    "finalComp": [
                        {"apiName": "Fixture unit", "boardIndex": 25, "items": []}
                    ],
                    "mainChampion": {"apiName": "Fixture unit"},
                    "tips": [{"stage": "Stage 2", "tip": "Fixture stage tip"}],
                    "augments": [],
                    "carousel": [],
                    "altBuilds": [],
                }
            ]
        },
    )
    overrides = tmp_path / "overrides.toml"
    overrides.write_text(
        tomli_w.dumps(
            {
                "entities": {
                    "fixture-unit": {"threat_tags": ["aoe"]},
                    "missing-id": {"name": "obsolete"},
                },
                "guides": {"fixture-guide": {"tier": "S"}},
            }
        )
    )
    result = DataStore(tmp_path / "snapshots").refresh(
        path, now=NOW, sources=[source], overrides=overrides
    )
    assert result.snapshot.guides["fixture-guide"].positions["fixture-unit"] == 25
    assert result.snapshot.guides["fixture-guide"].tier == "S"
    assert result.snapshot.entities["fixture-unit"].threat_tags == ("aoe",)
    assert "missing-id" in "\n".join(result.warnings)


def test_new_patch_cli_carries_sources_and_marks_calendar_boundary(tmp_path):
    from tft_data.calendar import PatchCalendar
    from tft_data.cli import main

    patch_files(tmp_path / "test.1")
    assert (
        main(
            [
                "new-patch",
                "test.2",
                "--data-dir",
                str(tmp_path),
                "--from-patch",
                "test.1",
                "--live-at",
                "2026-10-10T10:00:00+03:00",
                "--offline",
            ]
        )
        == 0
    )
    result = DataStore(tmp_path / "snapshots").refresh(tmp_path / "test.2", now=NOW)
    assert result.snapshot.static["shop_odds"].source == "carried"
    calendar = PatchCalendar.load(tmp_path / "patches.toml")
    boundary = calendar.at(datetime(2026, 10, 10, 8, tzinfo=UTC))
    assert boundary.patch == "test.2"
    assert boundary.uncertain


def test_empty_economy_table_rejects_snapshot_and_preserves_last_good(tmp_path):
    import tomllib

    import tomli_w

    path = patch_files(tmp_path / "patch")
    store = DataStore(tmp_path / "snapshots")
    first = store.refresh(path, now=NOW).snapshot
    raw = tomllib.loads((path / "static.toml").read_text())
    raw["fields"]["shop_odds"]["value"] = {}
    (path / "static.toml").write_text(tomli_w.dumps(raw))
    result = store.refresh(path, now=NOW)
    assert result.snapshot.snapshot_id == first.snapshot_id
    assert "Invalid static shop_odds" in "\n".join(result.warnings)


def test_restart_keeps_last_good_immutable_snapshot_when_patch_files_disappear(
    tmp_path,
):
    path = patch_files(tmp_path / "patch")
    first = DataStore(tmp_path / "snapshots").refresh(path, now=NOW).snapshot
    (path / "static.toml").unlink()
    restarted = DataStore(tmp_path / "snapshots").refresh(path, now=NOW)
    assert restarted.snapshot.snapshot_id == first.snapshot_id
    assert restarted.snapshot.names["fixture-unit"] == "Fixture unit"


def test_tactics_checked_rows_expose_rates_and_map_trait_tier_to_breakpoint(tmp_path):
    import json

    from tft_data.sources import MemorySource

    path = patch_files(tmp_path / "patch")
    (path / "entities.json").write_text(
        json.dumps(
            {
                "entities": [
                    {
                        "id": "DA_Lux18_Blackthorn",
                        "kind": "unit",
                        "name": "Fixture unit",
                        "cost": 2,
                        "values": {"team_slot_cost": {"value": 1, "source": "default"}},
                    },
                    {
                        "id": "DA_18_Spellweaver",
                        "kind": "trait",
                        "name": "Fixture trait",
                        "values": {
                            "breakpoints": {"value": [2, 4, 6], "source": "cdragon"}
                        },
                    },
                ]
            }
        )
    )
    # Statistics excerpt read 2026-10-06, wrapped in an explicitly synthetic
    # publication for this adapter test. This is not the source's patch label.
    payload = {
        "patch": "test.1",
        "updated_at": NOW.isoformat(),
        "statsData": {
            "totalEntries": 4026162,
            "lastUpdated": 1791297861,
            "units": {
                "DA_Lux18_Blackthorn": {
                    "count": 81014,
                    "place": 3.37,
                    "top4": 70.19,
                    "starCount": 24,
                    "starPlace": 1,
                    "starTop4": 100,
                }
            },
            "traits": {
                "DA_18_Spellweaver__1": {"count": 1067956, "place": 4.4, "top4": 52.14}
            },
            "items": [],
        },
    }
    source = MemorySource("tactics.tools", "statistics", "test.1", NOW, payload)
    result = DataStore(tmp_path / "snapshots").refresh(path, now=NOW, sources=[source])
    unit = next(row for row in result.snapshot.statistics if row.kind == "unit")
    trait = next(row for row in result.snapshot.statistics if row.kind == "trait")
    assert unit.top4_rate == 0.7019
    assert unit.unit_star is None
    assert 0.02012 < unit.play_rate < 0.02013
    assert trait.breakpoint == 2


def test_refresh_recomputes_cost_line_defaults_without_inventing_guided_schedule(
    tmp_path,
):
    path = patch_files(tmp_path / "patch")
    result = DataStore(tmp_path / "snapshots").refresh(path, now=NOW)
    defaults = result.snapshot.tunable("default_lines_by_carry_cost")
    assert defaults["1"]["roll_level"] == 5
    assert defaults["5"]["roll_level"] == 9


def test_game_start_during_refresh_defers_publication_until_between_games(tmp_path):
    from tft_data.sources import MemorySource

    path = patch_files(tmp_path / "patch")
    store = DataStore(tmp_path / "snapshots")
    first = store.refresh(path, now=NOW).snapshot
    state = {"in_game": False}

    class GameStartingSource(MemorySource):
        def fetch(self):
            state["in_game"] = True
            return super().fetch()

    source = GameStartingSource(
        "metatft",
        "statistics",
        "test.1",
        NOW,
        {"rows": [{"id": "fixture-unit", "kind": "unit", "avg": 4.2, "count": 900}]},
    )
    result = store.refresh(
        path, now=NOW, sources=[source], can_publish=lambda: not state["in_game"]
    )
    assert result.deferred
    assert store.current.snapshot_id == first.snapshot_id
    state["in_game"] = False
    published = store.publish_pending(in_game=False)
    assert published.snapshot.statistics[0].average_placement == 4.2


def test_curated_augment_tiers_and_positioning_remain_distinct_from_statistics(
    tmp_path,
):
    from tft_data.sources import MemorySource

    path = patch_files(tmp_path / "patch")
    source = MemorySource(
        "metatft",
        "enrichment",
        "test.1",
        NOW,
        {
            "content": {
                "content": {
                    "tierList": [
                        {
                            "label": "S",
                            "content": [{"id": "fixture-augment", "type": "augment"}],
                        }
                    ]
                }
            },
            "positioning": {"fixture-unit": [1.0] + [0.0] * 27},
        },
    )
    result = DataStore(tmp_path / "snapshots").refresh(path, now=NOW, sources=[source])
    assert result.snapshot.augment_tiers["fixture-augment"] == "S"
    assert result.snapshot.positioning["fixture-unit"][0] == 1.0
    assert not result.snapshot.statistics


def test_refresh_cli_validates_offline_and_rejects_invalid_candidate_with_old_snapshot(
    tmp_path, capsys
):
    from tft_data.cli import main

    path = patch_files(tmp_path / "patch")
    snapshots = tmp_path / "snapshots"
    assert main(["refresh", str(path), "--snapshots", str(snapshots), "--offline"]) == 0
    (path / "static.toml").write_text('patch="test.1"')
    assert main(["validate", str(path), "--snapshots", str(snapshots)]) == 2
    assert "stale since" in capsys.readouterr().out


def test_shared_npcs_are_catalogued_without_entering_playable_unit_pool(tmp_path):
    from tft_data.adapters import CommunityDragon

    path = patch_files(tmp_path / "patch")
    payload = {
        "setData": [
            {
                "number": 18,
                "mutator": "TFTSet18",
                "champions": [
                    {
                        "apiName": "DA_18_Ornn",
                        "name": "Fixture Ornn",
                        "cost": 4,
                        "traits": [],
                    },
                    {
                        "apiName": "DA_18_Sivir",
                        "name": "Fixture Sivir",
                        "cost": 4,
                        "traits": [],
                    },
                    {
                        "apiName": "TFT_BlueGolem",
                        "name": "Shared Golem",
                        "cost": 1,
                        "traits": [],
                    },
                    {
                        "apiName": "TFT5_EmblemArmoryKey",
                        "name": "Tome of Traits",
                        "cost": 8,
                        "traits": [],
                    },
                    {
                        "apiName": "TFT6_MercenaryChest",
                        "name": "Mercenary Chest",
                        "cost": 11,
                        "traits": [],
                    },
                ],
                "traits": [],
            }
        ],
        "items": [],
    }
    result = DataStore(tmp_path / "snapshots").refresh(
        path, now=NOW, entity_adapters=[CommunityDragon(payload, 18)]
    )
    assert result.snapshot.entities["TFT_BlueGolem"].kind == "npc"
    assert result.snapshot.entities["DA_18_Ornn"].kind == "unit"
    assert result.snapshot.entities["TFT5_EmblemArmoryKey"].kind == "npc"
    assert result.snapshot.entities["TFT6_MercenaryChest"].kind == "npc"


def test_avatar_forms_share_base_pool_and_stay_out_of_independent_shop_choices(
    tmp_path,
):
    from tft_data.adapters import CommunityDragon

    path = patch_files(tmp_path / "patch")
    payload = {
        "setData": [
            {
                "number": 18,
                "mutator": "TFTSet18",
                "champions": [
                    {
                        "apiName": "DA_Lux18_Base",
                        "name": "Lux",
                        "cost": 5,
                        "traits": [],
                    },
                    {
                        "apiName": "DA_Lux18_Blackthorn",
                        "name": "Lux (Blackthorn)",
                        "cost": 5,
                        "traits": [],
                    },
                    {
                        "apiName": "DA_18_Lux_Coven",
                        "name": "Lux (Coven)",
                        "cost": 5,
                        "traits": [],
                    },
                ],
                "traits": [],
            }
        ],
        "items": [],
    }
    result = DataStore(tmp_path / "snapshots").refresh(
        path,
        now=NOW,
        entity_adapters=[
            CommunityDragon(payload, 18, expected_unit_ids=("DA_Lux18_Base",))
        ],
    )
    form = result.snapshot.entities["DA_Lux18_Blackthorn"]
    assert form.kind == "unit_form"
    assert form.values["pool_id"].value == "DA_Lux18_Base"
    legacy_form = result.snapshot.entities["DA_18_Lux_Coven"]
    assert legacy_form.kind == "unit_form"
    assert legacy_form.values["pool_id"].value == "DA_Lux18_Base"


def test_new_set_cli_archives_overrides_and_drops_set_specific_margin(tmp_path):
    import json
    import tomllib

    import tomli_w
    from tft_data.cli import main

    old = patch_files(tmp_path / "test.1")
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    static = tomllib.loads((old / "static.toml").read_text())
    static.update(patch="test.2", set_number=19)
    tunables = tomllib.loads((old / "tunables.toml").read_text())
    tunables["patch"] = "test.2"
    (fresh / "static.toml").write_text(tomli_w.dumps(static))
    (fresh / "tunables.toml").write_text(tomli_w.dumps(tunables))
    payload = {
        "setData": [
            {
                "number": 19,
                "mutator": "TFTSet19",
                "champions": [
                    {
                        "apiName": "fixture-unit",
                        "name": "Fixture unit",
                        "cost": 2,
                        "traits": [],
                    }
                ],
                "traits": [],
            }
        ],
        "items": [],
    }
    (fresh / "cdragon.json").write_text(json.dumps(payload))
    owner = tmp_path / "overrides.toml"
    original = '[entities.fixture-unit]\nname="Owner fixture"\n'
    owner.write_text(original)
    overlay=fresh/'capacity.json'
    overlay.write_text(json.dumps({'schema_version':1,'patch':'test.2','set_number':19,
        'entities':{'fixture-unit':{'values':{'team_slot_cost':{'value':1,'source':'owner',
            'citation':'Declared synthetic ordinary-unit rule; not patch evidence'}}}}}))
    uncertified=['new-set','test.2','--from-patch','test.1','--data-dir',str(tmp_path),
        '--static-file',str(fresh/'static.toml'),'--tunables-file',str(fresh/'tunables.toml'),
        '--cdragon-file',str(fresh/'cdragon.json'),'--live-at','2026-10-10T10:00:00+03:00',
        '--overrides',str(owner)]
    assert main(uncertified)==2
    assert owner.read_text()==original
    assert not (tmp_path/'overrides-set18.toml').exists()
    assert not (tmp_path/'test.2').exists()
    assert not (tmp_path/'patches.toml').exists()
    assert (
        main(
            [
                "new-set",
                "test.2",
                "--from-patch",
                "test.1",
                "--data-dir",
                str(tmp_path),
                "--static-file",
                str(fresh / "static.toml"),
                "--tunables-file",
                str(fresh / "tunables.toml"),
                "--cdragon-file",
                str(fresh / "cdragon.json"),
                "--live-at",
                "2026-10-10T10:00:00+03:00",
                "--overrides",
                str(owner),
                "--entity-overlay-file",str(overlay),
            ]
        )
        == 0
    )
    assert (tmp_path / "overrides-set18.toml").read_text() == original
    loaded = DataStore(tmp_path / "snapshots").refresh(tmp_path / "test.2", now=NOW)
    assert "wisp_buy_margin" not in loaded.snapshot.tunables
    assert loaded.snapshot.tunables["unit_weight"].value == 1


def test_unqualified_fallback_cannot_replace_qualified_statistics(
    tmp_path, monkeypatch
):
    from datetime import timedelta
    from packages.data.tests.test_sources import external_responses, DONOR_URL
    from tft_data.sources import HTTPSource, MemorySource

    primary = MemorySource(
        "metatft",
        "statistics",
        "test.1",
        NOW,
        {"rows": [{"id": "fixture-unit", "kind": "unit", "avg": 4.2, "count": 900}]},
    )
    backup = HTTPSource(
        "backup",
        "statistics",
        DONOR_URL,
        provider="metatft",
        required_cohort={"minimum_rank": "DIAMOND", "regions": "all"},
    )
    external_responses(
        monkeypatch,
        {
            DONOR_URL: {
                "patch": "test.1",
                "updated": 1791641438134,
                "rows": [
                    {"id": "fixture-unit", "kind": "unit", "avg": 1.1, "count": 900}
                ],
            }
        },
    )
    root = tmp_path / "snapshots"
    store = DataStore(root)
    path = patch_files(tmp_path / "patch")
    original = store.refresh(path, now=NOW, sources=[primary]).snapshot
    primary.payload = {"broken": True}
    primary.updated_at = NOW + timedelta(hours=2)

    result = store.refresh(
        path, now=NOW + timedelta(hours=2), sources=[primary], fallback=backup
    )

    assert result.snapshot.statistics[0].average_placement == 4.2
    assert result.snapshot.statistics[0].stale
    assert not result.snapshot.sources["backup"].qualified
    assert "fallback unavailable" in "\n".join(result.warnings)
    assert "regions" in "\n".join(result.warnings)
    assert (
        DataStore(root).get(result.snapshot.snapshot_id).sources["backup"]
        == result.snapshot.sources["backup"]
    )
    assert not original.statistics[0].stale


def test_new_cohort_requirements_do_not_grandfather_unconfirmed_cached_rows(
    tmp_path, monkeypatch
):
    from datetime import timedelta
    from packages.data.tests.test_sources import external_responses, DONOR_URL
    from tft_data.sources import HTTPSource

    body = {
        "patch": "test.1",
        "updated": 1791641438134,
        "rows": [{"id": "fixture-unit", "kind": "unit", "avg": 4.2, "count": 900}],
    }
    external_responses(monkeypatch, {DONOR_URL: body})
    root = tmp_path / "snapshots"
    path = patch_files(tmp_path / "patch")
    now = datetime(2026, 10, 10, 16, tzinfo=UTC)
    original = (
        DataStore(root)
        .refresh(
            path,
            now=now,
            sources=[HTTPSource("units", "statistics", DONOR_URL, provider="metatft")],
        )
        .snapshot
    )
    assert original.statistics[0].average_placement == 4.2
    strict = HTTPSource(
        "units",
        "statistics",
        DONOR_URL,
        provider="metatft",
        required_cohort={"minimum_rank": "DIAMOND", "regions": "all"},
    )

    result = DataStore(root).refresh(
        path, now=now + timedelta(hours=2), sources=[strict]
    )

    assert not result.snapshot.statistics
    assert not result.snapshot.sources["units"].qualified
    assert original.statistics[0].average_placement == 4.2
    assert DataStore(root).get(original.snapshot_id) == original


def test_fallback_preserves_its_own_one_hour_refresh_age(tmp_path):
    from datetime import timedelta
    from tft_data.sources import MemorySource

    primary = MemorySource("metatft", "statistics", "test.1", NOW, {"broken": True})
    backup = MemorySource(
        "tactics.tools",
        "statistics",
        "test.1",
        NOW,
        {"rows": [{"id": "fixture-unit", "kind": "unit", "avg": 4.4, "count": 800}]},
    )
    store = DataStore(tmp_path / "snapshots")
    path = patch_files(tmp_path / "patch")
    first = store.refresh(path, now=NOW, sources=[primary], fallback=backup).snapshot
    backup.updated_at = NOW + timedelta(minutes=30)
    backup.payload["rows"][0]["avg"] = 4.1

    young = store.refresh(
        path, now=NOW + timedelta(minutes=30), sources=[primary], fallback=backup
    ).snapshot
    assert young.statistics[0].average_placement == 4.4
    assert (
        young.sources["tactics.tools"].fetched_at
        == first.sources["tactics.tools"].fetched_at
    )
    later = store.refresh(
        path, now=NOW + timedelta(hours=2), sources=[primary], fallback=backup
    ).snapshot
    assert later.statistics[0].average_placement == 4.1
    assert later.sources["tactics.tools"].updated_at == NOW + timedelta(minutes=30)


def test_refresh_cli_reports_unqualified_own_payload_without_publishing_tiers(
    tmp_path, monkeypatch, capsys
):
    from packages.data.tests.test_sources import (
        external_responses,
        TIERS_URL,
        DONOR_URL,
    )
    from tft_data.cli import main

    responses = {
        TIERS_URL: {
            "updated": 1791641438134,
            "tft_set": "TFTSet18",
            "queue_id": 1100,
            "global_augment_tiers": {"fixture-augment": "S"},
        },
        DONOR_URL: {"patch": "test.1", "updated": 1791641414471},
    }
    external_responses(monkeypatch, responses)
    path = patch_files(tmp_path / "patch")
    root = tmp_path / "snapshots"
    manifest = tmp_path / "sources.toml"
    manifest.write_text("""schema_version=1
[statistics]
minimum_rank="DIAMOND"
regions="all"
[refresh]
sources=["tiers"]
[sources.tiers]
provider="metatft"
kind="enrichment"
url="https://example.invalid/augments_tiers"
metadata_url="https://example.invalid/unit_items_processed"
""")

    assert (
        main(
            ["refresh", str(path), "--snapshots", str(root), "--sources", str(manifest)]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "Confirmed patch identity unavailable" in output
    assert "unavailable" in output
    saved = DataStore(root).current
    assert not saved.augment_tiers
    assert saved.sources["tiers"].patch is None
    assert saved.sources["tiers"].donor_hint["patch"] == "test.1"
    assert main(["refresh", str(path), "--snapshots", str(root), "--offline"]) == 0
    reloaded_output = capsys.readouterr().out
    assert "Confirmed patch identity unavailable" in reloaded_output


def test_rejected_payload_records_latest_owned_publication_without_relabeling_last_good(
    tmp_path, monkeypatch
):
    from datetime import timedelta
    from packages.data.tests.test_sources import external_responses, DONOR_URL
    from tft_data.sources import HTTPSource

    body = {
        "patch": "test.1",
        "updated": 1791641438134,
        "rows": [{"id": "fixture-unit", "kind": "unit", "avg": 4.2, "count": 900}],
    }
    responses = {DONOR_URL: body}
    external_responses(monkeypatch, responses)
    root = tmp_path / "snapshots"
    path = patch_files(tmp_path / "patch")
    store = DataStore(root)
    source = HTTPSource("units", "statistics", DONOR_URL, provider="metatft")
    now = datetime(2026, 10, 10, 16, tzinfo=UTC)
    first = store.refresh(path, now=now, sources=[source]).snapshot
    responses[DONOR_URL] = {
        **body,
        "updated": 1791645038134,
        "rows": [{"broken": True}],
    }

    rejected = store.refresh(
        path, now=now + timedelta(hours=2), sources=[source]
    ).snapshot

    assert rejected.statistics[0].average_placement == 4.2
    assert rejected.sources["units"].updated_at == first.sources["units"].updated_at
    assert (
        rejected.sources["units"].last_attempt["updated_at"]
        == "2026-10-10T15:10:38.134000+00:00"
    )
    assert rejected.sources["units"].last_attempt["qualified"] is False
    assert rejected.sources["units"].last_attempt["error"]
    assert (
        DataStore(root).get(rejected.snapshot_id).sources["units"]
        == rejected.sources["units"]
    )


def test_thin_qualified_update_cannot_resurrect_an_unqualified_cohort_prior(
    tmp_path, monkeypatch
):
    from datetime import timedelta
    from packages.data.tests.test_sources import external_responses, DONOR_URL
    from tft_data.sources import HTTPSource

    body = {
        "patch": "test.1",
        "updated": 1791641438134,
        "rows": [{"id": "fixture-unit", "kind": "unit", "avg": 4.2, "count": 900}],
    }
    responses = {DONOR_URL: body}
    external_responses(monkeypatch, responses)
    root = tmp_path / "snapshots"
    path = patch_files(tmp_path / "patch")
    now = datetime(2026, 10, 10, 16, tzinfo=UTC)
    original = (
        DataStore(root)
        .refresh(
            path,
            now=now,
            sources=[HTTPSource("units", "statistics", DONOR_URL, provider="metatft")],
        )
        .snapshot
    )
    responses[DONOR_URL] = {
        **body,
        "updated": 1791645038134,
        "filters": {"minimum_rank": "DIAMOND", "regions": "all"},
        "rows": [{"id": "fixture-unit", "kind": "unit", "avg": 3.1, "count": 30}],
    }
    strict = HTTPSource(
        "units",
        "statistics",
        DONOR_URL,
        provider="metatft",
        required_cohort={"minimum_rank": "DIAMOND", "regions": "all"},
    )

    result = DataStore(root).refresh(
        path, now=now + timedelta(hours=2), sources=[strict]
    )

    assert result.snapshot.sources["units"].qualified
    assert not result.snapshot.statistics
    assert original.statistics[0].average_placement == 4.2


@pytest.mark.parametrize('order',(-1,3,True))
def test_invalid_provider_pick_stage_is_unavailable_and_never_installed(tmp_path,order):
    from tft_data.sources import MemorySource
    path=patch_files(tmp_path/'patch')
    source=MemorySource('metatft','statistics','test.1',NOW,{'rows':[
        {'id':'augment','kind':'augment','avg':4,'count':1000,'order':order}]})
    report=DataStore(tmp_path/'snapshots').refresh(path,sources=(source,),now=NOW)
    assert not report.snapshot.statistics
    assert report.snapshot.sources['metatft'].qualified is False
    assert any('order' in reason.lower() for reason in report.snapshot.sources['metatft'].qualification_reasons)
    assert any('order' in warning.lower() for warning in report.warnings)


@pytest.mark.parametrize('effect',(
    {'effect_kind':'risky','values':{'outcomes':[{'probability':1,'effect':{'effect_kind':'gold','values':{'gold':4}}}]}},
    {'effect_kind':'sale_modifier','values':{'duration_rounds':1,'sale_gold_by_cost_star':{'1':{'1':1}}}},
))
def test_supported_conditional_and_sale_effects_publish_as_immutable_patch_data(tmp_path,effect):
    import tomllib
    import tomli_w
    path=patch_files(tmp_path/'patch')
    static=tomllib.loads((path/'static.toml').read_text())
    static['fields']['wisps']['value']={'fixture':dict(effect,cost=1,offer_stages=['3'])}
    (path/'static.toml').write_text(tomli_w.dumps(static))
    result=DataStore(tmp_path/'snapshots').refresh(path,sources=(),now=NOW)
    assert result.snapshot.value('wisps')['fixture']['effect_kind']==effect['effect_kind']
    with pytest.raises(TypeError):
        result.snapshot.value('wisps')['fixture']['values']['invented']=0


def test_refresh_refuses_uncertified_team_slot_cost_and_keeps_previous_snapshot(tmp_path):
    import json
    path=patch_files(tmp_path/'capacity-patch')
    store=DataStore(tmp_path/'capacity-store')
    first=store.refresh(path,now=NOW)
    payload=json.loads((path/'entities.json').read_text())
    payload['entities'][0]['values'].pop('team_slot_cost')
    (path/'entities.json').write_text(json.dumps(payload))
    failed=store.refresh(path,now=NOW)
    assert failed.snapshot.snapshot_id==first.snapshot.snapshot_id
    assert any('team slot cost unavailable' in text for text in failed.warnings)
