"""The core and background children share the real durable store."""
import json
import subprocess
import sys
import pytest

from tft_core.storage import SessionStore


@pytest.mark.parametrize('process_count',(2,8))
def test_concurrent_process_constructors_preserve_logs_metadata_and_replay_cache(tmp_path,process_count):
    store = SessionStore(tmp_path/'logs',tmp_path/'config',live_installed=False)
    for index in range(10):
        store.start_game(str(901+index),patch='fixture.1',data_snapshot_id='historical-pin',
            timestamp='2026-10-14T10:00:00+00:00')
        store.end_game(placement=index%8+1,timestamp='2026-10-14T10:30:00+00:00')
    store.write_replay_cache('901',[{'decision_id':'fixture-decision'}],
        engine_version='fixture-engine',tunables_hash='fixture-tunables',data_snapshot_id='historical-pin')
    before = {str(901+index):store.log_path(str(901+index)).read_bytes() for index in range(10)}
    expected = store.list_games()
    script = '''
import json,sys
from pathlib import Path
from tft_core.storage import SessionStore
print('ready',flush=True)
sys.stdin.readline()
store=SessionStore(Path(sys.argv[1]),Path(sys.argv[2]),live_installed=False)
print(json.dumps({'games':store.list_games(),'cache':store.read_replay_cache('901',
    engine_version='fixture-engine',tunables_hash='fixture-tunables',data_snapshot_id='historical-pin')}))
'''
    children = [subprocess.Popen([sys.executable,'-c',script,str(store.root),str(store.config_root)],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(process_count)]
    try:
        for child in children:
            assert child.stdout.readline().strip() == 'ready'
        for child in children:
            child.stdin.write('go\n')
            child.stdin.flush()
        outputs = [(child,*child.communicate(timeout=15)) for child in children]
        errors = [stderr for child,_,stderr in outputs if child.returncode != 0]
        assert not errors,errors
        for _,stdout,_ in outputs:
            result = json.loads(stdout)
            assert result['games'] == expected
            assert result['cache'] == [{'decision_id':'fixture-decision'}]
        assert store.list_games() == expected
        assert all(store.log_path(game).read_bytes() == content for game,content in before.items())
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.communicate()


def test_independent_store_cache_writes_keep_one_committed_sequence(tmp_path):
    first = SessionStore(tmp_path/'logs',tmp_path/'config',live_installed=False)
    first.start_game('901')
    first.end_game(placement=4)
    second = SessionStore(first.root,first.config_root,live_installed=False)
    for writer,version in ((first,'a'),(second,'b'),(first,'c')):
        writer.write_replay_cache('901',[{'version':version}],engine_version=version,
            tunables_hash='fixture',data_snapshot_id='fixture-pin')
    events = first.read_events('901')
    assert [event['seq'] for event in events] == [0,1,2,3,4]
    assert [event['payload']['engine_version'] for event in events if event['kind'] == 'replay_cache'] == ['a','b','c']


def test_failed_rebuild_preserves_last_good_index_and_committed_other_games(tmp_path):
    store = SessionStore(tmp_path/'logs',tmp_path/'config',live_installed=False)
    store.start_game('901')
    store.end_game(placement=4)
    before = store.log_path('901').read_bytes()
    index = (store.root/'index.sqlite3').read_bytes()
    known = store.list_games()
    bad = store.log_path('902')
    bad.parent.mkdir()
    bad.write_bytes(b'{"external_corrupt_committed_log":true}\n')
    with pytest.raises(ValueError,match='sequence'):
        store.rebuild_index()
    assert (store.root/'index.sqlite3').read_bytes() == index
    assert store.list_games() == known
    assert store.log_path('901').read_bytes() == before
    bad.unlink()
    assert SessionStore(store.root,store.config_root,live_installed=False).list_games() == known


def test_background_cache_processes_and_next_game_writer_preserve_authoritative_metadata(tmp_path):
    store = SessionStore(tmp_path/'logs',tmp_path/'config',live_installed=False)
    store.start_game('901',data_snapshot_id='original-pin')
    store.end_game(placement=4)
    script = '''
import sys
from pathlib import Path
from tft_core.storage import SessionStore
store=SessionStore(Path(sys.argv[1]),Path(sys.argv[2]),live_installed=False)
print('ready',flush=True)
sys.stdin.readline()
for turn in range(5):
    version='child-'+sys.argv[3]+'-'+str(turn)
    store.write_replay_cache('901',[{'version':version}],engine_version=version,
        tunables_hash='fixture',data_snapshot_id='original-pin')
print('completed',flush=True)
'''
    children = [subprocess.Popen([sys.executable,'-c',script,str(store.root),str(store.config_root),str(index)],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for index in range(2)]
    try:
        for child in children:
            assert child.stdout.readline().strip() == 'ready'
        for child in children:
            child.stdin.write('go\n')
            child.stdin.flush()
        for identity in ('902','903','904'):
            store.start_game(identity,data_snapshot_id='next-game-pin')
            store.append_event('snapshot',{'external_fixture':True})
            store.end_game(placement=3)
        for child in children:
            stdout,stderr = child.communicate(timeout=15)
            assert child.returncode == 0,stderr
            assert stdout.strip() == 'completed'
        assert [event['seq'] for event in store.read_events('901')] == list(range(12))
        games = {row['game_id']:row for row in store.list_games()}
        assert set(games) == {'901','902','903','904'}
        assert games['901']['data_snapshot_id'] == 'original-pin'
        for identity in ('902','903','904'):
            assert games[identity]['finished'] is True
            assert games[identity]['placement'] == 3
            assert games[identity]['data_snapshot_id'] == 'next-game-pin'
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.communicate()
