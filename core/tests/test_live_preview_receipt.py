"""Preview display receipts cross the authenticated public socket into the log."""
import asyncio
import json
import pytest
from websockets.exceptions import ConnectionClosedError
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from websockets.asyncio.client import connect

from pathlib import Path
import runpy
_fixture = runpy.run_path(str(Path(__file__).with_name("test_live_combat_preview.py")))
FIXTURES, SCHEDULE, frame, combat = (_fixture[name] for name in ("FIXTURES", "SCHEDULE", "frame", "combat"))


def test_preview_receipt_is_durable_deduplicated_and_not_actionable(tmp_path):
    from tft_core.messages import Hello, dump
    from tft_core.server import CoreServer
    from tft_core.storage import SessionStore
    from tft_engine import GameHistory
    from tft_live.advisor import LiveAdvisor

    async def scenario():
        data = FIXTURES['patch']()
        sessions = SessionStore(tmp_path/'app', tmp_path/'config', live_installed=True)
        sessions.set_mode('live')
        sessions.start_game('123', data_snapshot_id=data.snapshot_id)
        server = CoreServer('token', sessions=sessions)
        now = datetime.now(UTC)
        def fresh(source, at):
            return replace(source, captured_at=at, fields={k:replace(v, read_at=at) for k,v in source.fields.items()})
        planning = fresh(frame(game_id='123', pinned_line=SCHEDULE), now-timedelta(seconds=1))
        fight = fresh(combat(game_id='123'), now)
        server.observe_live_capture(fight, data)
        server.publish_live(LiveAdvisor().evaluate(fight, GameHistory((planning,)), data, mode='live'))
        state = server.live.state(sessions.mode)
        shown = {'v':1, 'type':'live_preview_shown', 'game_id':'123', 'revision':state.revision,
                 'data_snapshot_id':data.snapshot_id, 'round_id':'3-2',
                 'preview':state.content.next_planning.model_dump(mode='json'),
                 'surface':'overlay', 'timestamp':datetime.now(UTC).isoformat()}
        async with server.listen() as listening:
            url = f'ws://127.0.0.1:{listening.sockets[0].getsockname()[1]}'
            async with connect(url) as unauthenticated:
                await unauthenticated.send(json.dumps(shown))
                with pytest.raises(ConnectionClosedError):
                    await unauthenticated.recv()
            async with connect(url) as ws:
                await ws.send(dump(Hello(token='token')))
                await ws.recv(); await ws.recv()
                await ws.send(json.dumps(shown)); await ws.send(json.dumps(shown))
                await ws.send(json.dumps({'v':1,'type':'request_live_state'})); await ws.recv()
                events = sessions.read_events('123')
                receipts = [e for e in events if e['kind']=='preview_shown']
                assert len(receipts)==1
                assert receipts[0]['timestamp']==shown['timestamp']
                payload=receipts[0]['payload']
                assert payload['preview']==shown['preview']
                assert payload['data_snapshot_id']==data.snapshot_id
                assert payload['round_id']=='3-2'
                assert payload['delivery_revision']==state.revision
                assert payload['evidence_id']==state.content.evidence_id
                assert payload['surface']=='overlay'
                assert not any(e['kind']=='ui_show' for e in events)
                for forged in ({'preview':shown['preview']|{'level':7}}, {'game_id':'124'},
                               {'revision':'sha256:'+'0'*64}, {'data_snapshot_id':'invented'},
                               {'round_id':'3-3'}, {'timestamp':(now-timedelta(days=1)).isoformat()},
                               {'timestamp':(now+timedelta(days=1)).isoformat()}):
                    await ws.send(json.dumps(shown|forged))
                    assert json.loads(await ws.recv())['code']=='live_request_rejected'
                server.observe_live_capture(fresh(combat('3-3', game_id='123'), datetime.now(UTC)), data)
                await ws.recv()  # subscribed invalidation
                await ws.send(json.dumps(shown))
                assert json.loads(await ws.recv())['code']=='live_request_rejected'
                assert len([e for e in sessions.read_events('123') if e['kind']=='preview_shown'])==1
                await ws.send(json.dumps({'v':1,'type':'set_session_mode','mode':'silent'}))
                assert json.loads(await ws.recv())['mode']=='silent'
                assert json.loads(await ws.recv())['content'] is None
                await ws.send(json.dumps(shown))
                assert json.loads(await ws.recv())['code']=='live_request_rejected'
    asyncio.run(scenario())


@pytest.mark.parametrize('boundary', ['silent', 'baseline', 'capture_missing', 'capture_stale',
    'phase_stale', 'phase_aged_at_receipt', 'phase_changed', 'data_changed', 'level_reached', 'pin_epoch',
    'superseded', 'game_ended', 'unavailable'])
def test_preview_receipt_rejects_changed_permission_or_evidence(tmp_path, boundary, monkeypatch):
    from tft_core.messages import parse_ui_message, PinLine
    from tft_core.server import CoreServer
    from tft_core.storage import SessionStore
    from tft_engine import GameHistory
    from tft_live.advisor import LiveAdvisor

    data = FIXTURES['patch']()
    sessions = SessionStore(tmp_path/'app', tmp_path/'config', live_installed=True)
    sessions.set_mode('live'); sessions.start_game('123', data_snapshot_id=data.snapshot_id)
    server = CoreServer('token', sessions=sessions)
    now = datetime.now(UTC)
    def fresh(source, at=now):
        return replace(source, captured_at=at, fields={k:replace(v, read_at=at) for k,v in source.fields.items()})
    planning = fresh(frame(game_id='123', pinned_line=SCHEDULE), now-timedelta(seconds=1))
    fight = fresh(combat(game_id='123'))
    history = GameHistory(()) if boundary=='unavailable' else GameHistory((planning,))
    server.observe_live_capture(fight, data)
    server.publish_live(LiveAdvisor().evaluate(fight, history, data, mode='live'))
    state = server.live.state(sessions.mode)
    message = parse_ui_message(json.dumps({'v':1, 'type':'live_preview_shown', 'game_id':'123',
        'revision':state.revision,'data_snapshot_id':data.snapshot_id, 'round_id':'3-2',
        'preview':state.content.next_planning.model_dump(mode='json'),
        'surface':'overlay','timestamp':datetime.now(UTC).isoformat()}))
    if boundary in ('silent','baseline'):
        sessions.set_mode(boundary)
    elif boundary=='capture_missing':
        server.observe_live_capture(None, None)
    elif boundary=='capture_stale':
        server.observe_live_capture(fresh(fight, now-timedelta(minutes=5)), data)
    elif boundary=='phase_stale':
        server.observe_live_capture(replace(fight, fields=dict(fight.fields)|{
            'phase':replace(fight.fields['phase'],read_at=now-timedelta(minutes=5))}), data)
    elif boundary=='phase_aged_at_receipt':
        server.observe_live_capture(replace(fight, fields=dict(fight.fields)|{
            'phase':replace(fight.fields['phase'],read_at=now-timedelta(seconds=1.5))}), data)
        class ReceiptClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return now+timedelta(seconds=1)
        monkeypatch.setattr('tft_core.live_delivery.datetime', ReceiptClock)
    elif boundary=='phase_changed':
        server.observe_live_capture(planning, data)
    elif boundary=='data_changed':
        server.observe_live_capture(fight, replace(data, snapshot_id='changed'))
    elif boundary=='level_reached':
        server.observe_live_capture(fresh(combat(game_id='123',level=6)), data)
    elif boundary=='pin_epoch':
        server.live.pin_line(PinLine(game_id='123',revision=state.revision), sessions.mode)
    elif boundary=='superseded':
        newer = fresh(combat(game_id='123', seconds=2))
        server.observe_live_capture(newer,data)
        server.publish_live(LiveAdvisor().evaluate(newer, history, data, mode='live'))
    elif boundary=='game_ended':
        sessions.end_game()
    with pytest.raises(ValueError):
        server.live.preview_shown(message, sessions.mode)
    assert not any(e['kind']=='preview_shown' for e in sessions.read_events('123'))


def test_preview_receipt_accepts_overlay_only_and_has_no_actionable_identity():
    from pydantic import ValidationError
    from tft_core.messages import LivePreviewShown
    point = {'available':True,'reason':None,'comp_id':'A','line_id':'fixed','pinned':True,
        'planning_round':'3-2','planning_snapshot_id':'123:3-2:0','round_id':'4-1','level':6,
        'gold_floor':None,'evidence_path':['plan','line']}
    receipt = {'game_id':'123','revision':'sha256:'+'a'*64,'data_snapshot_id':'fixture',
        'round_id':'3-2','preview':point,'surface':'overlay','timestamp':datetime.now(UTC)}
    LivePreviewShown(**receipt)
    for changed in ({'surface':'voice'}, {'surface':'cockpit'}, {'decision_id':'invented'},
                    {'timestamp':'2026-10-17T00:00:00'}):
        with pytest.raises(ValidationError):
            LivePreviewShown(**(receipt|changed))
