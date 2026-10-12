"""Nonblocking refresh scheduling with publication on the core event loop."""

import asyncio
import threading

from .models import RefreshResult


class RefreshCoordinator:
    def __init__(self, store, patch_dir, **refresh_options):
        self.store = store
        self.patch_dir = patch_dir
        self.options = refresh_options
        self.in_game = False
        self.task = None
        self.last_result = RefreshResult(store.current)

    def set_in_game(self, value):
        self.in_game = bool(value)
        if not self.in_game:
            self.last_result = self.store.publish_pending()
        # Capture stores this object at game start; later refreshes never mutate it.
        return self.store.current

    def trigger(self, reason):
        """Start, Lobby and game end launch checks; queueing never waits on IO."""
        if self.in_game or reason not in {"startup", "Lobby", "end-of-game"}:
            return None
        if self.task is not None and not self.task.done():
            return self.task
        self.task = asyncio.create_task(self._run(reason))
        return self.task

    async def _run(self, reason):
        # Network IO cannot be cancelled by cancelling an asyncio executor
        # future. A dedicated daemon keeps an interrupted refresh from holding
        # process teardown; it may only stage a candidate, never publish it.
        loop = asyncio.get_running_loop()
        result_future = loop.create_future()

        def deliver(result=None, error=None):
            if result_future.done():
                return
            if error:
                result_future.set_exception(error)
            else:
                result_future.set_result(result)

        def fetch():
            result, error = None, None
            try:
                result = self.store.refresh(
                    self.patch_dir,
                    trigger=reason,
                    can_publish=lambda: not self.in_game,
                    defer_publication=True,
                    **self.options,
                )
            except Exception as caught:
                error = caught
            try:
                if not loop.is_closed():
                    loop.call_soon_threadsafe(deliver, result, error)
            except RuntimeError:
                pass  # Shutdown has already reported the interrupted refresh.

        threading.Thread(target=fetch, name="tft-data-refresh", daemon=True).start()
        result = await result_future
        if not self.in_game:
            published = self.store.publish_pending()
            if published.changed:
                result = published
        self.last_result = result
        return result

    async def wait(self):
        if self.task is not None:
            return await self.task
        return self.last_result
