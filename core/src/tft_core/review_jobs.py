"""Durable, serial review subprocess supervision owned by the core.

Requests survive restart. One child may run at a time, and its job identity comes
from the actual historical review service. Only a successful, validated receipt
may announce a stored review; unavailable outcomes never become placement truth.
"""

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from uuid import uuid4
from datetime import UTC, datetime

from tft_core.engine_runtime import LatestEngineWorker
from tft_core.review_lease import OwnedReviewChildren, JobMutex, atomic_record


def _write(path, value):
    atomic_record(path, value)

class ReviewJobs:
    def __init__(self, sessions, data_store, service, repository, *, ready=None,
                 hard_timeout=600, latency_budget=30, error=None):
        self.sessions, self.data_store, self.service = sessions, data_store, service
        self.repository = Path(repository)
        self.root = sessions.root / 'review-jobs'
        self.requests = self.root / 'requests'
        self.records = self.root / 'jobs'
        # The presentation budget marks late results; only the operational
        # watchdog terminates a child that has not completed.
        self.ready, self.hard_timeout = ready, hard_timeout
        self.latency_budget = latency_budget
        self.error = error
        self.status = 'Review worker waiting for a finalized game'
        self._wake = asyncio.Event()
        self._closed = False
        self._child_shutdown_complete = True
        self._loop = None
        # Server worker threads enqueue while the supervisor marks requests handled.
        self._requests_lock = threading.Lock()
        self._task = None
        self._process = None
        self._future = None
        self._identity = LatestEngineWorker(self._identify, self._identified)
        self.children = OwnedReviewChildren(self.root / 'leases')
        self._blocked = set()

    def _command(self, game_id, job_id):
        return [sys.executable, '-m', 'tft_core.review_worker', game_id,
                '--log-root', str(self.sessions.root),
                '--config-root', str(self.sessions.config_root),
                '--snapshots', str(self.data_store.root),
                '--repository', str(self.repository), '--expected-job-id', job_id]

    def start(self):
        self._loop = asyncio.get_running_loop()
        self.records.mkdir(parents=True, exist_ok=True)
        self.requests.mkdir(parents=True, exist_ok=True)
        self.children.register_owner()
        self._identity.start()
        self._task = asyncio.create_task(self._run(), name='review-job-supervisor')
        self._task.add_done_callback(self._finished)
        self._wake.set()

    def _finished(self, task):
        if self._closed:
            return
        failure = task.exception() if not task.cancelled() else "unexpected cancellation"
        self.status = f"Review supervisor stopped: {failure}"
        if self.error:
            self.error("review_supervisor_failed", self.status)

    def enqueue(self, game_id, *, regenerate=False):
        game_id = str(game_id)
        if not game_id.isdecimal() or int(game_id) <= 0:
            raise ValueError('Review requires a positive game ID')
        game = next((row for row in self.sessions.list_games() if row['game_id'] == game_id), None)
        if not game or not game.get('finished'):
            raise ValueError('Review requires successful capture finalization and game_end')
        if self._closed or (self._task is not None and self._task.done()):
            raise RuntimeError('Review supervisor is closed or stopped')
        path = self.requests / f'{game_id}.json'
        with self._requests_lock:
            pending = json.loads(path.read_text()) if path.exists() else {}
            # A queued manual regeneration is not downgraded by a later ordinary request.
            regenerate = regenerate or (pending.get('state') == 'queued' and pending.get('regenerate', False))
            _write(path, {'game_id': game_id, 'state': 'queued',
                'regenerate': regenerate, 'request_nonce': uuid4().hex})
        if self._loop:
            self._loop.call_soon_threadsafe(self._wake.set)
        else:
            self._wake.set()

    def jobs(self):
        return [json.loads(path.read_text()) for path in self.records.glob('*.json')]

    def _identified(self, game_id, identity, error):
        if self._future and not self._future.done():
            if error:
                self._future.set_exception(ValueError(error))
            else:
                self._future.set_result(identity)

    def _identify(self, game_id):
        identity = self.service.job_identity(game_id)
        end = next(event for event in reversed(self.sessions.read_events(game_id))
                   if event['kind'] == 'game_end')
        return {**identity, 'ended_at': end['timestamp']}

    async def _job_identity(self, game_id):
        self._future = asyncio.get_running_loop().create_future()
        self._identity.submit(game_id)
        return await self._future

    async def _run(self):
        await self._recover()
        while not self._closed:
            await self._wake.wait()
            self._wake.clear()
            # Persisted requests form the durable backlog. No list/task/callback
            # is allocated for every completed game; only one request is selected.
            while not self._closed:
                selected = None
                for path in self.requests.glob('*.json'):
                    request = json.loads(path.read_text())
                    if request['state'] == 'queued':
                        selected = (path, request)
                        break
                if selected is None:
                    break
                path, request = selected
                try:
                    await self._produce(request['game_id'], regenerate=request.get('regenerate', False))
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    self.status = f'Review unavailable: {type(error).__name__}: {error}'
                    request['reason'] = self.status
                    if self.error:
                        self.error('review_unavailable', self.status)
                with self._requests_lock:
                    latest = json.loads(path.read_text())
                    if latest.get('request_nonce') == request.get('request_nonce'):
                        request['state'] = 'handled'
                        _write(path, request)

    async def _recover(self):
        reconciled = await self.children.reconcile()
        self._blocked = {row['job_id'] for row in reconciled if row['state'] == 'blocked'}
        for row in reconciled:
            if row['state'] == 'blocked' and self.error:
                self.error('review_ownership_blocked', row['reason'])
        for path in self.records.glob('*.json'):
            record = json.loads(path.read_text())
            if record['state'] == 'running' and record['job_id'] not in self._blocked:
                reservation = JobMutex(self.children.root, 'schedule-' + record['job_id'])
                if not reservation.acquire():
                    self._blocked.add(record['job_id'])
                    if self.error:
                        self.error('review_ownership_blocked', 'Another core currently owns this review job')
                    continue
                try:
                    record.update(state='interrupted', reason='Core restarted before checked review completion')
                    _write(path, record)
                finally:
                    reservation.close()

    async def _read_bounded(self, stream, maximum):
        chunks, size = [], 0
        while chunk := await stream.read(8192):
            size += len(chunk)
            if size > maximum:
                raise ValueError('Review worker output exceeded its bounded receipt limit')
            chunks.append(chunk)
        return b''.join(chunks)

    async def _produce(self, game_id, *, regenerate=False):
        identity = await self._job_identity(game_id)
        job_id = identity['job_id']
        if not isinstance(job_id, str) or len(job_id) != 64 or any(c not in '0123456789abcdef' for c in job_id):
            raise ValueError('Review service returned an invalid job identity')
        path = self.records / f'{job_id}.json'
        if job_id in self._blocked:
            raise ValueError('Review child ownership is blocked; no duplicate evaluator was launched')
        if not regenerate and path.exists() and json.loads(path.read_text())['state'] in {'completed', 'unavailable'}:
            return
        reservation = JobMutex(self.children.root, 'schedule-' + job_id)
        if not reservation.acquire():
            raise ValueError('Another core currently owns this review job; duplicate evaluation blocked')
        record = {**identity, 'state': 'running', 'owner_nonce': self.children.owner_nonce,
                  'started_at': datetime.now(UTC).isoformat()}
        _write(path, record)
        flags = (subprocess.BELOW_NORMAL_PRIORITY_CLASS | subprocess.CREATE_NO_WINDOW) if os.name == 'nt' else 0
        reads = []
        try:
            command = self.children.command(self._command(game_id, job_id), game_id, job_id)
            environment = dict(os.environ)
            environment.pop('TFT_CORE_TOKEN', None)
            self._process = await asyncio.create_subprocess_exec(*command, env=environment,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                creationflags=flags)
            reads = [asyncio.create_task(self._read_bounded(self._process.stdout, 65536)),
                     asyncio.create_task(self._read_bounded(self._process.stderr, 262144))]
            async with asyncio.timeout(self.hard_timeout):
                output, diagnostic = await asyncio.gather(*reads)
                exit_code = await self._process.wait()
            receipt = json.loads(output)
            if receipt.get('game_id') != game_id or receipt.get('job_id') != job_id:
                raise ValueError('Review worker receipt identity mismatch')
            if receipt.get('status') not in {'review_ready', 'review_unavailable'}:
                raise ValueError('Review worker did not return a completion receipt')
            if exit_code and receipt['status'] != 'review_unavailable':
                raise ValueError(f'Review worker exited {exit_code} without an unavailable receipt')
            if receipt.get('engine_version') != identity['engine_version'] or receipt.get('data_snapshot_id') != identity['data_snapshot_id']:
                raise ValueError('Review worker receipt changed its historical inputs')
            if receipt['status'] == 'review_ready':
                if exit_code:
                    raise ValueError('Review completion receipt has a failed process exit')
                if os.name != 'nt' and receipt.get('priority', {}).get('nice', -1) < 10:
                    raise ValueError('Review worker did not establish below-normal priority')
            # Receipt alone is insufficient: locked reviews deliberately have no
            # detail, but successful service publication must still be retrievable.
            finished = datetime.now(UTC)
            elapsed = (finished - datetime.fromisoformat(record['ended_at'])).total_seconds()
            record.update(state='completed' if receipt['status'] == 'review_ready' else 'unavailable',
                          receipt=receipt, finished_at=finished.isoformat(),
                          latency_seconds=elapsed, late=elapsed > self.latency_budget)
            _write(path, record)
            self.status = 'Review stored' if record['state'] == 'completed' else receipt.get('reason', 'Review unavailable')
            if record['state'] == 'completed' and self.ready:
                await self.ready(game_id)
        except asyncio.CancelledError:
            if record.get('state') in {'completed', 'unavailable'}:
                record.update(delivery_state='interrupted',
                    delivery_reason='Core shutdown interrupted readiness announcement after durable review completion')
            else:
                record.update(state='interrupted', reason='Core shutdown interrupted review; no completion was announced')
            _write(path, record)
            raise
        except Exception as error:
            reason = f'{type(error).__name__}: {error}'
            if record.get('state') in {'completed', 'unavailable'}:
                record.update(delivery_state='failed', delivery_reason=reason)
                self.status = f'Review completion delivery failed: {reason}'
                code = 'review_delivery_failed'
            else:
                record.update(state='failed', reason=reason)
                self.status = f'Review failed: {reason}'
                code = 'review_failed'
            _write(path, record)
            if self.error:
                self.error(code, self.status)
        finally:
            try:
                stopped = await self._stop_child()
                if stopped and 'command' in locals() and self.children.record_path(job_id).exists():
                    self.children.reaped(job_id, command, stopped[0])
            finally:
                for task in reads:
                    if not task.done():
                        task.cancel()
                try:
                    await asyncio.gather(*reads, return_exceptions=True)
                finally:
                    reservation.close()

    async def _stop_child(self):
        process, self._process = self._process, None
        if process is None:
            return None
        if process.returncode is not None:
            return (process.returncode,)
        try:
            process.terminate()
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(process.wait(), .15)
        except TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), .15)
            except TimeoutError:
                self.status = 'Review child shutdown timed out; completion remains unconfirmed'
                self._child_shutdown_complete = False
                self._closed = True
                if self.error:
                    self.error('review_shutdown_timeout', self.status)
                return None
        return (process.returncode,)

    async def shutdown(self):
        self._closed = True
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        stopped = await self._identity.shutdown(timeout=.25)
        if not stopped:
            self.status = 'Review identity shutdown timed out; no result was published'
        self.children.close_owner()
        return stopped and self._child_shutdown_complete
