#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")


class DbWorker:
    """One dedicated thread that every one of the MCP server's SQLite calls
    runs on, for the server process's whole lifetime -- never a
    thread-per-call pool (spec §10.1).

    `open_connection` connects with sqlite3's default `check_same_thread=True`,
    so a connection must be created, used, and closed on the same thread; a
    thread-per-call pool would also reintroduce real SQLITE_BUSY/
    SQLITE_BUSY_SNAPSHOT contention between concurrent tool calls in the same
    process, the exact case §3.2 only ever accepted `busy_timeout` as
    sufficient for at CLI-process granularity. A single worker thread makes
    both non-issues: two tool calls in the same session simply queue behind
    each other, which is cheap at this scale, and the server's own async
    event loop never blocks on DB work, only on this thread's queue.
    """

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="corvee-mcp-db")

    async def run(self, fn: Callable[[], T]) -> T:
        """Run `fn` on the dedicated thread and await its result.

        `fn` takes no arguments -- callers close over whatever a specific
        call needs (e.g. `lambda: apply_update(conn, task_id, actor, ...)`),
        keeping this method's own signature independent of any one handler's
        argument shape.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, fn)

    def close(self) -> None:
        """Shut the worker thread down. A call submitted afterward is
        rejected (`RuntimeError`) rather than silently hanging or spawning a
        replacement thread.
        """
        self._executor.shutdown(wait=True)
