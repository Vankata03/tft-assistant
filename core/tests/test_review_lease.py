"""Review ownership is checked before any process can be terminated."""

import asyncio
import json
from pathlib import Path
import subprocess
import sys

import psutil


def test_core_reconciles_child_ownership_before_a_busy_store_constructor(tmp_path):
    """A held store gate cannot prevent startup ownership reconciliation."""
    import os
    from tft_core.storage import SessionStore
    from tft_core.review_lease import OwnedReviewChildren, atomic_record

    store = SessionStore(tmp_path / 'logs', tmp_path / 'config', live_installed=False)
    holder_code = '''
import os,sys
with open(sys.argv[1], 'a+b') as stream:
    if os.name == 'nt':
        import msvcrt
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
    print('held', flush=True)
    sys.stdin.readline()
'''
    holder = subprocess.Popen([sys.executable, '-c', holder_code,
        str(store.root / '.session-store.lock')], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    lease = OwnedReviewChildren(store.root / 'review-jobs/leases').record_path('a' * 64)
    observed = psutil.Process(holder.pid)
    atomic_record(lease, {'schema_version': 1, 'kind': 'tft-review-child',
        'job_id': 'a' * 64, 'game_id': '901', 'state': 'running',
        'launch_nonce': 'b' * 32, 'owner_nonce': 'c' * 32,
        'owner': {'pid': 99999999, 'created_at': 1, 'command': []},
        'pid': holder.pid, 'created_at': observed.create_time(), 'command': observed.cmdline()})
    environment = dict(os.environ, TFT_ASSISTANT_DATA_ROOT=str(store.root),
        TFT_ASSISTANT_CONFIG_ROOT=str(store.config_root))
    startup_code = '''
import asyncio
from tft_core.app import run
try:
    asyncio.run(run('temporary-test-auth'))
except TimeoutError:
    print('store-busy', flush=True)
else:
    raise AssertionError('Held store must remain guarded')
'''
    try:
        assert holder.stdout.readline().strip() == 'held'
        result = subprocess.run([sys.executable, '-c', startup_code], env=environment,
            capture_output=True, text=True, timeout=5)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == 'store-busy'
        assert json.loads(lease.read_text())['state'] == 'blocked'
        assert holder.poll() is None
    finally:
        holder.communicate('release\n', timeout=5)


def test_unrelated_process_is_never_terminated_by_a_claimed_review_lease(tmp_path):
    from tft_core.review_lease import OwnedReviewChildren

    process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(10)'])
    try:
        observed = psutil.Process(process.pid)
        children = OwnedReviewChildren(tmp_path)
        job_id = 'a' * 64
        path = children.record_path(job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            'schema_version': 1, 'kind': 'tft-review-child', 'job_id': job_id,
            'game_id': '901', 'state': 'running', 'launch_nonce': 'b' * 32,
            'owner_nonce': 'c' * 32, 'owner': {'pid': 99999999, 'created_at': 1, 'command': []},
            'pid': process.pid, 'created_at': observed.create_time(),
            'command': observed.cmdline(),
        }))
        results = asyncio.run(children.reconcile())
        assert results[0]['state'] == 'blocked'
        assert 'identity' in results[0]['reason']
        assert process.poll() is None
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_abrupt_review_owner_death_is_reconciled_before_restart_without_auth_leak(tmp_path):
    import errno
    import os
    import time

    import pytest
    from tests.test_replay_contracts import ROOT, logged_game

    if not hasattr(os, 'mkfifo'):
        pytest.skip('This external filesystem stall is POSIX; Windows ownership needs device qualification')
    sessions, store, data, _ = logged_game(tmp_path)
    parent_code = '''
import asyncio,sys
from pathlib import Path
from tft_core.review_jobs import ReviewJobs
from tft_core.storage import SessionStore
from tft_data import DataStore
from tft_review import ReviewService
async def run():
    sessions=SessionStore(Path(sys.argv[1]),Path(sys.argv[2]),live_installed=True)
    store=DataStore(Path(sys.argv[3]))
    jobs=ReviewJobs(sessions,store,ReviewService(sessions,store,repository=Path(sys.argv[4])),Path(sys.argv[4]))
    jobs.start()
    jobs.enqueue('901')
    print('ready',flush=True)
    await asyncio.Event().wait()
asyncio.run(run())
'''
    environment = dict(os.environ)
    environment['TFT_CORE_TOKEN'] = 'fixture-auth-value-never-printed'
    command = [sys.executable, '-c', parent_code, str(sessions.root),
               str(sessions.config_root), str(store.root), str(ROOT)]
    owner = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, env=environment)
    restarted, writer = None, None
    pointer = store.root / 'current.json'
    original = pointer.read_bytes()
    try:
        assert owner.stdout.readline().strip() == 'ready'
        lease = None
        deadline = time.monotonic() + 5
        child_dir = sessions.root / 'review-jobs/leases/children'
        while time.monotonic() < deadline:
            records = [json.loads(path.read_text()) for path in child_dir.glob('*.json')]
            if records and records[0]['state'] == 'running':
                lease = records[0]
                break
            time.sleep(.002)
        assert lease is not None
        pointer.unlink()
        os.mkfifo(pointer)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                writer = os.open(pointer, os.O_WRONLY | os.O_NONBLOCK)
                break
            except OSError as error:
                assert error.errno == errno.ENXIO
                time.sleep(.005)
        assert writer is not None  # The actual42 child opened the external FIFO.
        child = psutil.Process(lease['pid'])
        auth_present = 'TFT_CORE_TOKEN' in child.environ()
        assert auth_present is False
        assert child.nice() >= 10
        from tft_core.review_lease import OwnedReviewChildren
        observer = OwnedReviewChildren(sessions.root / 'review-jobs/leases')
        still_owned = asyncio.run(observer.reconcile())
        assert still_owned[0]['state'] == 'blocked'
        assert 'live core' in still_owned[0]['reason']
        assert owner.poll() is None
        assert child.is_running()
        lease_path = child_dir / f"{lease['job_id']}.json"
        try:
            for changed_field in ('created_at', 'command', 'launch_nonce', 'owner_nonce'):
                changed = json.loads(json.dumps(lease))
                if changed_field == 'created_at':
                    changed['created_at'] += 1
                elif changed_field == 'command':
                    changed['command'][-1] = 'unrecognized-worker-argument'
                else:
                    changed[changed_field] = ('0' if changed[changed_field][0] != '0' else '1') + changed[changed_field][1:]
                lease_path.write_text(json.dumps(changed))
                refused = asyncio.run(observer.reconcile())
                assert refused[0]['state'] == 'blocked', changed_field
                assert child.is_running(), changed_field
                assert owner.poll() is None, changed_field
        finally:
            lease_path.write_text(json.dumps(lease))
        owner.kill()  # A Popen-owned test parent, not a PID taken from a file.
        owner.wait(timeout=5)
        pointer.unlink()
        pointer.write_bytes(original)
        restarted = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, env=environment)
        assert restarted.stdout.readline().strip() == 'ready'
        deadline = time.monotonic() + 5
        archived = None
        history = sessions.root / 'review-jobs/leases/history'
        while time.monotonic() < deadline:
            path = history / f"{lease['job_id']}.{lease['launch_nonce']}.json"
            if path.exists():
                archived = json.loads(path.read_text())
                if archived['state'] != 'blocked':
                    break
            time.sleep(.005)
        assert archived is not None
        assert archived['state'] == 'interrupted'
        assert 'termination confirmed' in archived['reason']
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            records = [json.loads(path.read_text()) for path in (sessions.root / 'review-jobs/jobs').glob('*.json')]
            if records and records[0]['state'] in {'completed', 'failed', 'unavailable'}:
                break
            time.sleep(.01)
        assert records[0]['state'] == 'completed', records
        assert len(records) == 1
        assert records[0]['receipt']['locked'] is True
    finally:
        if pointer.exists() and not pointer.is_file():
            pointer.unlink()
        if not pointer.exists():
            pointer.write_bytes(original)
        if writer is not None:
            os.close(writer)
        for process in (owner, restarted):
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
