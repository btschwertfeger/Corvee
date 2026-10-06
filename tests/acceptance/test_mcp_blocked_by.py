#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import pytest

pytest.importorskip("mcp")

from click.testing import CliRunner
from mcp.server.mcpserver import MCPServer
from mcp_helpers import call as _call

from corvee.cli.main import cli
from corvee.config import ProjectConfig


class TestBlockedBy:
    def test_task_show_and_search_carry_blocked_by(
        self, app: MCPServer, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """MCP keeps the stored `state` and reports open blockers in `blocked_by`."""
        for title in ("blocker", "waiting"):
            runner.invoke(cli, ["task", "add", title, "--description", "d"])
        runner.invoke(cli, ["task", "link", "TASK-1", "TASK-2", "--relation", "blocks"])

        shown = _call(app, "task_show", ref="TASK-2")
        assert shown["blocked_by"] == ["TASK-1"]
        assert shown["state"] == "open"
        found = _call(app, "task_search", text="waiting")
        assert found["result"][0]["blocked_by"] == ["TASK-1"]
