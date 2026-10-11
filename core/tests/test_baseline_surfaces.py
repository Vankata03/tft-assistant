import asyncio
import json

from websockets.asyncio.client import connect

from tft_core.messages import Hello, dump
from tft_core.server import CoreServer


def test_authenticated_surface_request_in_silent_mode_contains_status_only():
    async def scenario():
        server = CoreServer("surface-token")
        async with server.listen() as listening:
            port = listening.sockets[0].getsockname()[1]
            async with connect(f"ws://127.0.0.1:{port}") as ws:
                await ws.send(dump(Hello(token="surface-token")))
                await ws.recv()
                await ws.recv()
                await ws.send(json.dumps({"v": 1, "type": "request_baseline_state"}))
                state = json.loads(await ws.recv())
                assert state["type"] == "baseline_state"
                assert state["mode"] == "silent"
                assert state["content"] is None
                assert state["voice"] is None
                assert "unavailable" in state["status"].lower()

    asyncio.run(scenario())


def fixture_data():
    from tft_data import DataSnapshot, Entity, Guide, TaggedValue

    values = {
        "xp_table": {"6": 12},
        "rules_flags": {"passive_xp": 2, "xp_buy_amount": 4, "xp_buy_cost": 4},
        "round_order": ["3-2", "3-3", "3-4"],
        "round_types": {"3-2": "combat", "3-3": "combat", "3-4": "combat"},
        "item_recipes": {"finished": ["component-a", "component-b"]},
        "wisps": {"wisp": {"worth": 3.5}},
    }
    entities = {
        "carry": Entity("carry", "unit", "Fixture carry", 3),
        "component-a": Entity("component-a", "item", "Fixture sword"),
        "component-b": Entity("component-b", "item", "Fixture bow"),
        "finished": Entity("finished", "item", "Fixture blade"),
        "augment": Entity("augment", "augment", "Fixture augment"),
        "wisp": Entity("wisp", "wisp", "Fixture Wisp"),
    }
    guide = Guide(
        "guide-a",
        "S",
        ("carry",),
        ("carry",),
        ("carry",),
        {"carry": ("finished",)},
        {"carry": 7},
        {"3": "Fixture stage plan"},
        {"augment": "Guide"},
        ("component-a",),
        line=({"round": "3-4", "level": 7},),
    )
    return DataSnapshot(
        "fixture-snapshot",
        "fixture-patch",
        18,
        {k: TaggedValue(v, "default") for k, v in values.items()},
        {},
        entities=entities,
        guides={guide.id: guide},
        augment_tiers={"augment": "A"},
    )


def test_guide_selection_renders_static_content_and_passive_xp_without_opponent_state():
    from datetime import UTC, datetime

    from tft_core.baseline import BaselineController
    from tft_core.messages import SessionMode

    now = datetime(2026, 10, 7, tzinfo=UTC)
    controller = BaselineController()
    controller.update(
        data=fixture_data(),
        snapshot={
            "game_id": "fixture-game",
            "round_id": "3-2",
            "phase": "planning",
            "captured_at": now.isoformat(),
            "fields": {
                "level": {"value": 6, "read_at": now.isoformat()},
                "xp": {"value": 0, "read_at": now.isoformat()},
                "components": {"value": ["component-a"], "read_at": now.isoformat()},
                "shop": {
                    "value": [{"unit_id": "carry", "slot": 2}],
                    "read_at": now.isoformat(),
                },
            },
        },
        now=now,
        round_start=True,
    )
    controller.select("guide-a")
    view = controller.state(SessionMode.BASELINE, now=now)
    assert view.content.selected.final_layout[0].position == 7
    assert view.content.selected.early_layout[0].position is None
    assert view.content.xp_hint.buys == 2
    assert view.content.xp_hint.gold == 8
    assert view.content.xp_hint.passive_xp == 4
    assert view.content.shop[0].slot == 2
    assert view.content.shop[0].in_guide
    assert view.content.recipes[0].components[0].held
    assert view.content.augments[0].tier == "A"
    assert view.content.augments[0].in_guide
    assert view.content.wisps[0].worth == 3.5
    assert view.voice.text == "Fixture stage plan"
    assert controller.state(SessionMode.BASELINE, now=now).voice is None
    assert controller.state(SessionMode.SILENT, now=now).content is None


def test_par_chip_uses_complete_own_board_and_static_growth_and_pauses_stale_reads():
    from dataclasses import replace
    from datetime import UTC, datetime, timedelta

    import pytest
    from tft_data import TaggedValue

    from tft_core.baseline import BaselineController

    now = datetime(2026, 10, 7, tzinfo=UTC)
    data = replace(
        fixture_data(),
        tunables={
            k: TaggedValue(v, "owner")
            for k, v in {
                "cost_star_baseline": {"3": {"1": 1}},
                "confidence_medium_min": 0.5,
                "unit_weight": 1,
                "trait_weight": 1,
                "item_weight": 1,
                "item_values": {
                    "finished": 1,
                    "component": 0.35,
                    "high_cost_bonus": 0.25,
                },
                "opponent_growth_curve": {"3-2": 0},
                "fight_scale": 1,
                "win_scale_by_stage": {},
            }.items()
        },
    )
    snapshot = {
        "game_id": "own-game",
        "round_id": "3-2",
        "fields": {
            "level": {"value": 6, "read_at": now.isoformat(), "confidence": 1},
            "board": {
                "value": {"units": [{"unit_id": "carry", "stars": 1, "items": []}]},
                "read_at": now.isoformat(),
                "confidence": 1,
            },
            "inventory_complete": {"value": True, "read_at": now.isoformat()},
            "opponent_sightings": {
                "value": [{"secret-opponent": "secret-traits"}],
                "read_at": now.isoformat(),
            },
        },
    }
    controller = BaselineController()
    controller.update(data=data, snapshot=snapshot)
    state = controller.state("baseline", now=now)
    assert state.content.par.probability == pytest.approx(0.7310585786)
    assert "secret" not in state.model_dump_json()
    assert (
        controller.state(
            "baseline", now=now + timedelta(seconds=3)
        ).content.par.probability
        is None
    )
    assert controller.state("silent", now=now + timedelta(seconds=3)).stale
    assert controller.state("live", now=now).content is None


def test_authenticated_guide_requests_and_downgrade_clear_all_game_content(tmp_path):
    from tft_core.messages import SessionMode
    from tft_core.storage import SessionStore

    async def scenario():
        sessions = SessionStore(
            tmp_path / "app", tmp_path / "config", live_installed=False
        )
        server = CoreServer("surface-token", sessions=sessions)
        server.publish_baseline(data=fixture_data())
        async with server.listen() as listening:
            port = listening.sockets[0].getsockname()[1]
            async with connect(f"ws://127.0.0.1:{port}") as ws:
                await ws.send(dump(Hello(token="surface-token")))
                await ws.recv()
                await ws.recv()
                await ws.send(json.dumps({"v": 1, "type": "request_baseline_state"}))
                state = json.loads(await ws.recv())
                assert state["content"]["guides"][0]["id"] == "guide-a"
                await ws.send(
                    json.dumps({"v": 1, "type": "select_guide", "guide_id": "guide-a"})
                )
                state = json.loads(await ws.recv())
                assert state["content"]["selected"]["id"] == "guide-a"
                await ws.send(
                    json.dumps({"v": 1, "type": "set_session_mode", "mode": "silent"})
                )
                assert json.loads(await ws.recv())["mode"] == "silent"
                state = json.loads(await ws.recv())
                assert state["content"] is None
                assert state["voice"] is None
                assert "guide-a" not in json.dumps(state)
                await ws.send(
                    json.dumps({"v": 1, "type": "select_guide", "guide_id": "guide-a"})
                )
                assert (
                    json.loads(await ws.recv())["code"] == "baseline_request_rejected"
                )
                assert server.mode == SessionMode.SILENT

    asyncio.run(scenario())


def test_static_wisp_offer_and_calibrated_anchors_remain_display_only():
    from datetime import UTC, datetime

    from tft_core.baseline import BaselineController

    now = datetime(2026, 10, 10, tzinfo=UTC)
    controller = BaselineController()
    controller.update(
        data=fixture_data(),
        snapshot={
            "game_id": "fixture",
            "round_id": "3-2",
            "fields": {
                "wisp": {
                    "value": {"wisp_id": "wisp", "slot": 4},
                    "read_at": now.isoformat(),
                }
            },
        },
        anchors=[
            {
                "kind": "wisp",
                "index": 4,
                "x": 0.8,
                "y": 0.9,
                "width": 0.15,
                "height": 0.05,
            }
        ],
        overlay_bounds={"x": 0, "y": 0, "width": 1280, "height": 720},
        overlay_allowed=True,
    )
    state = controller.state("baseline", now=now)
    assert state.content.wisps[0].offered_slot == 4
    assert state.content.anchors[0].x == 0.8
    assert state.content.overlay_allowed
    assert controller.state("silent", now=now).content is None


def test_surface_display_events_are_logged_only_in_coached_modes(tmp_path):
    from tft_core.storage import SessionStore

    async def scenario():
        sessions = SessionStore(
            tmp_path / "app", tmp_path / "config", live_installed=False
        )
        sessions.start_game("12345")
        server = CoreServer("surface-token", sessions=sessions)
        async with (
            server.listen() as listening,
            connect(f"ws://127.0.0.1:{listening.sockets[0].getsockname()[1]}") as ws,
        ):
            await ws.send(dump(Hello(token="surface-token")))
            await ws.recv()
            await ws.recv()
            await ws.send(
                json.dumps(
                    {
                        "v": 1,
                        "type": "surface_shown",
                        "surface": "cockpit",
                        "content_id": "guide:guide-a",
                        "timestamp": "2026-10-10T00:00:00Z",
                    }
                )
            )
            await ws.send(json.dumps({"v": 1, "type": "request_baseline_state"}))
            await ws.recv()
            events = sessions.read_events("12345")
            assert events[-1]["kind"] == "ui_show"
            assert events[-1]["payload"]["content_id"] == "guide:guide-a"
            await ws.send(
                json.dumps({"v": 1, "type": "set_session_mode", "mode": "silent"})
            )
            await ws.recv()
            await ws.recv()
            await ws.send(
                json.dumps(
                    {
                        "v": 1,
                        "type": "surface_shown",
                        "surface": "voice",
                        "content_id": "secret",
                        "timestamp": "2026-10-10T00:00:00Z",
                    }
                )
            )
            assert json.loads(await ws.recv())["code"] == "surface_suppressed"
            assert sessions.read_events("12345")[-1]["kind"] == "mode_change"

    asyncio.run(scenario())


def test_interim_layout_uses_only_explicit_positions():
    from dataclasses import replace

    from tft_core.baseline import BaselineController

    data = fixture_data()
    guide = replace(data.guides["guide-a"], early_positions={"carry": 15})
    controller = BaselineController()
    controller.update(data=replace(data, guides={"guide-a": guide}))
    controller.select("guide-a")
    assert controller.state("baseline").content.selected.early_layout[0].position == 15


def test_global_tiers_are_available_before_a_guide_is_selected():
    from tft_core.baseline import BaselineController

    controller = BaselineController()
    controller.update(data=fixture_data())
    state = controller.state("baseline")
    assert state.content.selected is None
    assert state.content.augments[0].tier == "A"
    assert not state.content.augments[0].in_guide


def test_shop_membership_uses_checked_unit_form_identity():
    from dataclasses import replace
    from datetime import UTC, datetime

    from tft_data import Entity, TaggedValue

    from tft_core.baseline import BaselineController

    data = fixture_data()
    form = Entity(
        "carry-form",
        "unit_form",
        "Fixture carry form",
        values={"canonical_id": TaggedValue("carry", "cdragon")},
    )
    guide = replace(
        data.guides["guide-a"],
        units=("carry-form",),
        early_units=(),
        positions={"carry-form": 7},
    )
    now = datetime(2026, 10, 10, tzinfo=UTC)
    controller = BaselineController()
    controller.update(
        data=replace(
            data, entities={**data.entities, form.id: form}, guides={guide.id: guide}
        ),
        snapshot={
            "fields": {
                "shop": {
                    "value": [{"slot": 0, "unit_id": "carry"}],
                    "read_at": now.isoformat(),
                }
            }
        },
    )
    controller.select(guide.id)
    assert controller.state("baseline", now=now).content.shop[0].in_guide


def test_baseline_reads_only_current_stage_wisp_reference_and_preserves_unavailable_rows():
    from dataclasses import replace
    from datetime import UTC, datetime
    from tft_data import TaggedValue
    from tft_core.baseline import BaselineController

    now=datetime(2026,10,12,tzinfo=UTC)
    data=fixture_data()
    table={'wisp':{'3':{'label':'situational','placement_gain':.12,'paired_standard_error':.03,'source':'engine_standard_state'}}}
    data=replace(data,static=dict(data.static)|{'wisp_worth_table':TaggedValue(table,'owner','synthetic standard states')})
    controller=BaselineController()
    controller.update(data=data,snapshot={'round_id':'3-2','phase':'planning','fields':{}},now=now)
    row=controller.state('baseline',now=now).content.wisps[0]
    assert row.worth_label=='situational' and row.worth_stage=='3'
    assert row.worth==.12 and row.paired_standard_error==.03 and row.source=='owner'
    controller.update(data=data,snapshot={'round_id':'4-2','phase':'planning','fields':{}},now=now)
    missing=controller.state('baseline',now=now).content.wisps[0]
    assert missing.worth is None and missing.worth_label is None
    assert missing.worth_stage=='4' and missing.paired_standard_error is None
    assert controller.state('silent',now=now).content is None
