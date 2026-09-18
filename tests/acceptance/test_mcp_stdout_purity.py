#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import asyncio

import pytest

pytest.importorskip("mcp")

from corvee.config import ProjectConfig
from corvee.mcp.server import build_server
from corvee.mcp.server_config import ServerConfig


class TestStdoutPurity:
    def test_a_tool_call_writes_nothing_to_stdout(
        self, project: ProjectConfig, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """§10.2 calls stdout the one hard blocker for a stdio transport: any
        stray print() would corrupt JSON-RPC framing. A handler call must
        write nothing to stdout -- pinned directly here, not just inferred
        from the e2e protocol test not crashing.
        """
        config = ServerConfig(actor="agent:test", project=project, session_id="sess-server")
        server, worker = build_server(config)
        try:
            asyncio.run(server.call_tool("brief", {}))
        finally:
            worker.close()

        captured = capsys.readouterr()
        assert captured.out == ""
