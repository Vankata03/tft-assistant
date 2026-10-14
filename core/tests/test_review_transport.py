"""Authenticated post-game access uses real durable logs and review locks."""
import asyncio,json,base64
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
