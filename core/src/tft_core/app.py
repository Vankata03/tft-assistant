"""Entry point of the core process (`uv run tft-core`).

The shell starts the core with a per-launch token in `TFT_CORE_TOKEN` and a
pipe on stdin. The core binds the WebSocket to a free localhost port and
prints one JSON line on stdout, `{"event": "ready", "port": ..., "v": ...}`.
Logs go to stderr. The core exits when stdin closes, so it never outlives the
shell.
"""

import asyncio
import json
import logging
import os
import sys
import threading
from pathlib import Path

from tft_capture.lcu import GameflowWatcher
from tft_core.messages import SCHEMA_VERSION
from tft_core.server import CoreServer
from tft_core.storage import SessionStore
from tft_core.runtime import CaptureRuntime, RuntimeSettings
from tft_core.engine_runtime import EngineRuntime
from tft_core.review_jobs import ReviewJobs
from tft_core.review_lease import OwnedReviewChildren
from tft_review import ReviewService
from tft_data import DataStore

log = logging.getLogger("tft_core")


def _stdin_closed(loop: asyncio.AbstractEventLoop) -> asyncio.Event:
    closed = asyncio.Event()

    def wait() -> None:
        sys.stdin.buffer.read()
        loop.call_soon_threadsafe(closed.set)

    threading.Thread(target=wait, name="stdin-watch", daemon=True).start()
    return closed


async def run(
    token: str,
    *,
    sessions=None,
    data_store=None,
    settings_path=None,
    watcher_options=None,
    devices=None,
    closed=None,
    repository=None,
) -> None:
    """Run the actual server with optional external platform/LCU boundaries."""
    # A previous review child can hold the durable store gate after its core
    # dies. Resolve paths without opening the store, then reconcile only
    # positively identified owned children before construction/rebuild.
    root = sessions.root if sessions is not None else SessionStore.default_locations()[0]
    recovered = await OwnedReviewChildren(root / "review-jobs" / "leases").reconcile()
    ownership_warnings = tuple(
        f"Review child {row['job_id']}: {row['reason']}"
        for row in recovered if row['state'] == 'blocked'
    )
    for warning in ownership_warnings:
        log.error("%s", warning)
    sessions = sessions if sessions is not None else SessionStore.default()
    data_store = data_store or DataStore(sessions.root / "snapshots")
    settings_path = (
        settings_path
        or os.environ.get("TFT_ASSISTANT_SETTINGS")
        or sessions.config_root / "settings.toml"
    )
    settings, settings_error = None, None
    try:
        settings = RuntimeSettings.load(settings_path)
    except ValueError as error:
        settings_error = str(error)
        log.error("%s", settings_error)
    repository = Path(repository or Path(__file__).resolve().parents[3])
    review, review_error = None, None
    try:
        review = ReviewService(sessions, data_store, repository=repository)
    except (OSError, ValueError, RuntimeError) as error:
        review_error = f"Review initialization unavailable: {error}"
        log.exception("Review initialization failed; capture lifecycle remains guarded")
    server = CoreServer(token, sessions=sessions, managed_lifecycle=True, review_service=review)
    runtime = CaptureRuntime(
        server,
        sessions,
        data_store,
        settings=settings,
        settings_error=settings_error,
        devices=devices,
        warnings=(*ownership_warnings, *((review_error,) if review_error else ())),
    )
    engine = EngineRuntime(runtime, server, sessions)
    reviews = ReviewJobs(sessions, data_store, review, repository,
                         ready=server.publish_review_ready, error=server.publish_runtime_error) if review else None

    async def update(gameflow):
        previous = runtime.completed_game
        await runtime.update(gameflow)
        completed = runtime.completed_game
        if completed is not None and completed is not previous:
            try:
                if reviews is None:
                    raise RuntimeError(review_error or "Review supervisor unavailable")
                reviews.enqueue(completed["game_id"])
            except (OSError, ValueError, RuntimeError) as error:
                server.publish_runtime_error("review_enqueue_failed", str(error))

    async with server.listen() as ws_server:
        port = ws_server.sockets[0].getsockname()[1]
        print(
            json.dumps({"event": "ready", "port": port, "v": SCHEMA_VERSION}),
            flush=True,
        )
        log.info("Core listening on 127.0.0.1:%d", port)
        await runtime.start()
        engine.start()
        if reviews is not None:
            try:
                reviews.start()
            except (OSError, ValueError, RuntimeError) as error:
                review_error = f"Review supervision unavailable: {error}"
                server.publish_runtime_error("review_start_failed", review_error)
                runtime.warnings = (*runtime.warnings, review_error)
                await reviews.shutdown()
                reviews = None
        watcher = asyncio.create_task(
            GameflowWatcher(update, **(watcher_options or {})).run(), name="gameflow-watcher"
        )
        closing = asyncio.create_task(
            (closed or _stdin_closed(asyncio.get_running_loop())).wait(), name="shell-close-wait"
        )
        try:
            done, _ = await asyncio.wait((closing, watcher), return_when=asyncio.FIRST_COMPLETED)
            if watcher in done and closing not in done:
                failure = watcher.exception() if not watcher.cancelled() else "unexpected cancellation"
                server.publish_runtime_error("watcher_failed", f"Gameflow watcher stopped: {failure}")
                raise RuntimeError(f"Gameflow watcher stopped: {failure}")
            log.info("Shell closed stdin; finalizing capture")
        finally:
            watcher.cancel()
            closing.cancel()
            await asyncio.gather(watcher, closing, return_exceptions=True)
            if not await engine.shutdown():
                server.publish_runtime_error("engine_shutdown_timeout", engine.status)
            if reviews is not None and not await reviews.shutdown():
                server.publish_runtime_error("review_shutdown_timeout", reviews.status)
            io_status=await server.shutdown_io(timeout=.25)
            log.info('Owned I/O shutdown status: %s',io_status)
            await runtime.shutdown()
            log.info("Capture shutdown status: %s", runtime.status)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    token = os.environ.get("TFT_CORE_TOKEN")
    if not token:
        sys.exit("TFT_CORE_TOKEN is not set; the shell starts the core")
    asyncio.run(run(token))


if __name__ == "__main__":
    main()
