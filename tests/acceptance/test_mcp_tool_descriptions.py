#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import asyncio

import pytest

pytest.importorskip("mcp")

from mcp.server.mcpserver import MCPServer
from mcp_helpers import call_error as _call_error


class TestToolDescriptionsAreCallerFacing:
    def test_no_description_mentions_python_typing_implementation_details(
        self, app: MCPServer
    ) -> None:
        """Every tool description is copy for the LLM deciding whether to
        call the tool, not a maintainer note about why a return type is
        cast (that rationale now lives once, on `dispatch.run_tool`).
        """
        tools = asyncio.run(app.list_tools())
        leaky_terms = ("cast", "CallToolResult", "return type")
        offenders = {
            tool.name: tool.description
            for tool in tools
            if tool.description and any(term in tool.description for term in leaky_terms)
        }
        assert offenders == {}

    def test_every_parameter_across_every_tool_has_a_description(self, app: MCPServer) -> None:
        tools = asyncio.run(app.list_tools())
        missing = {
            (tool.name, param_name)
            for tool in tools
            for param_name, param_schema in tool.input_schema.get("properties", {}).items()
            if not param_schema.get("description")
        }
        assert missing == set()

    def test_closed_choice_parameters_advertise_an_enum_in_their_schema(
        self, app: MCPServer
    ) -> None:
        tools = {t.name: t for t in asyncio.run(app.list_tools())}
        assert tools["brief"].input_schema["properties"]["scope"]["enum"] == [
            "local",
            "global",
            "all",
        ]
        assert tools["task_add"].input_schema["properties"]["task_type"]["enum"] == [
            "task",
            "bug",
            "feature",
            "epic",
            "chore",
            "spike",
        ]
        assert tools["task_add"].input_schema["properties"]["priority"]["enum"] == [
            "low",
            "medium",
            "high",
            "critical",
        ]


class TestClosedChoiceEnumIsAdvisoryNotEnforced:
    """The `enum` in a closed-choice parameter's schema is a hint for a
    well-behaved host to validate against before sending a call; it must
    not become strict SDK-level validation, which would bypass this
    surface's own clean `UsageError` JSON body (spec §10.2) in favor of a
    raw, differently-shaped protocol error.
    """

    def test_invalid_scope_still_gives_the_clean_usage_error(self, app: MCPServer) -> None:
        error = _call_error(app, "brief", scope="bogus")
        assert error["error"]["code"] == "invalid_scope"

    def test_invalid_task_type_still_gives_the_clean_usage_error(self, app: MCPServer) -> None:
        error = _call_error(app, "task_add", title="t", description="d", task_type="bogus")
        assert error["error"]["code"] == "invalid_type"

    def test_invalid_priority_still_gives_the_clean_usage_error(self, app: MCPServer) -> None:
        error = _call_error(app, "task_add", title="t", description="d", priority="bogus")
        assert error["error"]["code"] == "invalid_priority"
