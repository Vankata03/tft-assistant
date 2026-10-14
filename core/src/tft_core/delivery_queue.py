"""One awaited socket writer with a bounded latest value per state type."""

import asyncio
from collections import OrderedDict
from websockets.exceptions import ConnectionClosed


class ClientWriter:
    def __init__(self, websocket):
        self.websocket = websocket
        self.pending = OrderedDict()
        self.ready = asyncio.Event()
        self.sequence = 0
        self.task = asyncio.create_task(self._run())

    def publish(self, key, value):
        # A blocked send owns only its current bytes. Unsent states replace the
        # previous value of that type rather than accumulate socket writes.
        self.pending[key] = (value, None)
        self.ready.set()

    async def send(self, value):
        future = asyncio.get_running_loop().create_future()
        self.sequence += 1
        self.pending[self.sequence] = (value, future)
        self.ready.set()
        await future

    async def _run(self):
        current = None
        try:
            while True:
                await self.ready.wait()
                while self.pending:
                    _, (value, current) = self.pending.popitem(last=False)
                    await self.websocket.send(value)
                    if current is not None and not current.done():
                        current.set_result(None)
                    current = None
                self.ready.clear()
        except ConnectionClosed as error:
            if current is not None and not current.done():
                current.set_exception(error)
        finally:
            if current is not None and not current.done():
                current.cancel()
            for _, future in self.pending.values():
                if future is not None and not future.done():
                    future.cancel()
            self.pending.clear()

    async def close(self):
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)
