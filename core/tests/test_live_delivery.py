"""Live delivery through the actual Engine and the approved display boundary."""

import json
from pathlib import Path
import runpy
import pytest


def test_live_delivery_keeps_engine_order_and_resolves_complete_line_evidence():
    from tft_live.advisor import LiveAdvisor
    from tft_engine import GameHistory, evaluate

    fixtures = runpy.run_path(str(Path(__file__).parents[1] /
                                 "packages/engine/tests/test_planning.py"))
    patch, snapshot = fixtures["patch"], fixtures["snapshot"]
    data, state, history = patch(), snapshot(), GameHistory()
    original = evaluate(state, history, data, "live")
    delivery = LiveAdvisor().evaluate(state, history, data, mode="live")

    assert [row["decision_id"] for row in delivery.content["advice"]] == [
        row.decision_id for row in original.advice
    ]
    assert [row["action"] for row in delivery.content["advice"]] == [
        row.action for row in original.advice
    ]
    encoded = json.dumps(delivery.content, allow_nan=False).encode()
    assert b"rollout_placements" not in encoded
    assert b"before_lines" not in encoded
    assert len(encoded) < 256 * 1024
    evidence = delivery.evidence.resolve()
    assert evidence["advice"] == [row.to_dict() for row in original.advice]
    assert evidence["line_results"] == {
        comp: [row.to_dict() for row in lines]
        for comp, lines in original.line_results.items()
    }
    assert delivery.content["game_id"] == state.game_id
    assert delivery.content["snapshot_id"] == state.snapshot_id
    assert delivery.content["data_snapshot_id"] == data.snapshot_id
    assert delivery.content["plan"] == original.plan.to_dict()
    assert len(delivery.content["lines"]) == len(original.line_results[original.plan.target])
    for row, advice in zip(delivery.content["advice"], original.advice):
        assert row["payload"].get("paused") == advice.payload.get("paused")
        assert row["validity"] == list(advice.validity)


def test_live_advisor_suppresses_other_modes_and_reports_missing_data():
    from tft_live.advisor import LiveAdvisor
    from tft_engine import GameHistory

    fixtures = runpy.run_path(str(Path(__file__).parents[1] /
                                 "packages/engine/tests/test_planning.py"))
    state = fixtures["snapshot"]()
    advisor = LiveAdvisor()
    assert advisor.evaluate(state, GameHistory(), None, mode="silent") is None
    assert advisor.evaluate(state, GameHistory(), None, mode="baseline") is None
    delivery = advisor.evaluate(state, GameHistory(), None, mode="live")
    assert delivery.content["data_snapshot_id"] is None
    assert delivery.content["advice"][0]["payload"]["paused"] is True
    assert delivery.content["lines"] == []


def test_socket_delivery_details_shown_membership_and_downgrade(tmp_path):
    import asyncio
    from dataclasses import replace
    from datetime import UTC, datetime
    from websockets.asyncio.client import connect
    from tft_core.messages import Hello, dump
    from tft_core.server import CoreServer
    from tft_core.storage import SessionStore
    from tft_engine import GameHistory
    from tft_live.advisor import LiveAdvisor

    async def scenario():
        fixture = runpy.run_path(str(Path(__file__).parents[1] /
                                    "packages/engine/tests/test_planning.py"))
        now = datetime.now(UTC)
        initial = fixture["snapshot"]()
        snapshot = replace(initial, game_id="123", captured_at=now,
                           fields={name: replace(field, read_at=now) for name, field in initial.fields.items()})
        sessions = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
        sessions.set_mode("live")
        sessions.start_game("123", data_snapshot_id=fixture["patch"]().snapshot_id)
        server = CoreServer("token", sessions=sessions)
        delivery = LiveAdvisor().evaluate(snapshot, GameHistory(), fixture["patch"](), mode="live")
        server.publish_live(delivery)
        async with server.listen() as listening:
            async with connect(f"ws://127.0.0.1:{listening.sockets[0].getsockname()[1]}") as ws:
                await ws.send(dump(Hello(token="token")))
                await ws.recv(); await ws.recv()
                await ws.send(json.dumps({"v": 1, "type": "request_live_state"}))
                state = json.loads(await ws.recv())
                assert state["content"]["advice"][0]["action"] == delivery.content["advice"][0]["action"]
                revision = state["revision"]
                request = {"v": 1, "type": "request_evidence_page", "request_id": "r1",
                           "game_id": "123", "revision": revision,
                           "path": ["advice", 0, "options"], "cursor": 0, "limit": 2}
                await ws.send(json.dumps(request))
                page = json.loads(await ws.recv())
                assert page["type"] == "evidence_page"
                assert page["page"]["total"] == len(delivery.evidence.resolve(path=("advice", 0, "options")))
                assert len(json.dumps(page).encode()) < 65536
                await ws.send(json.dumps(request | {"path": ["line_results", "A", 0, "seed"]}))
                seed_page = json.loads(await ws.recv())["page"]
                original_seed = delivery.evidence.resolve(path=("line_results", "A", 0, "seed"))
                assert original_seed > 2**53 - 1
                assert seed_page["items"][0]["value"] == str(original_seed)
                assert seed_page["integer_paths"] == [["items", 0, "value"]]
                shown = {"v": 1, "type": "live_surface_shown", "game_id": "123",
                         "revision": revision, "decision_id": delivery.content["advice"][0]["decision_id"],
                         "option_id": delivery.content["advice"][0]["option_id"],
                         "surface": "cockpit", "timestamp": datetime.now(UTC).isoformat()}
                await ws.send(json.dumps(shown))
                await ws.send(json.dumps(shown))
                await ws.send(json.dumps(request))  # response confirms the preceding acknowledgement was consumed.
                await ws.recv()
                actual = [e for e in sessions.read_events("123") if e["kind"] == "ui_show"]
                assert len(actual) == 1
                assert actual[0]["payload"]["decision_id"] == shown["decision_id"]
                assert actual[0]["payload"]["delivery_revision"] == revision
                line = state["content"]["lines"][0]
                pin = {"v": 1, "type": "pin_line", "game_id": "123", "revision": revision,
                       "comp_id": line["comp_id"], "line_id": line["line_id"], "seed": line["seed"]}
                await ws.send(json.dumps(pin))
                assert json.loads(await ws.recv())["pin"]["line_id"] == line["line_id"]
                await ws.send(json.dumps(pin | {"line_id": "invented schedule"}))
                assert json.loads(await ws.recv())["code"] == "live_request_rejected"
                await ws.send(json.dumps(pin | {"schedule": {"rolls": {"3-2": 0}}}))
                assert json.loads(await ws.recv())["code"] == "invalid_message"
                assert len([e for e in sessions.read_events("123") if e["kind"] == "line_pin"]) == 1
                pin_event = next(e for e in sessions.read_events("123") if e["kind"] == "line_pin")
                assert server.live.pin_read_at == datetime.fromisoformat(pin_event["timestamp"])
                assert pin_event["payload"]["data_snapshot_id"] == delivery.content["data_snapshot_id"]
                assert server.live.pin_context["game_id"] == "123"
                assert server.live.pin_context["delivery_revision"] == revision
                await ws.send(json.dumps(shown | {"decision_id": "invented"}))
                assert json.loads(await ws.recv())["code"] == "live_request_rejected"
                from tft_engine import FieldValue
                changed_at = datetime.now(UTC)
                changed = replace(snapshot, captured_at=changed_at, fields=dict(snapshot.fields) | {
                    "gold": FieldValue(snapshot.fields["gold"].value + 1, changed_at, "fixture", 1)})
                server.observe_live_capture(changed, fixture["patch"]())
                invalidated = json.loads(await ws.recv())
                assert "gold changed" in invalidated["invalidated"][shown["decision_id"]]
                await ws.send(json.dumps(shown | {"surface": "overlay", "timestamp": datetime.now(UTC).isoformat()}))
                assert json.loads(await ws.recv())["code"] == "live_request_rejected"
                assert len([e for e in sessions.read_events("123") if e["kind"] == "ui_show"]) == 1
                await ws.send(json.dumps({"v": 1, "type": "set_session_mode", "mode": "silent"}))
                assert json.loads(await ws.recv())["mode"] == "silent"
                cleared = json.loads(await ws.recv())
                assert cleared["type"] == "live_state" and cleared["content"] is None
                assert server.live.pin_read_at is None and server.live.pin_context is None
                await ws.send(json.dumps(request))
                assert json.loads(await ws.recv())["code"] == "live_request_rejected"
        stored = next(e for e in sessions.read_events("123") if e["kind"] == "advice_delivery")
        assert sessions.read_evidence("123", stored["payload"]["evidence_id"]).resolve() == delivery.evidence.resolve()

    asyncio.run(scenario())


def test_socket_burst_coalesces_unsent_states_for_a_slow_surface():
    import asyncio
    from websockets.asyncio.client import connect
    from tft_core.messages import Hello, dump
    from tft_core.server import CoreServer

    async def scenario():
        server = CoreServer("token")
        async with server.listen() as listening:
            async with connect(f"ws://127.0.0.1:{listening.sockets[0].getsockname()[1]}", max_queue=1) as ws:
                await ws.send(dump(Hello(token="token")))
                await ws.recv(); await ws.recv()
                await ws.send(json.dumps({"v": 1, "type": "request_baseline_state"}))
                await ws.recv()
                for index in range(200):
                    server.publish_baseline(status=f"capture {index}")
                latest = json.loads(await ws.recv())
                assert latest["status"] == "capture 199"
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(ws.recv(), 0.05)
    asyncio.run(scenario())


def test_live_opponent_projection_is_inferred_and_partial_rosters_have_no_next_probability():
    from dataclasses import replace
    from tft_engine import GameHistory, TraitSighting
    from tft_live.advisor import LiveAdvisor
    fixture=runpy.run_path(str(Path(__file__).parents[1]/'packages/engine/tests/test_planning.py'))
    data,state=fixture['patch'](),fixture['snapshot']()
    rules=data.static['rules_flags']
    data=replace(data,static=dict(data.static)|{'rules_flags':replace(rules,value=dict(rules.value)|{'recent_opponent_exclusion_count':0})})
    sighting=TraitSighting('p1','3-2',2,{'fire':2},read_at=state.captured_at)
    complete=replace(state,fields=dict(state.fields)|{'recent_opponent_fights_complete':replace(state.fields['lobby_complete'],value=True),'recent_opponent_fights':replace(state.fields['lobby'],value=())})
    delivery=LiveAdvisor().evaluate(complete,GameHistory(sightings=(sighting,)),data,mode='live')
    first=next(row for row in delivery.content['opponents'] if row['opponent_id']=='p1')
    assert first['next_probability']==.5 and first['age_rounds']==0
    assert first['unit_probabilities'] and first['inference_certainty']>0
    assert 'units' not in first and 'items' not in first and 'positions' not in first
    partial=replace(complete,fields=dict(complete.fields)|{'lobby_complete':replace(complete.fields['lobby_complete'],value=False)})
    view=LiveAdvisor().evaluate(partial,GameHistory(sightings=(sighting,)),data,mode='live')
    assert view.content['opponents']
    assert all(row['next_probability'] is None and row['scout_due'] is False for row in view.content['opponents'])
    assert view.content['opponents'][0]['read_at']==state.captured_at.isoformat()


def test_async_publication_keeps_socket_responsive_and_rejects_a_downgrade_during_disk_flush(tmp_path,monkeypatch):
    import asyncio,os,threading
    from datetime import datetime,UTC
    from dataclasses import replace
    from websockets.asyncio.client import connect
    from tft_core.server import CoreServer
    from tft_core.storage import SessionStore
    from tft_core.messages import Hello,dump
    from tft_engine import GameHistory
    from tft_live.advisor import LiveAdvisor
    # The external disk flush is controlled; storage/log collaborators remain real.
    entered,release=threading.Event(),threading.Event()
    original=os.fsync
    held=False
    def slow_disk(fd):
        nonlocal held
        if threading.current_thread() is not threading.main_thread() and not held:
            held=True;entered.set()
            if not release.wait(3):raise OSError('Recorded disk timeout')
        return original(fd)
    async def scenario():
        fixture=runpy.run_path(str(Path(__file__).parents[1]/'packages/engine/tests/test_planning.py'))
        source=fixture['snapshot']();now=datetime.now(UTC)
        snapshot=replace(source,game_id='123',captured_at=now,fields={name:replace(field,read_at=now) for name,field in source.fields.items()})
        logs=SessionStore(tmp_path/'app',tmp_path/'config',live_installed=True);logs.set_mode('live');logs.start_game('123')
        server=CoreServer('token',sessions=logs)
        delivery=LiveAdvisor().evaluate(snapshot,GameHistory(),fixture['patch'](),mode='live')
        monkeypatch.setattr(os,'fsync',slow_disk)
        async with server.listen() as listener:
            async with connect(f'ws://127.0.0.1:{listener.sockets[0].getsockname()[1]}') as ws:
                await ws.send(dump(Hello(token='token')));await ws.recv();await ws.recv()
                pending=asyncio.create_task(server.publish_live_async(delivery))
                try:
                    assert await asyncio.to_thread(entered.wait,1)
                    await ws.send(json.dumps({'v':1,'type':'set_session_mode','mode':'baseline'}))
                    state=json.loads(await asyncio.wait_for(ws.recv(),1))
                    assert state['mode']=='baseline'
                finally:release.set()
                with pytest.raises(ValueError,match='mode|permission|superseded|cancelled'):
                    await pending
                assert not [row for row in logs.read_events('123') if row['kind']=='advice_delivery']
                assert not list((logs.log_path('123').parent/'evidence').glob('*.json'))
    asyncio.run(scenario())


def test_roll_tracker_uses_confirmed_copy_ledger_and_fixed_capture_floor():
    from dataclasses import replace
    from tft_engine import GameHistory
    from tft_live.advisor import LiveAdvisor
    fixture=runpy.run_path(str(Path(__file__).parents[1]/'packages/engine/tests/test_planning.py'))
    state=fixture['snapshot'](roll_down=True,roll_down_floor=10,owned_copies={'a':3,'c':1},shop=({'slot':0,'unit_id':'a','cost':1},),
        pinned_line={'id':'fixed-roll','levels':{},'rolls':{'3-2':10}})
    delivery=LiveAdvisor().evaluate(state,GameHistory(),fixture['patch'](),mode='live')
    tracker=delivery.content['roll_tracker']
    assert tracker['available'] is True and tracker['gold_floor']==10 and tracker['rolls_left']==10
    assert next(row for row in tracker['units'] if row['unit_id']=='a')['copies']==3
    unknown=replace(state,fields={name:field for name,field in state.fields.items() if name!='owned_copies'})
    absent=LiveAdvisor().evaluate(unknown,GameHistory(),fixture['patch'](),mode='live').content['roll_tracker']
    assert absent['available'] is False and 'ledger' in absent['reason']


def test_pin_change_rejects_inflight_old_pin_publication(tmp_path,monkeypatch):
    import asyncio,os,threading
    from dataclasses import replace
    from datetime import datetime,UTC
    from websockets.asyncio.client import connect
    from tft_core.messages import Hello,dump
    from tft_core.server import CoreServer
    from tft_core.storage import SessionStore
    from tft_engine import GameHistory
    from tft_live.advisor import LiveAdvisor
    entered,release=threading.Event(),threading.Event()
    original=os.fsync
    held=False
    def block_flush(fd):
        nonlocal held
        if threading.current_thread().name.startswith('tft-io') and not held:
            held=True;entered.set()
            if not release.wait(3):raise OSError('External flush timeout')
        return original(fd)
    async def scenario():
        fixtures=runpy.run_path(str(Path(__file__).parents[1]/'packages/engine/tests/test_planning.py'))
        source=fixtures['snapshot']();now=datetime.now(UTC)
        state=replace(source,game_id='123',captured_at=now,fields={name:replace(field,read_at=now) for name,field in source.fields.items()})
        logs=SessionStore(tmp_path/'app',tmp_path/'config',live_installed=True);logs.set_mode('live');logs.start_game('123')
        server=CoreServer('token',sessions=logs)
        advisor=LiveAdvisor();first=advisor.evaluate(state,GameHistory(),fixtures['patch'](),mode='live');server.publish_live(first)
        newer_at=datetime.now(UTC)
        updated=replace(state,snapshot_id='newer-frame',captured_at=newer_at,fields={name:replace(field,read_at=newer_at) for name,field in state.fields.items()})
        newer=advisor.evaluate(updated,GameHistory(),fixtures['patch'](),mode='live')
        monkeypatch.setattr(os,'fsync',block_flush)
        async with server.listen() as listener:
            async with connect(f'ws://127.0.0.1:{listener.sockets[0].getsockname()[1]}') as ws:
                await ws.send(dump(Hello(token='token')));await ws.recv();await ws.recv()
                await ws.send(json.dumps({'v':1,'type':'request_live_state'}));current=json.loads(await ws.recv())
                pending=asyncio.create_task(server.publish_live_async(newer))
                try:
                    for _ in range(100):
                        if entered.is_set():break
                        await asyncio.sleep(.005)
                    assert entered.is_set()
                    line=current['content']['lines'][1]
                    await ws.send(json.dumps({'v':1,'type':'pin_line','game_id':'123','revision':current['revision'],'comp_id':line['comp_id'],'line_id':line['line_id'],'seed':line['seed']}))
                    pinned=json.loads(await asyncio.wait_for(ws.recv(),1));assert pinned['pin']['line_id']==line['line_id']
                finally:release.set()
                with pytest.raises(ValueError,match='superseded|permission|cancelled'):await pending
                assert len([row for row in logs.read_events('123') if row['kind']=='advice_delivery'])==1
                assert server.live.state(logs.mode).revision==current['revision']
    asyncio.run(scenario())


def test_raw_capture_keeps_accepted_ui_pin_causal_without_changing_capture_time(tmp_path):
    import asyncio
    from dataclasses import replace
    from datetime import datetime,UTC
    from websockets.asyncio.client import connect
    from tft_core.messages import Hello,dump
    from tft_core.server import CoreServer
    from tft_core.storage import SessionStore
    from tft_engine import FieldValue,GameHistory
    from tft_live.advisor import LiveAdvisor
    async def scenario():
        fixtures=runpy.run_path(str(Path(__file__).parents[1]/'packages/engine/tests/test_planning.py'))
        source=fixtures['snapshot']();data=fixtures['patch']();now=datetime.now(UTC)
        frame=replace(source,game_id='123',captured_at=now,fields={name:replace(field,read_at=now) for name,field in source.fields.items()})
        logs=SessionStore(tmp_path/'app',tmp_path/'config',live_installed=True);logs.set_mode('live');logs.start_game('123')
        server=CoreServer('token',sessions=logs);advisor=LiveAdvisor()
        server.observe_live_capture(frame,data);server.publish_live(advisor.evaluate(frame,GameHistory(),data,mode='live'))
        async with server.listen() as listener:
            async with connect(f'ws://127.0.0.1:{listener.sockets[0].getsockname()[1]}') as ws:
                await ws.send(dump(Hello(token='token')));await ws.recv();await ws.recv()
                await ws.send(json.dumps({'v':1,'type':'request_live_state'}));current=json.loads(await ws.recv())
                line=current['content']['lines'][0]
                await ws.send(json.dumps({'v':1,'type':'pin_line','game_id':'123','revision':current['revision'],'comp_id':line['comp_id'],'line_id':line['line_id'],'seed':line['seed']}));await ws.recv()
                captured=datetime.now(UTC)
                raw=replace(frame,captured_at=captured,fields={name:replace(field,read_at=captured) for name,field in frame.fields.items()})
                pinned=replace(raw,fields=dict(raw.fields)|{'pinned_line':FieldValue(server.live.pin_schedule,server.live.pin_read_at,'ui_pin',1)})
                server.observe_live_capture(raw,data)
                await ws.recv()
                delivery=advisor.evaluate(pinned,GameHistory(),data,mode='live');server.publish_live(delivery)
                latest=json.loads(await ws.recv())
                econ=next(row for row in latest['content']['advice'] if row['domain']=='econ')
                assert econ['decision_id'] not in latest['invalidated']
                assert datetime.fromisoformat(latest['content']['captured_at'])==captured
                assert 'pinned_line' not in raw.fields
                server.observe_live_capture(frame,data)
                earlier=json.loads(await ws.recv())
                assert 'pinned_line' in earlier['invalidated'][econ['decision_id']]
    asyncio.run(scenario())


def test_ui_pin_receipt_time_does_not_expire_otherwise_fresh_display_fields():
    from dataclasses import replace
    from datetime import timedelta,datetime
    from tft_engine import GameHistory,FieldValue
    from tft_live.advisor import LiveAdvisor
    fixtures=runpy.run_path(str(Path(__file__).parents[1]/'packages/engine/tests/test_planning.py'))
    frame=fixtures['snapshot']();data=fixtures['patch']()
    pinned=replace(frame,fields=dict(frame.fields)|{'pinned_line':FieldValue({'id':'hold','levels':{},'rolls':{}},frame.captured_at-timedelta(seconds=30),'ui_pin',1)})
    view=LiveAdvisor().evaluate(pinned,GameHistory(),data,mode='live')
    dependent=[row for row in view.content['advice'] if 'pinned_line' in row['validity']]
    assert dependent
    assert all(row['valid_until'] is None or datetime.fromisoformat(row['valid_until'])>=frame.captured_at for row in dependent)


@pytest.mark.parametrize('cause',('capture_paused','mode_downgrade','unpinned_mode_downgrade','log_unavailable'))
def test_clearing_an_accepted_pin_records_one_causal_reset_or_fails_visibly(tmp_path,cause):
    import asyncio,subprocess,sys
    from dataclasses import replace
    from datetime import datetime,UTC
    from websockets.asyncio.client import connect
    from tft_core.messages import Hello,dump
    from tft_core.server import CoreServer
    from tft_core.storage import SessionStore
    from tft_engine import GameHistory
    from tft_live.advisor import LiveAdvisor
    async def scenario():
        fixtures=runpy.run_path(str(Path(__file__).parents[1]/'packages/engine/tests/test_planning.py'))
        source=fixtures['snapshot']();data=fixtures['patch']();now=datetime.now(UTC)
        frame=replace(source,game_id='123',captured_at=now,fields={name:replace(field,read_at=now) for name,field in source.fields.items()})
        logs=SessionStore(tmp_path/'app',tmp_path/'config',live_installed=True);logs.set_mode('live')
        logs.start_game('123',data_snapshot_id=data.snapshot_id)
        server=CoreServer('token',sessions=logs)
        server.observe_live_capture(frame,data);server.publish_live(LiveAdvisor().evaluate(frame,GameHistory(),data,mode='live'))
        async with server.listen() as listener:
            async with connect(f'ws://127.0.0.1:{listener.sockets[0].getsockname()[1]}') as ws:
                await ws.send(dump(Hello(token='token')));await ws.recv();await ws.recv()
                await ws.send(json.dumps({'v':1,'type':'request_live_state'}));current=json.loads(await ws.recv())
                if cause!='unpinned_mode_downgrade':
                    line=current['content']['lines'][0]
                    await ws.send(json.dumps({'v':1,'type':'pin_line','game_id':'123','revision':current['revision'],'comp_id':line['comp_id'],'line_id':line['line_id'],'seed':line['seed']}))
                    assert json.loads(await ws.recv())['pin']['line_id']==line['line_id']
                before=logs.read_events('123')
                if cause=='log_unavailable':
                    holder=subprocess.Popen([sys.executable,'-c','''
import os,sys
with open(sys.argv[1],'a+b') as stream:
    if os.name=='nt':
        import msvcrt
        stream.seek(0)
        msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
    else:
        import fcntl
        fcntl.flock(stream.fileno(),fcntl.LOCK_EX)
    print('held',flush=True)
    sys.stdin.readline()
''',str(logs.root/'.session-store.lock')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
                    try:
                        assert holder.stdout.readline().strip()=='held'
                        server.observe_live_capture(frame,None)
                    finally:
                        holder.communicate('release\n',timeout=5)
                    state=server.live.state(logs.mode)
                    assert state.pin is None
                    assert 'pin reset could not be logged' in state.status
                    assert logs.read_events('123')==before
                    return
                if cause=='capture_paused':
                    for _ in range(2):server.observe_live_capture(frame,None)
                else:
                    await ws.send(json.dumps({'v':1,'type':'set_session_mode','mode':'baseline'}))
                    await asyncio.sleep(.1)
                    server.observe_live_capture(frame,None)
                added=logs.read_events('123')[len(before):]
                resets=[event for event in added if event['kind']=='session_controls_reset']
                if cause=='unpinned_mode_downgrade':
                    assert resets==[]
                    return
                pin=next(event for event in before if event['kind']=='line_pin')
                assert len(resets)==1
                reset=resets[0]
                assert reset['payload']=={'schema_version':1,'game_id':'123','data_snapshot_id':data.snapshot_id,
                    'delivery_revision':current['revision'],'pin_seq':pin['seq'],'pin_read_at':pin['timestamp'],
                    'reason':reset['payload']['reason']}
                assert reset['payload']['reason']
                assert reset['seq']>pin['seq'] and reset['timestamp']>=pin['timestamp']
                assert server.live.pin is None
                # Review's causal control reader drops the pin exactly at this reset.
                from datetime import timedelta
                from tft_review.controls import project_session_controls
                events=logs.read_events('123')
                def at(event):
                    moment=datetime.fromisoformat(event['timestamp'])+timedelta(milliseconds=1)
                    return replace(frame,captured_at=moment,fields={name:replace(field,read_at=moment) for name,field in frame.fields.items()})
                assert project_session_controls(at(pin),events,through_seq=pin['seq']).snapshot.fields['pinned_line'].source=='ui_pin'
                after=project_session_controls(at(reset),events,through_seq=reset['seq'])
                assert 'pinned_line' not in after.snapshot.fields
                assert after.provenance['reset']['log_seq']==reset['seq']
    asyncio.run(scenario())
