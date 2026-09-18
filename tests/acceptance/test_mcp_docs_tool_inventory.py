#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import asyncio
import re
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp.server.mcpserver import MCPServer

DOCS_MCP_PATH = Path(__file__).parents[2] / "docs" / "mcp.md"
_TABLE_ROW_RE = re.compile(r"^\| `(\w+)` \|")


def _documented_tool_names() -> set[str]:
    """The tool names listed in docs/mcp.md's own tool table -- parsed from
    the doc itself, not a second hardcoded copy of the list, so this test
    can never itself drift from what the doc says (TASK-34: the tool
    inventory was hardcoded in 4 places -- this doc's table, its own
    "Sixteen tools" count, the server's own INSTRUCTIONS string, and
    tests/e2e/test_mcp_protocol.py's _EXPECTED_TOOLS -- with only the last
    one checked against the live server).
    """
    names: set[str] = set()
    in_table = False
    for line in DOCS_MCP_PATH.read_text().splitlines():
        if line.startswith("| Tool | Writes?"):
            in_table = True
            continue
        if not in_table:
            continue
        match = _TABLE_ROW_RE.match(line)
        if match:
            names.add(match.group(1))
        elif line.strip() and not line.startswith("|"):
            break
    return names


class TestDocsToolTableMatchesTheLiveServer:
    def test_every_documented_tool_is_registered_and_vice_versa(self, app: MCPServer) -> None:
        documented = _documented_tool_names()
        registered = {tool.name for tool in asyncio.run(app.list_tools())}
        assert documented == registered

    def test_the_stated_tool_count_matches_the_table(self) -> None:
        """ "Sixteen tools" (docs/mcp.md) and "Sixteen tools" (docs/spec.md
        §10.3) are prose, not something a test can parse out of context
        reliably across both files -- this at least ties docs/mcp.md's own
        count claim to its own table, so a future 17th tool added to the
        table without updating the word "Sixteen" fails loudly here.
        """
        text = DOCS_MCP_PATH.read_text()
        match = re.search(r"^(\w+) tools,", text, re.MULTILINE)
        assert match is not None, "docs/mcp.md's tool-count sentence not found"
        word_to_count = {
            "Eleven": 11,
            "Twelve": 12,
            "Thirteen": 13,
            "Fourteen": 14,
            "Fifteen": 15,
            "Sixteen": 16,
            "Seventeen": 17,
            "Eighteen": 18,
            "Nineteen": 19,
            "Twenty": 20,
        }
        stated_count = word_to_count.get(match.group(1))
        assert stated_count is not None, f"unrecognized count word {match.group(1)!r}"
        assert stated_count == len(_documented_tool_names())
