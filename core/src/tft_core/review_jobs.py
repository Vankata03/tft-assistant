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
from datetime import UTC, datetime
from time import time
from hashlib import sha256

from tft_core.engine_runtime import LatestEngineWorker
from tft_core.review_lease import OwnedReviewChildren, JobMutex, atomic_record
from tft_core.outcomes import OutcomeCollector


def _write(path, value):
    atomic_record(path, value)

class ReviewJobs:
    def __init__(self, sessions, data_store, service, repository, *, ready=None,
                 hard_timeout=600, latency_budget=30, error=None,
                 outcome_retry_seconds=30):
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
        self.outcomes = OutcomeCollector(sessions)
        self.outcome_retry_seconds = outcome_retry_seconds
        self.status = 'Review worker waiting for a finalized game'
        self._wake = asyncio.Event()
        self._closed = False
        self._child_shutdown_complete = True
        self._task = None
        self._process = None
        self._launches = set()
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

    def enqueue(self, game_id):
        game_id = str(game_id)
        if not game_id.isdecimal() or int(game_id) <= 0:
            raise ValueError('Review requires a positive game ID')
        game = next((row for row in self.sessions.list_games() if row['game_id'] == game_id), None)
        if not game or not game.get('finished'):
            raise ValueError('Review requires successful capture finalization and game_end')
        if self._closed or (self._task is not None and self._task.done()):
            raise RuntimeError('Review supervisor is closed or stopped')
        _write(self.requests / f'{game_id}.json', {'game_id': game_id, 'state': 'queued'})
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
            try:
                await asyncio.wait_for(self._wake.wait(), self.outcome_retry_seconds)
            except TimeoutError:
                pass
            self._wake.clear()
            # Persisted requests form the durable backlog. No list/task/callback
            # is allocated for every completed game; only one request is selected.
            while not self._closed:
                selected = None
                for path in self.requests.glob('*.json'):
                    request = json.loads(path.read_text())
                    if request['state'] == 'queued' and request.get('outcome_retry_at', 0) <= time():
                        selected = (path, request)
                        break
                if selected is None:
                    break
                path, request = selected
                try:
                    await self._produce(request['game_id'])
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    self.status = f'Review unavailable: {type(error).__name__}: {error}'
                    request['reason'] = self.status
                    if self.error:
                        self.error('review_unavailable', self.status)
                # Preserve an on-demand request accepted while this job ran.
                latest = json.loads(path.read_text())
                if latest.get('request_nonce') != request.get('request_nonce'):
                    continue
                request['state'] = 'handled'
                outcome = self.outcomes.status(request['game_id'])
                if outcome is not None:
                    request['outcome_state'] = outcome['state']
                    request.pop('outcome_reason', None)
                    request['outcome_attempts'] = request.get('outcome_attempts', 0) + 1
                    if outcome['state'] == 'pending' and request['outcome_attempts'] < 10:
                        request.update(state='queued', regenerate=False,
                            outcome_retry_at=time() + self.outcome_retry_seconds)
                    if outcome['state'] != 'confirmed':
                        reason = outcome['reason']
                        if outcome['state'] == 'pending' and request['state'] == 'handled':
                            reason = 'Outcome retry limit reached; check owner match API and regenerate review to retry'
                        request['outcome_reason'] = reason
                        if self.error and outcome.get('configured'):
                            self.error('outcome_unavailable', reason)
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

    async def _launch_child(self, command, environment, flags):
        revoked = False
        async def spawn():
            process = await asyncio.create_subprocess_exec(*command, env=environment,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, creationflags=flags)
            if revoked:
                stopped = await self._stop_process(process)
                if stopped:
                    self.children.reaped(command[command.index('--job-id') + 1], command, stopped[0])
                raise asyncio.CancelledError()
            self._process = process
            self.children.launch_state(command, 'active')
            return process
        launch = asyncio.create_task(spawn())
        self._launches.add(launch)
        def finished(task):
            self._launches.discard(task)
            if not task.cancelled():
                task.exception()
        launch.add_done_callback(finished)
        try:
            await asyncio.shield(launch)
        except asyncio.CancelledError:
            revoked = True
            self.children.launch_state(command, 'revoked')
            launch.cancel()
            _, pending = await asyncio.wait({launch}, timeout=.15)
            if pending:
                job_id = command[command.index('--job-id') + 1]
                self._blocked.add(job_id)
                self.children.launch_state(command, 'blocked')
                if self.error:
                    self.error('review_launch_blocked', 'Process startup cancellation remains unconfirmed; late child admission is blocked')
            raise

    async def _produce(self, game_id):
        await self._collect_outcome(game_id)
        if self._closed:
            return
        # Collection can change the historical review identity. Compute it only
        # after the owned preflight has exited and its final facts are durable.
        identity = await self._job_identity(game_id)
        job_id = identity['job_id']
        if not isinstance(job_id, str) or len(job_id) != 64 or any(c not in '0123456789abcdef' for c in job_id):
            raise ValueError('Review service returned an invalid job identity')
        path = self.records / f'{job_id}.json'
        if job_id in self._blocked:
            raise ValueError('Review child ownership is blocked; no duplicate evaluator was launched')
        if path.exists() and json.loads(path.read_text())['state'] in {'completed', 'unavailable'}:
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
            async with asyncio.timeout(self.hard_timeout):
                await self._launch_child(command, environment, flags)
                reads = [asyncio.create_task(self._read_bounded(self._process.stdout, 65536)),
                         asyncio.create_task(self._read_bounded(self._process.stderr, 262144))]
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

    async def _collect_outcome(self, game_id):
        configured = (self.sessions.config_root/'outcome-source.json').exists() or self.sessions.run is not None
        confirmed = self.sessions.read_outcome(game_id) is not None
        if confirmed or not configured:
            previous = self.outcomes.status(game_id) or {}
            _write(self.sessions.root/'outcome-status'/f'{game_id}.json', {
                'game_id': game_id, 'attempts': previous.get('attempts', 0) + 1,
                'configured': configured, 'state': 'confirmed' if confirmed else 'unavailable',
                'reason': None if confirmed else 'Configure private outcome-source.json with owner_puuid, platform and region, or start the EUNE run'})
            return
        job_id = sha256(f'outcome:{self.sessions.root.resolve()}:{game_id}'.encode()).hexdigest()
        if job_id in self._blocked:
            raise ValueError('Outcome child ownership is blocked')
        reservation = JobMutex(self.children.root, 'schedule-' + job_id)
        if not reservation.acquire():
            raise ValueError('Another core owns this outcome collection')
        reads = []
        command = None
        try:
            command = self.children.command(self._command(game_id, job_id) + ['--collect-outcome'], game_id, job_id)
            environment = dict(os.environ)
            environment.pop('TFT_CORE_TOKEN', None)
            flags = (subprocess.BELOW_NORMAL_PRIORITY_CLASS | subprocess.CREATE_NO_WINDOW) if os.name == 'nt' else 0
            async with asyncio.timeout(self.hard_timeout):
                await self._launch_child(command, environment, flags)
                reads = [asyncio.create_task(self._read_bounded(self._process.stdout, 65536)),
                         asyncio.create_task(self._read_bounded(self._process.stderr, 262144))]
                output, diagnostic = await asyncio.gather(*reads)
                exit_code = await self._process.wait()
            receipt = json.loads(output)
            if (exit_code or receipt.get('status') != 'outcome_collected'
                or receipt.get('game_id') != game_id or receipt.get('job_id') != job_id):
                raise ValueError('Outcome worker did not return a checked collection receipt')
        except Exception as error:
            # Stop/reap before publishing retry status. No detached worker can
            # subsequently replace it or publish truth after shutdown returns.
            stopped = await self._stop_child()
            if stopped and command and self.children.record_path(job_id).exists():
                self.children.reaped(job_id, command, stopped[0])
            previous = self.outcomes.status(game_id) or {}
            _write(self.sessions.root/'outcome-status'/f'{game_id}.json', {
                'game_id': game_id, 'attempts': previous.get('attempts', 0) + 1,
                'configured': (self.sessions.config_root/'outcome-source.json').exists() or self.sessions.run is not None,
                'state': 'pending', 'reason': f'Outcome collection {type(error).__name__}; retry pending'})
        finally:
            try:
                stopped = await self._stop_child()
                if stopped and command and self.children.record_path(job_id).exists():
                    self.children.reaped(job_id, command, stopped[0])
            finally:
                for task in reads:
                    task.cancel()
                await asyncio.gather(*reads, return_exceptions=True)
                reservation.close()

    async def _stop_child(self):
        process = self._process
        if process is None:
            return None
        stopped = await self._stop_process(process)
        if stopped:
            self._process = None
        return stopped

    async def _stop_process(self, process):
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
        launches = set(self._launches)
        if launches:
            await asyncio.wait(launches, timeout=.3)
        stopped = await self._identity.shutdown(timeout=.25)
        if not stopped:
            self.status = 'Review identity shutdown timed out; no result was published'
        self.children.close_owner()
        return stopped and self._child_shutdown_complete and not self._launches
