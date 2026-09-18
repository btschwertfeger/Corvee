#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest

from corvee.config import ProjectConfig
from corvee.mcp.server import ServerConfig, build_server

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer


@pytest.fixture
def app(project: ProjectConfig) -> Iterator[MCPServer]:
    """A real MCPServer, with the real tools registered, backed by the
    `project` fixture's database -- built once per test, worker thread
    closed on teardown.

    The `mcp` SDK import stays inside `build_server` (never at this
    conftest's own module level): this file loads for every acceptance
    test's collection, not just the MCP ones, so a top-level `mcp` import
    here would make the whole `tests/acceptance/` directory fail to
    collect in an environment without the optional `corvee[mcp]` extra
    installed, the same reason `mcp/server.py` itself only imports the SDK
    inside `build_server`.
    """
    config = ServerConfig(actor="agent:test", project=project, session_id="sess-server")
    server, worker = build_server(config)
    yield server
    worker.close()
