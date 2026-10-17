"""Authenticated post-game access uses real durable logs and review locks."""
import asyncio,json,base64
import pytest
from PIL import Image
from websockets.asyncio.client import connect
from tft_core.server import CoreServer
from tft_core.storage import SessionStore
from tft_core.messages import Hello,dump


def test_logged_media_lock_chunks_and_silent_active_surface_gate(tmp_path):
    async def scenario():
        logs=SessionStore(tmp_path/'app',tmp_path/'config',live_installed=True)
        logs.start_game('123')
        name=logs.write_keyframe(Image.new('RGB',(32,32),'white'),reason='fixture')
        logs.end_game()
        server=CoreServer('review-token',sessions=logs)
        async with server.listen() as listener:
            async with connect(f'ws://127.0.0.1:{listener.sockets[0].getsockname()[1]}') as ws:
                await ws.send(dump(Hello(token='review-token')));await ws.recv();await ws.recv()
                request={'v':1,'type':'request_review','operation':'media','game_id':'123','request_id':'media', 'name':name,'cursor':0,'limit':24}
                await ws.send(json.dumps(request));error=json.loads(await ws.recv())
                assert error['code']=='review_request_rejected' and error['request_id']=='media'
                from tests.test_harness_baseline import baseline_fixture
                from datetime import datetime,UTC
                logs.start_run(baseline_fixture(sessions=logs,at=datetime.now(UTC)),set_id='18')
                chunks=[];cursor=0
                while True:
                    await ws.send(json.dumps(request|{'cursor':cursor}))
                    response=json.loads(await ws.recv())
                    assert response['type']=='review_response'
                    page=response['value'];chunks.append(base64.b64decode(page['base64']))
                    if page['next_cursor'] is None:break
                    cursor=page['next_cursor']
                assert b''.join(chunks)==logs.read_media('123',name)
                await ws.send(json.dumps(request|{'name':'media/'+('f'*32)+'.webp'}))
                assert json.loads(await ws.recv())['code']=='review_request_rejected'
                logs.set_mode('silent');logs.start_game('124')
                await ws.send(json.dumps(request))
                assert 'Silent' in json.loads(await ws.recv())['message']
                await ws.send(json.dumps(request|{'v':True}))
                assert json.loads(await ws.recv())['code']=='unsupported_version'
    asyncio.run(scenario())


def test_slow_review_media_cannot_queue_a_mode_downgrade_on_the_same_socket(tmp_path,monkeypatch):
    import threading
    from pathlib import Path
    entered,release=threading.Event(),threading.Event()
    original=Path.read_bytes
    held_path=None
    def slow_read(path):
        if path==held_path:
            entered.set()
            if not release.wait(3):raise OSError('Recorded media read timeout')
        return original(path)
    async def scenario():
        nonlocal held_path
        logs=SessionStore(tmp_path/'app',tmp_path/'config',live_installed=True)
        logs.set_mode('baseline');logs.start_game('123')
        name=logs.write_keyframe(Image.new('RGB',(32,32)),reason='fixture');logs.end_game()
        logs.set_mode('live');logs.start_game('124')
        held_path=logs.log_path('123').parent/name
        monkeypatch.setattr(Path,'read_bytes',slow_read)
        server=CoreServer('token',sessions=logs)
        async with server.listen() as listener:
            async with connect(f'ws://127.0.0.1:{listener.sockets[0].getsockname()[1]}') as ws:
                await ws.send(dump(Hello(token='token')));await ws.recv();await ws.recv()
                await ws.send(json.dumps({'v':1,'type':'request_review','request_id':'held-media','game_id':'123','operation':'media','name':name,'limit':24}))
                try:
                    # A separate external observer reports entry, without a default executor.
                    for _ in range(100):
                        if entered.is_set():break
                        await asyncio.sleep(.005)
                    assert entered.is_set()
                    await ws.send(json.dumps({'v':1,'type':'set_session_mode','mode':'silent'}))
                    message=json.loads(await asyncio.wait_for(ws.recv(),1))
                    assert message['type']=='session_mode' and message['mode']=='silent'
                finally:release.set()
                rejected=json.loads(await asyncio.wait_for(ws.recv(),1))
                assert rejected['type']=='error' and rejected['request_id']=='held-media'
                assert 'Silent' in rejected['message']
    asyncio.run(scenario())


def test_failed_media_io_reports_error_and_preserves_same_client_review_worker(tmp_path,monkeypatch):
    from pathlib import Path
    original=Path.read_bytes
    failed=False
    target=None
    def failed_once(path):
        nonlocal failed
        if path==target and not failed:
            failed=True
            raise OSError('External recorded-media read failure')
        return original(path)
    async def scenario():
        nonlocal target
        logs=SessionStore(tmp_path/'app',tmp_path/'config',live_installed=True)
        logs.set_mode('baseline');logs.start_game('123')
        name=logs.write_keyframe(Image.new('RGB',(32,32)),reason='fixture');logs.end_game()
        target=logs.log_path('123').parent/name
        monkeypatch.setattr(Path,'read_bytes',failed_once)
        server=CoreServer('token',sessions=logs)
        async with server.listen() as listener:
            async with connect(f'ws://127.0.0.1:{listener.sockets[0].getsockname()[1]}') as ws:
                await ws.send(dump(Hello(token='token')));await ws.recv();await ws.recv()
                request={'v':1,'type':'request_review','request_id':'failed-media','game_id':'123','operation':'media','name':name,'limit':24}
                await ws.send(json.dumps(request))
                error=json.loads(await asyncio.wait_for(ws.recv(),.5))
                assert error['type']=='error' and error['request_id']=='failed-media'
                assert 'External recorded-media read failure' in error['message']
                await ws.send(json.dumps(request|{'request_id':'retry-media'}))
                response=json.loads(await asyncio.wait_for(ws.recv(),.5))
                assert response['type']=='review_response' and response['request_id']=='retry-media'
                assert len(base64.b64decode(response['value']['base64']))==24
    asyncio.run(scenario())


def test_review_ready_uses_finished_game_last_mode_and_checked_report_not_current_default(tmp_path):
    from tft_engine.evidence import EvidenceGraph
    async def scenario():
        logs=SessionStore(tmp_path/'app',tmp_path/'config',live_installed=True)
        logs.set_mode('baseline');logs.start_game('123');logs.end_game()
        graph=EvidenceGraph.factor({'game_id':'123','summary':{'top5':[]},'moments':[]})
        logs.write_review('123',{'schema_version':1,'report_id':graph.root_id,'evidence_graph':graph.to_dict()},engine_version='fixture',data_snapshot_id='fixture')
        assert logs.mode.value=='silent'  # Default after the game is not its finished mode.
        server=CoreServer('token',sessions=logs)
        async with server.listen() as listener:
            async with connect(f'ws://127.0.0.1:{listener.sockets[0].getsockname()[1]}') as ws:
                await ws.send(dump(Hello(token='token')));await ws.recv();await ws.recv()
                ready=await server.publish_review_ready('123')
                assert ready is not None and ready.mode=='baseline'
                delivered=json.loads(await asyncio.wait_for(ws.recv(),1))
                assert delivered['type']=='review_ready' and delivered['game_id']=='123'
                assert delivered['report_id']==graph.root_id and delivered['latency_seconds']>=0
                logs.set_mode('live');logs.start_game('124');logs.set_mode('silent');logs.end_game()
                silent_graph=EvidenceGraph.factor({'game_id':'124','summary':{'top5':[]},'moments':[]})
                logs.write_review('124',{'schema_version':1,'report_id':silent_graph.root_id,'evidence_graph':silent_graph.to_dict()},engine_version='fixture',data_snapshot_id='fixture')
                assert next(row for row in logs.list_games() if row['game_id']=='124')['mode']=='live'
                assert await server.publish_review_ready('124') is None
                logs.set_mode('baseline');logs.start_game('125')
                assert await server.publish_review_ready('123') is None  # A later game's UI is not interrupted.
    asyncio.run(scenario())


def test_slow_tag_flush_does_not_hold_mode_lock_or_publish_after_silent_downgrade(tmp_path,monkeypatch):
    import os,threading,time
    from tft_data import DataStore
    from tft_engine.evidence import EvidenceGraph
    from tft_review import ReviewService
    entered,release=threading.Event(),threading.Event()
    original=os.fsync
    held=False
    def slow_disk(fd):
        nonlocal held
        if threading.current_thread().name.startswith('tft-io') and not held:
            held=True;entered.set()
            if not release.wait(2):raise OSError('External review-tag flush timeout')
        return original(fd)
    async def scenario():
        logs=SessionStore(tmp_path/'app',tmp_path/'config',live_installed=True)
        logs.set_mode('baseline');logs.start_game('123');logs.end_game()
        graph=EvidenceGraph.factor({'game_id':'123','summary':{'top5':[]},'moments':[]})
        logs.write_review('123',{'schema_version':1,'report_id':graph.root_id,'evidence_graph':graph.to_dict(),'decision_ids':['moment']},engine_version='fixture',data_snapshot_id='fixture')
        service=ReviewService(logs,DataStore(tmp_path/'data'),repository=tmp_path)
        logs.set_mode('live');logs.start_game('124')
        server=CoreServer('token',sessions=logs,review_service=service)
        monkeypatch.setattr(os,'fsync',slow_disk)
        async with server.listen() as listener:
            async with connect(f'ws://127.0.0.1:{listener.sockets[0].getsockname()[1]}') as ws:
                await ws.send(dump(Hello(token='token')));await ws.recv();await ws.recv()
                await ws.send(json.dumps({'v':1,'type':'request_review','request_id':'held-tag','game_id':'123','operation':'tag','report_id':graph.root_id,'evidence_id':graph.root_id,'moment_id':'moment','tag':'agree'}))
                for _ in range(100):
                    if entered.is_set():break
                    await asyncio.sleep(.005)
                assert entered.is_set()
                started=time.monotonic()
                try:
                    await ws.send(json.dumps({'v':1,'type':'set_session_mode','mode':'silent'}))
                    messages=[]
                    while not any(row.get('type')=='session_mode' for row in messages):
                        messages.append(json.loads(await asyncio.wait_for(ws.recv(),1)))
                    assert time.monotonic()-started<.5
                finally:release.set()
                if not any(row.get('request_id')=='held-tag' for row in messages):
                    messages.append(json.loads(await asyncio.wait_for(ws.recv(),1)))
                assert any(row.get('request_id')=='held-tag' and row['type']=='error' for row in messages)
                assert logs.read_review('123')['tags']=={}
    asyncio.run(scenario())


def test_authenticated_regeneration_and_cross_game_summaries_use_review_jobs(tmp_path):
    from tests.test_replay_contracts import ROOT, logged_game
    from tft_core.review_jobs import ReviewJobs
    from tft_review import ReviewService
    async def scenario():
        logs, store, _, _ = logged_game(tmp_path, mode='baseline')
        service = ReviewService(logs, store, repository=ROOT)
        jobs = ReviewJobs(logs, store, service, ROOT)
        server = CoreServer('token', sessions=logs, review_service=service)
        server.review.enqueue = jobs.enqueue
        jobs.start()
        try:
            async with server.listen() as listener:
                async with connect(f'ws://127.0.0.1:{listener.sockets[0].getsockname()[1]}') as ws:
                    await ws.send(dump(Hello(token='token'))); await ws.recv(); await ws.recv()
                    await ws.send(json.dumps({'v':1, 'type':'request_review', 'request_id':'manual',
                        'game_id':'901', 'operation':'regenerate'}))
                    queued = json.loads(await ws.recv())
                    assert queued['type'] == 'review_response', queued
                    assert queued['value']['state'] == 'queued'
                    for _ in range(500):
                        records = jobs.jobs()
                        if records and records[0]['state'] == 'completed': break
                        await asyncio.sleep(.01)
                    assert jobs.jobs()[0]['state'] == 'completed'
                    await ws.send(json.dumps({'v':1, 'type':'request_review_games', 'request_id':'games'}))
                    view = json.loads(await ws.recv())
                    assert view['games'][0]['game_id'] == '901'
                    assert 'total_estimated_cost' in view['games'][0]
                    assert view['aggregates']['last10']['games'] == 1
                    logs.set_mode('silent'); logs.start_game('902')
                    await ws.send(json.dumps({'v':1, 'type':'request_review', 'request_id':'blocked',
                        'game_id':'901', 'operation':'regenerate'}))
                    assert json.loads(await ws.recv())['code'] == 'review_request_rejected'
        finally:
            await jobs.shutdown()
    asyncio.run(scenario())


def test_locked_finished_review_cannot_be_manually_regenerated(tmp_path):
    import pytest
    from tft_core.review_transport import ReviewTransport
    from tests.test_replay_contracts import logged_game
    logs, _, _, _ = logged_game(tmp_path)
    with pytest.raises(ValueError, match='locked'):
        ReviewTransport(logs).call('regenerate', '901')


def test_visible_review_notice_receipt_is_durable_late_and_preserves_review_input(tmp_path, monkeypatch):
    from datetime import datetime, UTC, timedelta
    from tft_engine.evidence import EvidenceGraph
    import tft_core.server as server_module
    clock = datetime.now(UTC)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return clock
    monkeypatch.setattr(server_module, 'datetime', Clock)
    async def scenario():
        nonlocal clock
        logs = SessionStore(tmp_path/'app', tmp_path/'config', live_installed=True)
        logs.set_mode('baseline'); logs.start_game('123',timestamp=(clock-timedelta(seconds=20)).isoformat())
        logs.end_game(timestamp=(clock-timedelta(seconds=10)).isoformat())
        graph = EvidenceGraph.factor({'game_id':'123','summary':{'top5':[]},'moments':[]})
        logs.write_review('123',{'schema_version':1,'report_id':graph.root_id,'evidence_graph':graph.to_dict()},engine_version='fixture',data_snapshot_id='fixture')
        before = logs.log_path('123').read_bytes()
        report_before = logs.read_review('123')
        server = CoreServer('token',sessions=logs)
        async with server.listen() as listener:
            async with connect(f'ws://127.0.0.1:{listener.sockets[0].getsockname()[1]}') as ws:
                await ws.send(dump(Hello(token='token'))); await ws.recv(); await ws.recv()
                await server.publish_review_ready('123')
                ready = json.loads(await ws.recv())
                assert ready['late'] is False
                clock += timedelta(seconds=25)
                receipt = {key:ready[key] for key in ('game_id','report_id','evidence_id','job_id','notice_id')}
                receipt.update(v=1,type='review_notice_shown',surface='status',timestamp=clock.isoformat())
                await ws.send(json.dumps(receipt))
                response = json.loads(await ws.recv())
                assert response['type']=='review_ready', response
                assert response['display_late'] is True
                assert response['display_latency_seconds']==35
                stored = json.loads((logs.root/'reviews'/'123.notice.json').read_text())
                assert stored['receipts'][0]['surface']=='status'
                assert stored['receipts'][0]['late'] is True
                await ws.send(json.dumps(receipt))
                assert json.loads(await ws.recv())['type']=='review_ready'
                assert len(json.loads((logs.root/'reviews'/'123.notice.json').read_text())['receipts'])==1
                for change in ({'notice_id':'a'*32},{'report_id':'sha256:'+'b'*64},
                               {'game_id':'999'},{'job_id':'f'*64},
                               {'timestamp':(clock+timedelta(seconds=1)).isoformat()},
                               {'timestamp':(clock-timedelta(seconds=6)).isoformat()}):
                    await ws.send(json.dumps(receipt|change))
                    error=json.loads(await ws.recv())
                    assert error['code']=='review_notice_rejected', error
                logs.set_mode('baseline');logs.start_game('124',timestamp=clock.isoformat())
                await ws.send(json.dumps(receipt))
                assert json.loads(await ws.recv())['code']=='review_notice_rejected'
                assert logs.log_path('123').read_bytes()==before
                assert logs.read_review('123')==report_before
    asyncio.run(scenario())


@pytest.mark.parametrize('invalidate',['new_game','republished_notice'])
def test_slow_notice_flush_keeps_same_socket_mode_responsive_and_cancels_on_new_game(tmp_path, monkeypatch, invalidate):
    import threading
    import tft_core.storage as storage
    from datetime import datetime, UTC
    from tft_engine.evidence import EvidenceGraph
    entered, release = threading.Event(), threading.Event()
    original = storage.os.fsync
    def fsync(fd):
        if threading.current_thread().name.startswith('tft-io'):
            entered.set()
            if not release.wait(3):raise TimeoutError('fixture notice flush timed out')
        return original(fd)
    async def scenario():
        logs=SessionStore(tmp_path/'app',tmp_path/'config',live_installed=True)
        logs.set_mode('baseline');logs.start_game('123');logs.end_game()
        graph=EvidenceGraph.factor({'game_id':'123','summary':{'top5':[]},'moments':[]})
        logs.write_review('123',{'schema_version':1,'report_id':graph.root_id,'evidence_graph':graph.to_dict()},engine_version='fixture',data_snapshot_id='fixture')
        server=CoreServer('token',sessions=logs)
        async with server.listen() as listener:
            async with connect(f'ws://127.0.0.1:{listener.sockets[0].getsockname()[1]}') as ws:
                await ws.send(dump(Hello(token='token')));await ws.recv();await ws.recv()
                await server.publish_review_ready('123');ready=json.loads(await ws.recv())
                monkeypatch.setattr(storage.os,'fsync',fsync)
                receipt={key:ready[key] for key in ('game_id','report_id','evidence_id','job_id','notice_id')}
                receipt.update(v=1,type='review_notice_shown',surface='status',timestamp=datetime.now(UTC).isoformat())
                try:
                    await ws.send(json.dumps(receipt))
                    for _ in range(100):
                        if entered.is_set():break
                        await asyncio.sleep(.01)
                    assert entered.is_set()
                    await ws.send(json.dumps({'v':1,'type':'set_session_mode','mode':'baseline'}))
                    response=json.loads(await asyncio.wait_for(ws.recv(),.5))
                    assert response['type']=='session_mode',response
                    if invalidate=='new_game':logs.start_game('124')
                    else:
                        await server.publish_review_ready('123')
                        assert json.loads(await ws.recv())['type']=='review_ready'
                finally:release.set()
                error=json.loads(await asyncio.wait_for(ws.recv(),1))
                assert error['code']=='review_notice_rejected'
                assert not (logs.root/'reviews'/'123.notice.json').exists()
    asyncio.run(scenario())
