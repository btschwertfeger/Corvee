#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import asyncio

import pytest

pytest.importorskip("mcp")

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, InputRequiredResult

from corvee.cli.context import corvee_context
from corvee.config import ProjectConfig
from corvee.db.tasks import insert_task


class TestInProcessConcurrency:
    def test_concurrent_tool_calls_against_one_server_all_succeed_correctly(
        self, app: MCPServer, project: ProjectConfig
    ) -> None:
        """Several tool calls fired concurrently at one server (the shape a
        single agent conversation making parallel calls, or several tools
        in flight at once, would produce) all serialize correctly on the
        single DB worker thread (§10.1): no SQLITE_BUSY, no lost writes, no
        interleaved corruption. The in-process analogue of §9's existing
        subprocess-based concurrency tests, which never share one process
        and so never exercise this failure mode.
        """
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            task_ids = [insert_task(ctx.conn, title=f"task {i}").id for i in range(10)]

        async def _claim_all() -> list[CallToolResult | InputRequiredResult]:
            return await asyncio.gather(
                *(
                    app.call_tool("task_claim", {"ref": f"TASK-{task_id}", "session_id": "sess-1"})
                    for task_id in task_ids
                )
            )

        results = asyncio.run(_claim_all())

        for result in results:
            assert isinstance(result, CallToolResult)
            assert not result.is_error, result.structured_content

        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            from corvee.db.tasks import require_tasks

            tasks = require_tasks(ctx.conn, task_ids)
        assert all(task.claimed_by == "agent:test" for task in tasks)

    def test_concurrent_fact_adds_all_land_without_loss(self, app: MCPServer) -> None:
        async def _add_all() -> list[CallToolResult | InputRequiredResult]:
            return await asyncio.gather(
                *(
                    app.call_tool("fact_add", {"claim": f"fact number {i}", "session_id": "sess-1"})
                    for i in range(10)
                )
            )

        results = asyncio.run(_add_all())
        claims: set[str] = set()
        for result in results:
            assert isinstance(result, CallToolResult)
            assert not result.is_error, result.structured_content
            assert result.structured_content is not None
            claims.add(result.structured_content["claim"])

        assert claims == {f"fact number {i}" for i in range(10)}
