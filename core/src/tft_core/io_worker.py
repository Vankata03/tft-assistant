"""Bounded daemon I/O workers, independent of asyncio's 300-second executor drain.

Cancellation prevents a queued operation from starting and signals in-flight
cooperative publication. Native file calls cannot be killed; a timed-out worker
stays daemon-owned, and permission checks prevent its later graph publication.
"""
import asyncio
import queue
import threading
import time


class OwnedIO:
    def __init__(self, *, workers=2, pending=8):
        self.count=workers
        self.queue=queue.Queue(maxsize=pending)
        self.closed=threading.Event()
        self.threads=[]
        self.jobs={}
        self.loop=None

    def _start(self):
        if self.closed.is_set():raise ValueError('Core I/O is closed')
        if self.loop is None:
            self.loop=asyncio.get_running_loop()
            for index in range(self.count):
                thread=threading.Thread(target=self._run,name=f'tft-io-{index}',daemon=True)
                self.threads.append(thread);thread.start()

    async def call(self,function,*args,cooperative=False,**kwargs):
        self._start()
        future=self.loop.create_future()
        cancelled=threading.Event()
        self.jobs[future]=cancelled
        try:
            self.queue.put_nowait((future,cancelled,function,args,kwargs,cooperative))
        except queue.Full:
            self.jobs.pop(future,None)
            raise ValueError('Core I/O queue is busy; retry this bounded request') from None
        if self.closed.is_set():future.cancel()  # Admitted while closing; workers may already be gone.
        try:return await future
        finally:
            cancelled.set()
            self.jobs.pop(future,None)

    def _run(self):
        while not self.closed.is_set():
            job=self.queue.get()
            if job is None:continue  # Close wakes idle workers without a polling delay.
            future,cancelled,function,args,kwargs,cooperative=job
            if cancelled.is_set() or self.closed.is_set():
                try:self.loop.call_soon_threadsafe(future.cancel)
                except RuntimeError:pass
                continue
            try:
                if cooperative:kwargs=kwargs|{'cancelled':cancelled.is_set}
                value=function(*args,**kwargs);error=None
            except BaseException as caught:
                value=None;error=caught
            def settle(future=future,value=value,error=error):
                if future.done():return
                if error is None:future.set_result(value)
                else:future.set_exception(error)
            try:self.loop.call_soon_threadsafe(settle)
            except RuntimeError:pass  # The owning loop already closed; no late publication.

    async def close(self, *, timeout=.25):
        self.closed.set()
        for future,cancelled in tuple(self.jobs.items()):
            cancelled.set();future.cancel()
        discarded=0
        while True:
            try:job=self.queue.get_nowait()
            except queue.Empty:break
            if job is not None:job[0].cancel();discarded+=1
        for _ in self.threads:
            # A request admitted before close may still fill the queue; any
            # queued item wakes a worker, which then observes close and exits.
            try:self.queue.put_nowait(None)
            except queue.Full:break
        deadline=time.monotonic()+timeout
        for thread in self.threads:thread.join(max(0,deadline-time.monotonic()))
        return {'alive_workers':sum(thread.is_alive() for thread in self.threads),'discarded_requests':discarded}
