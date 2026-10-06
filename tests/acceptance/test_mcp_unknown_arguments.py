#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import pytest

pytest.importorskip("mcp")

from mcp.server.mcpserver import MCPServer
from mcp_helpers import call as _call
from mcp_helpers import call_error as _call_error

from corvee.cli.context import corvee_context
from corvee.config import ProjectConfig
from corvee.db.tasks import insert_task


@pytest.fixture
def task_id(project: ProjectConfig) -> str:
    with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
        task = insert_task(ctx.conn, title="a task")
    return f"TASK-{task.id}"


class TestUnknownArguments:
    def test_typoed_argument_on_a_write_tool_is_rejected_without_writing(
        self, app: MCPServer, task_id: str
    ) -> None:
        error = _call_error(app, "task_claim", ref=task_id, forc=True)
        assert error["error"]["code"] == "unknown_argument"
        assert error["error"]["exit_code"] == 2
        assert "forc" in error["error"]["message"]
        for valid in ("ref", "session_id", "force"):
            assert valid in error["error"]["message"]
        assert _call(app, "task_show", ref=task_id)["claimed_by"] is None

    def test_unknown_argument_on_a_read_tool_is_rejected(
        self, app: MCPServer, task_id: str
    ) -> None:
        error = _call_error(app, "task_show", ref=task_id, bogus=1)
        assert error["error"]["code"] == "unknown_argument"
        assert error["error"]["exit_code"] == 2

    def test_hyphenated_session_id_is_rejected(self, app: MCPServer, task_id: str) -> None:
        error = _call_error(app, "task_claim", ref=task_id, **{"session-id": "sess-1"})
        assert error["error"]["code"] == "unknown_argument"
        assert "session-id" in error["error"]["message"]

    def test_every_unknown_key_is_named(self, app: MCPServer, task_id: str) -> None:
        error = _call_error(app, "task_show", ref=task_id, one=1, two=2)
        assert "one" in error["error"]["message"]
        assert "two" in error["error"]["message"]

    def test_force_is_ignored_on_a_transition_tool_but_other_unknowns_still_fail(
        self, app: MCPServer, task_id: str
    ) -> None:
        assert _call(app, "task_start", ref=task_id, force=True)["state"] == "in_progress"
        error = _call_error(app, "task_done", ref=task_id, force=True, bogus=1)
        assert error["error"]["code"] == "unknown_argument"
        assert "bogus" in error["error"]["message"]
