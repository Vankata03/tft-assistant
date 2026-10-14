"""One bounded review consumer per authenticated client; commands stay responsive."""
import asyncio


class ReviewRequests:
    def __init__(self, handler, *, limit=8):
        self.handler=handler
        self.queue=asyncio.Queue(maxsize=limit)
        self.task=asyncio.create_task(self._run())

    def submit(self,message):
        try:self.queue.put_nowait(message)
        except asyncio.QueueFull:raise ValueError('Review request queue is busy; retry') from None

    async def _run(self):
        while True:
            message=await self.queue.get()
            await self.handler(message)

    async def close(self):
        self.task.cancel()
        await asyncio.gather(self.task,return_exceptions=True)
        while not self.queue.empty():self.queue.get_nowait()
