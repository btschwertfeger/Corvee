#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

"""Shared call helpers for the MCP acceptance tests, factored out of the
five test files that each defined their own byte-identical copy.
"""

import asyncio
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult


def call(app: MCPServer, name: str, **kwargs: Any) -> dict[str, Any]:
    """Call a tool and return its structured_content, asserting success.

    A `CorveeError` a handler raises never reaches the caller as a Python
    exception: `run_tool` (§10.2) already converts it into a returned
    `CallToolResult(is_error=True, ...)`, which the SDK's own result
    conversion passes straight back from `call_tool()` -- so error paths
    are asserted with `call_error`, not `pytest.raises`.
    """
    result = asyncio.run(app.call_tool(name, kwargs))
    assert isinstance(result, CallToolResult)
    assert not result.is_error, result.structured_content
    assert result.structured_content is not None
    return result.structured_content


def call_error(app: MCPServer, name: str, **kwargs: Any) -> dict[str, Any]:
    result = asyncio.run(app.call_tool(name, kwargs))
    assert isinstance(result, CallToolResult)
    assert result.is_error, result.structured_content
    assert result.structured_content is not None
    return result.structured_content
