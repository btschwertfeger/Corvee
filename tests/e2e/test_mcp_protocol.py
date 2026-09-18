#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import asyncio
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from corvee.config import bootstrap_project

_RUN_CLI = "from corvee.cli.main import main; main()"

_EXPECTED_TOOLS = {
    "task_show",
    "brief",
    "task_claim",
    "task_unclaim",
    "task_comment",
    "task_start",
    "task_done",
    "task_cancel",
    "task_review",
    "task_block",
    "task_add",
    "task_search",
    "fact_search",
    "fact_add",
    "fact_verify",
    "fact_show",
}


class TestMcpServeRealProtocolRoundTrip:
    def test_lists_every_registered_tool_and_calls_brief(self, tmp_path: Path) -> None:
        """A real client, over a real stdio subprocess, speaking the actual
        MCP protocol (not app.call_tool() in-process): initialize, list the
        registered tools, and call one -- proving the whole stack wired
        together, not just each piece in isolation.
        """
        bootstrap_project(tmp_path)

        async def _run() -> tuple[list[str], dict[str, object] | None]:
            params = StdioServerParameters(
                command=sys.executable,
                args=["-c", _RUN_CLI, "mcp", "serve", "--project-root", str(tmp_path)],
            )
            async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                result = await session.call_tool("brief", {})
                return [t.name for t in tools.tools], result.structured_content

        tool_names, brief_result = asyncio.run(asyncio.wait_for(_run(), timeout=20))

        assert set(tool_names) == _EXPECTED_TOOLS
        assert brief_result == {"mine": [], "ready": [], "stale": [], "labels": []}
