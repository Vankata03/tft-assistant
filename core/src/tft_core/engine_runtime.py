"""Bounded latest-value Engine work on one owned daemon thread.

The event loop supplies immutable requests and owns publication. A slow evaluation
can retain one current request and one latest pending request; capture never waits
for evaluation. Shutdown invalidates all results before waiting for the thread.
"""

import asyncio
import threading
import time


class LatestEngineWorker:
    def __init__(self, evaluate, deliver):
        self.evaluate, self.deliver = evaluate, deliver
        self._condition = threading.Condition()
        self._pending = None
        self._closed = False
        self._loop = None
        self._thread = None
        self._result = None
        self._result_scheduled = False

    def start(self):
        if self._thread is not None:
            return
        self._loop = asyncio.get_running_loop()
        self._thread = threading.Thread(target=self._run, name='engine-latest', daemon=True)
        self._thread.start()

    def submit(self, request):
        with self._condition:
            if self._closed:
                return False
            self._pending = request
            self._condition.notify()
            return True

    def _run(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._closed or self._pending is not None)
                if self._closed:
                    return
                request, self._pending = self._pending, None
            result, error = None, None
            try:
                result = self.evaluate(request)
            except Exception as failure:
                error = f'{type(failure).__name__}: {failure}'
            with self._condition:
                if self._closed:
                    return
                self._result = (request, result, error)
                if self._result_scheduled:
                    continue
                self._result_scheduled = True
            try:
                self._loop.call_soon_threadsafe(self._drain)
            except RuntimeError:
                return

    def _drain(self):
        with self._condition:
            value, self._result = self._result, None
            self._result_scheduled = False
            closed = self._closed
        if value is not None and not closed:
            self.deliver(*value)

    async def shutdown(self, *, timeout=.25):
        with self._condition:
            self._closed = True
            self._pending = self._result = None
            self._condition.notify_all()
        deadline = time.monotonic() + timeout
        while self._thread and self._thread.is_alive() and time.monotonic() < deadline:
            await asyncio.sleep(.005)
        if self._thread and not self._thread.is_alive():
            self._thread.join(timeout=0)
        return self._thread is None or not self._thread.is_alive()


class EngineRuntime:
    """Join the sole capture lifecycle to optional Live evaluation and publication."""

    def __init__(self, capture, server, sessions):
        self.capture, self.server, self.sessions = capture, server, sessions
        self.worker = LatestEngineWorker(self._evaluate, self._delivery)
        self._consumer = None
        self._publish = None
        self._closed = False
        self._advisor = None
        self.status = 'Engine waiting for an installed Live session'

    def start(self):
        self.worker.start()
        self._consumer = asyncio.create_task(self._consume(), name='engine-capture-consumer')
        self._consumer.add_done_callback(self._finished)

    def _finished(self, task):
        if self._closed:
            return
        failure = task.exception() if not task.cancelled() else "unexpected cancellation"
        self.status = f"Engine capture consumer stopped: {failure}"
        self.server.publish_runtime_error("engine_consumer_failed", self.status)

    def _identity(self):
        import json

        return (self.capture.publication_generation, self.sessions.active_game_id,
                self.sessions.mode.value,
                self.capture.pinned_data.snapshot_id if self.capture.pinned_data else None,
                json.dumps(self.server.live.pin_schedule, sort_keys=True), self.server.live.epoch)

    def _allowed(self):
        snapshot = self.capture.latest_snapshot
        return (not self._closed and self.sessions.live_installed
                and self.sessions.mode.value == 'live'
                and self.capture.pinned_data is not None and snapshot is not None
                and snapshot.get('game_id') == self.sessions.active_game_id
                and snapshot.get('capture_status', {}).get('state') == 'capturing')

    async def _consume(self):
        while not self._closed:
            try:
                snapshot = await self.capture.next_snapshot()
            except asyncio.QueueShutDown:
                return
            if not self._allowed():
                continue
            # Decode/freeze before dispatch; mutable capture/UI objects never cross
            # into evaluation. A pin is a current observed UI choice, not OCR truth.
            from dataclasses import replace
            from datetime import datetime
            from tft_engine import FieldValue, GameSnapshot

            try:
                frozen = GameSnapshot.from_dict(snapshot)
                pin = self.server.live.pin_schedule
                read_at = self.server.live.pin_read_at
                if pin is not None and read_at is not None:
                    read_at = datetime.fromisoformat(read_at) if isinstance(read_at, str) else read_at
                    if read_at <= frozen.captured_at:
                        frozen = replace(frozen, fields={**frozen.fields,
                            'pinned_line': FieldValue(pin, read_at, 'ui_pin')})
                self.worker.submit((self._identity(), frozen, self.capture.pinned_data))
            except (ValueError, KeyError, TypeError) as error:
                self.status = f'Engine capture unavailable: {error}'
                self.server.publish_runtime_error('engine_capture_unavailable', self.status)

    def _evaluate(self, request):
        import importlib
        from tft_review.contracts import history_prefix

        identity, snapshot, data = request
        # Read storage on this dedicated thread. The causal prefix excludes the
        # current frame, later observations and any observations before a gap.
        events = self.sessions.read_events(snapshot.game_id)
        current = next((event['seq'] for event in events if event['kind'] == 'snapshot'
                        and event['payload'].get('snapshot_id') == snapshot.snapshot_id), None)
        if current is None:
            raise ValueError('Engine snapshot has no committed capture observation')
        history = history_prefix(events, through_seq=current - 1,
                                 captured_at=snapshot.captured_at.isoformat())
        if self._advisor is None:
            self._advisor = importlib.import_module('tft_live.advisor').LiveAdvisor()
        return self._advisor.evaluate(snapshot, history, data, mode=identity[2])

    def _delivery(self, request, delivery, error):
        if not self._allowed() or request[0] != self._identity():
            return
        if error:
            self.status = f'Engine evaluation unavailable: {error}'
            self.server.live.clear(self.status)
            self.server.publish_live_status()
            return
        if delivery is None:
            return
        # At most one publication task waits on owned I/O. A newer result replaces
        # its predecessor rather than accumulating a task per capture frame.
        if self._publish and not self._publish.done():
            self._publish.cancel()
        self._publish = asyncio.create_task(self._publish_delivery(request, delivery),
                                            name='engine-live-publication')

    async def _publish_delivery(self, request, delivery):
        try:
            if self._allowed() and request[0] == self._identity():
                await self.server.publish_live_async(delivery)
                self.status = 'Engine advice delivered'
        except (OSError, ValueError, RuntimeError) as error:
            self.status = f'Engine publication unavailable: {error}'
            self.server.live.clear(self.status)
            self.server.publish_live_status()

    async def shutdown(self, *, timeout=.25):
        self._closed = True
        for task in (self._consumer, self._publish):
            if task and not task.done():
                task.cancel()
        await asyncio.gather(*(task for task in (self._consumer, self._publish) if task),
                             return_exceptions=True)
        finished = await self.worker.shutdown(timeout=timeout)
        if not finished:
            self.status = 'Engine shutdown timed out; its delayed result was rejected'
        return finished
