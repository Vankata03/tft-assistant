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

from tft_capture.lcu import GameflowWatcher
from tft_core.messages import SCHEMA_VERSION
from tft_core.server import CoreServer
from tft_core.storage import SessionStore
from tft_core.runtime import CaptureRuntime, RuntimeSettings
from tft_data import DataStore

log = logging.getLogger("tft_core")


def _stdin_closed(loop: asyncio.AbstractEventLoop) -> asyncio.Event:
    closed = asyncio.Event()

    def wait() -> None:
        sys.stdin.buffer.read()
        loop.call_soon_threadsafe(closed.set)

    threading.Thread(target=wait, name="stdin-watch", daemon=True).start()
    return closed


async def run(token: str, *, sessions=None, data_store=None, settings_path=None,
              watcher_options=None, devices=None, closed=None) -> None:
    """Run the actual server with optional external platform/LCU boundaries."""
    sessions = sessions or SessionStore.default()
    data_store = data_store or DataStore(sessions.root / "snapshots")
    settings_path = settings_path or os.environ.get("TFT_ASSISTANT_SETTINGS") or sessions.config_root / "settings.toml"
    settings, settings_error = None, None
    try:
        settings = RuntimeSettings.load(settings_path)
    except ValueError as error:
        settings_error = str(error)
        log.error("%s", settings_error)
    server = CoreServer(token, sessions=sessions, managed_lifecycle=True)
    runtime = CaptureRuntime(server, sessions, data_store, settings=settings,
        settings_error=settings_error, devices=devices)
    async with server.listen() as ws_server:
        port = ws_server.sockets[0].getsockname()[1]
        print(json.dumps({"event": "ready", "port": port, "v": SCHEMA_VERSION}), flush=True)
        log.info("Core listening on 127.0.0.1:%d", port)
        await runtime.start()
        watcher = asyncio.create_task(GameflowWatcher(runtime.update, **(watcher_options or {})).run())
        try:
            await (closed or _stdin_closed(asyncio.get_running_loop())).wait()
            log.info("Shell closed stdin; finalizing capture")
        finally:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
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
