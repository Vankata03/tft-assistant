"""A real Python process can stop while external graph fsync remains blocked."""
import json
from pathlib import Path
import subprocess
import sys


def test_real_server_process_exits_without_default_executor_drain(tmp_path):
    core=Path(__file__).parents[1]
    script=tmp_path/'blocked_io.py'
    script.write_text('''import asyncio,json,os,threading,runpy
from pathlib import Path
from datetime import datetime,UTC
from dataclasses import replace
from tft_core.server import CoreServer
from tft_core.storage import SessionStore
from tft_core.app import _stdin_closed
from tft_engine import GameHistory
from tft_live.advisor import LiveAdvisor
root=Path(__import__('sys').argv[1]);core=Path(__import__('sys').argv[2])
f=runpy.run_path(str(core/'packages/engine/tests/test_planning.py'))
state=f['snapshot']();now=datetime.now(UTC)
state=replace(state,game_id='123',captured_at=now,fields={name:replace(field,read_at=now) for name,field in state.fields.items()})
logs=SessionStore(root/'app',root/'config',live_installed=True);logs.set_mode('live');logs.start_game('123')
delivery=LiveAdvisor().evaluate(state,GameHistory(),f['patch'](),mode='live')
original=os.fsync;held=False;gate=threading.Event()
def blocked(fd):
 global held
 if threading.current_thread().name.startswith('tft-io-') and not held:
  held=True;print('FLUSH_BLOCKED',flush=True);gate.wait(600)
 return original(fd)
os.fsync=blocked
async def main():
 server=CoreServer('shutdown-fixture',sessions=logs)
 async with server.listen():
  task=asyncio.create_task(server.publish_live_async(delivery))
  await _stdin_closed(asyncio.get_running_loop()).wait()
  status=await server.shutdown_io(timeout=.05)
  print(json.dumps({'shutdown':status}),flush=True)
  await asyncio.gather(task,return_exceptions=True)
asyncio.run(main())
''')
    process=subprocess.Popen([sys.executable,'-u',str(script),str(tmp_path/'state'),str(core)],
        cwd=core,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        first=process.stdout.readline()
        assert first.strip()=='FLUSH_BLOCKED'
        output,errors=process.communicate('',timeout=3)
        assert process.returncode==0,errors
        status=json.loads(next(line for line in output.splitlines() if line.startswith('{')))
        assert status['shutdown']['alive_workers']==1
        events=[json.loads(line) for line in (tmp_path/'state/app/games/123/events.jsonl').read_text().splitlines()]
        assert not any(event['kind'] in {'engine_evidence','advice_delivery','game_end'} for event in events)
        assert not list((tmp_path/'state/app/games/123/evidence').glob('*.json'))
    finally:
        if process.poll() is None:
            process.kill();process.communicate()


def test_repeated_real_shutdowns_wake_idle_workers_and_keep_only_the_native_blocked_worker(tmp_path):
    core=Path(__file__).parents[1]
    script=tmp_path/'repeated_shutdown.py'
    script.write_text('''import asyncio,json,os,threading,runpy,sys
from pathlib import Path
from datetime import datetime,UTC
from dataclasses import replace
from tft_core.server import CoreServer
from tft_core.storage import SessionStore
from tft_engine import GameHistory
from tft_live.advisor import LiveAdvisor
root=Path(sys.argv[1]);core=Path(sys.argv[2])
f=runpy.run_path(str(core/'packages/engine/tests/test_planning.py'))
state=f['snapshot']();now=datetime.now(UTC)
state=replace(state,game_id='123',captured_at=now,fields={name:replace(field,read_at=now) for name,field in state.fields.items()})
delivery=LiveAdvisor().evaluate(state,GameHistory(),f['patch'](),mode='live')
original=os.fsync;gate=threading.Event();blocked=set();entered=threading.Event()
def held(fd):
 name=threading.current_thread().name
 if name.startswith('tft-io-') and threading.current_thread() not in blocked:
  blocked.add(threading.current_thread());entered.set();gate.wait(600)
 return original(fd)
os.fsync=held
async def main():
 statuses=[]
 for turn in range(10):
  logs=SessionStore(root/str(turn)/'app',root/str(turn)/'config',live_installed=True);logs.set_mode('live');logs.start_game('123')
  server=CoreServer('shutdown-fixture',sessions=logs);entered.clear()
  async with server.listen():
   task=asyncio.create_task(server.publish_live_async(delivery))
   while not entered.is_set():await asyncio.sleep(.001)
   # Let the idle worker settle into its wait before shutdown begins.
   await asyncio.sleep(.003*turn)
   statuses.append(await server.shutdown_io(timeout=.01))
   await asyncio.gather(task,return_exceptions=True)
 print(json.dumps(statuses),flush=True)
asyncio.run(main())
''')
    result=subprocess.run([sys.executable,'-u',str(script),str(tmp_path/'state'),str(core)],
        cwd=core,capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
    statuses=json.loads(result.stdout.splitlines()[-1])
    assert [status['alive_workers'] for status in statuses]==[1]*10
    for turn in range(10):
        events=[json.loads(line) for line in (tmp_path/f'state/{turn}/app/games/123/events.jsonl').read_text().splitlines()]
        assert not any(event['kind'] in {'engine_evidence','advice_delivery'} for event in events)
