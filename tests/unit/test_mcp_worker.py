#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import asyncio
import threading
import time

import pytest

from corvee.mcp.worker import DbWorker


class TestDbWorker:
    def test_runs_fn_and_returns_result(self) -> None:
        """A submitted callable's return value comes back to the async caller."""
        worker = DbWorker()
        try:
            result = asyncio.run(worker.run(lambda: 42))
        finally:
            worker.close()
        assert result == 42

    def test_runs_on_a_dedicated_thread_not_the_caller(self) -> None:
        """The callable runs on the worker's own thread, never the calling
        (event loop) thread -- the whole point of offloading blocking sqlite3
        calls off the server's async loop (spec §10.1).
        """
        worker = DbWorker()
        try:
            main_thread_id = threading.get_ident()
            worker_thread_id = asyncio.run(worker.run(threading.get_ident))
        finally:
            worker.close()
        assert worker_thread_id != main_thread_id

    def test_repeated_calls_always_run_on_the_same_thread(self) -> None:
        """Every call goes to the same one dedicated thread, not a pool that
        could hand different calls to different threads.
        """
        worker = DbWorker()
        try:

            async def _main() -> list[int]:
                return [await worker.run(threading.get_ident) for _ in range(5)]

            thread_ids = asyncio.run(_main())
        finally:
            worker.close()
        assert len(set(thread_ids)) == 1

    def test_concurrent_calls_serialize_never_overlap(self) -> None:
        """Two calls submitted concurrently still run one at a time, in full,
        never interleaved -- the property that makes it safe to open/use/close
        one sqlite3 connection per call without cross-thread sharing.
        """
        worker = DbWorker()
        overlap_detected = False
        currently_running = threading.Event()

        def _work(marker: int) -> int:
            nonlocal overlap_detected
            if currently_running.is_set():
                overlap_detected = True
            currently_running.set()
            time.sleep(0.05)
            currently_running.clear()
            return marker

        async def _main() -> list[int]:
            return list(
                await asyncio.gather(worker.run(lambda: _work(1)), worker.run(lambda: _work(2)))
            )

        try:
            results = asyncio.run(_main())
        finally:
            worker.close()
        assert sorted(results) == [1, 2]
        assert not overlap_detected

    def test_exception_in_fn_propagates_to_caller(self) -> None:
        """An exception raised inside the submitted callable propagates to the
        async caller, not swallowed -- handlers rely on this to catch
        CorveeError the same way a direct call would raise it.
        """

        def _boom() -> None:
            raise ValueError("boom")

        worker = DbWorker()
        try:
            with pytest.raises(ValueError, match="boom"):
                asyncio.run(worker.run(_boom))
        finally:
            worker.close()

    def test_close_shuts_down_the_thread(self) -> None:
        """close() shuts the worker thread down; a call submitted afterward
        is rejected rather than silently hanging or spawning a new thread.
        """
        worker = DbWorker()
        asyncio.run(worker.run(lambda: None))
        worker.close()
        with pytest.raises(RuntimeError):
            asyncio.run(worker.run(lambda: None))
