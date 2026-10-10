"""Nonblocking refresh scheduling with publication on the core event loop."""

import asyncio

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
        result = await asyncio.to_thread(
            self.store.refresh,
            self.patch_dir,
            trigger=reason,
            can_publish=lambda: not self.in_game,
            defer_publication=True,
            **self.options,
        )
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
