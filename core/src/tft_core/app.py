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

log = logging.getLogger("tft_core")


def _stdin_closed(loop: asyncio.AbstractEventLoop) -> asyncio.Event:
    closed = asyncio.Event()

    def wait() -> None:
        sys.stdin.buffer.read()
        loop.call_soon_threadsafe(closed.set)

    threading.Thread(target=wait, name="stdin-watch", daemon=True).start()
    return closed


async def run(token: str) -> None:
    server = CoreServer(token, sessions=SessionStore.default())
    async with server.listen() as ws_server:
        port = ws_server.sockets[0].getsockname()[1]
        print(json.dumps({"event": "ready", "port": port, "v": SCHEMA_VERSION}), flush=True)
        log.info("Core listening on 127.0.0.1:%d", port)
        watcher = asyncio.create_task(GameflowWatcher(server.publish_gameflow).run())
        await _stdin_closed(asyncio.get_running_loop()).wait()
        log.info("Shell closed stdin; exiting")
        watcher.cancel()


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
