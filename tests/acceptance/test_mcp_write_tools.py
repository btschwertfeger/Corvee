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
from corvee.mcp.server import build_server
from corvee.mcp.server_config import ServerConfig


@pytest.fixture
def task_id(project: ProjectConfig) -> str:
    with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
        task = insert_task(ctx.conn, title="a task")
    return f"TASK-{task.id}"


class TestTaskClaim:
    def test_claims_the_task(self, app: MCPServer, task_id: str) -> None:
        result = _call(app, "task_claim", ref=task_id, session_id="sess-1")
        assert result["claimed_by"] == "agent:test"

    def test_conflict_with_another_claimant_gives_a_claim_conflict_error(
        self, app: MCPServer, task_id: str
    ) -> None:
        with corvee_context(scope="local", actor="agent:other", session_id=None) as ctx:
            from corvee.db.tasks import claim_task

            claim_task(ctx.conn, int(task_id.removeprefix("TASK-")), "agent:other")

        error = _call_error(app, "task_claim", ref=task_id, session_id="sess-1")
        assert error["error"]["code"] == "claim_conflict"
        assert error["error"]["exit_code"] == 4
        assert error["error"]["hint"] == (
            "call task_claim(force=true) on this ref to steal the claim, then retry"
        )

    def test_force_steals_the_claim(self, app: MCPServer, task_id: str) -> None:
        with corvee_context(scope="local", actor="agent:other", session_id=None) as ctx:
            from corvee.db.tasks import claim_task

            claim_task(ctx.conn, int(task_id.removeprefix("TASK-")), "agent:other")

        result = _call(app, "task_claim", ref=task_id, force=True, session_id="sess-1")
        assert result["claimed_by"] == "agent:test"


class TestTaskUnclaim:
    def test_releases_own_claim(self, app: MCPServer, task_id: str) -> None:
        _call(app, "task_claim", ref=task_id, session_id="sess-1")
        result = _call(app, "task_unclaim", ref=task_id, session_id="sess-1")
        assert result["claimed_by"] is None

    def test_someone_elses_claim_without_force_conflicts(
        self, app: MCPServer, task_id: str
    ) -> None:
        with corvee_context(scope="local", actor="agent:other", session_id=None) as ctx:
            from corvee.db.tasks import claim_task

            claim_task(ctx.conn, int(task_id.removeprefix("TASK-")), "agent:other")

        error = _call_error(app, "task_unclaim", ref=task_id, session_id="sess-1")
        assert error["error"]["code"] == "claim_conflict"

    def test_force_releases_someone_elses_stale_claim(self, app: MCPServer, task_id: str) -> None:
        with corvee_context(scope="local", actor="agent:other", session_id=None) as ctx:
            from corvee.db.tasks import claim_task

            claim_task(ctx.conn, int(task_id.removeprefix("TASK-")), "agent:other")

        result = _call(app, "task_unclaim", ref=task_id, force=True, session_id="sess-1")
        assert result["claimed_by"] is None


class TestTaskComment:
    def test_adds_a_comment_visible_via_task_show(self, app: MCPServer, task_id: str) -> None:
        _call(app, "task_comment", ref=task_id, text="found the root cause", session_id="sess-1")
        detail = _call(app, "task_show", ref=task_id)
        assert any(
            e["kind"] == "comment" and e["body"] == "found the root cause" for e in detail["events"]
        )

    def test_not_claim_gated(self, app: MCPServer, task_id: str) -> None:
        """Any actor can comment on a task regardless of who claims it (§4.4)."""
        with corvee_context(scope="local", actor="agent:other", session_id=None) as ctx:
            from corvee.db.tasks import claim_task

            claim_task(ctx.conn, int(task_id.removeprefix("TASK-")), "agent:other")

        result = _call(app, "task_comment", ref=task_id, text="a note", session_id="sess-1")
        assert result["claimed_by"] == "agent:other"

    def test_omitted_session_id_falls_back_to_the_servers_default(
        self, app: MCPServer, task_id: str
    ) -> None:
        """A caller that omits session_id entirely still stamps something
        useful on the event, rather than an unset value -- the server's
        own default (§10.1), not left None the way the CLI's optional
        --session-id would.
        """
        _call(app, "task_comment", ref=task_id, text="no session id given")
        detail = _call(app, "task_show", ref=task_id)
        comment_event = next(e for e in detail["events"] if e["body"] == "no session id given")
        assert comment_event["session_id"] == "sess-server"


class TestTaskStart:
    def test_claims_and_moves_to_in_progress(self, app: MCPServer, task_id: str) -> None:
        result = _call(app, "task_start", ref=task_id, session_id="sess-1")
        assert result["state"] == "in_progress"
        assert result["claimed_by"] == "agent:test"


class TestTaskDone:
    def test_moves_to_done_and_clears_the_claim(self, app: MCPServer, task_id: str) -> None:
        _call(app, "task_claim", ref=task_id, session_id="sess-1")
        result = _call(app, "task_done", ref=task_id, session_id="sess-1")
        assert result["state"] == "done"
        assert result["claimed_by"] is None


class TestTaskCancel:
    def test_moves_to_cancelled_and_clears_the_claim(self, app: MCPServer, task_id: str) -> None:
        _call(app, "task_claim", ref=task_id, session_id="sess-1")
        result = _call(app, "task_cancel", ref=task_id, session_id="sess-1")
        assert result["state"] == "cancelled"
        assert result["claimed_by"] is None


class TestTaskReview:
    def test_moves_to_review_and_keeps_the_claim(self, app: MCPServer, task_id: str) -> None:
        _call(app, "task_start", ref=task_id, session_id="sess-1")
        result = _call(app, "task_review", ref=task_id, session_id="sess-1")
        assert result["state"] == "review"
        assert result["claimed_by"] == "agent:test"


class TestTaskReopen:
    def test_reopens_a_cancelled_task(self, app: MCPServer, task_id: str) -> None:
        _call(app, "task_cancel", ref=task_id, session_id="sess-1")
        result = _call(app, "task_reopen", ref=task_id, session_id="sess-1")
        assert result["state"] == "open"
        assert result["claimed_by"] is None

    def test_reopens_a_done_task(self, app: MCPServer, task_id: str) -> None:
        _call(app, "task_done", ref=task_id, session_id="sess-1")
        result = _call(app, "task_reopen", ref=task_id, session_id="sess-1")
        assert result["state"] == "open"
        assert result["claimed_by"] is None

    def test_rejects_reopening_a_task_under_review(self, app: MCPServer, task_id: str) -> None:
        """`open` is the one state `review` cannot transition to directly
        (constants.py's TRANSITIONS)."""
        _call(app, "task_start", ref=task_id, session_id="sess-1")
        _call(app, "task_review", ref=task_id, session_id="sess-1")
        error = _call_error(app, "task_reopen", ref=task_id, session_id="sess-1")
        assert error["error"]["code"] == "invalid_transition"


class TestTaskBlock:
    def test_requires_a_comment(self, app: MCPServer, task_id: str) -> None:
        error = _call_error(app, "task_block", ref=task_id, comment="", session_id="sess-1")
        assert error["error"]["code"] == "comment_required"

    def test_whitespace_only_comment_is_rejected(self, app: MCPServer, task_id: str) -> None:
        error = _call_error(app, "task_block", ref=task_id, comment="   ", session_id="sess-1")
        assert error["error"]["code"] == "comment_required"

    def test_moves_to_blocked_and_writes_the_comment(self, app: MCPServer, task_id: str) -> None:
        result = _call(
            app, "task_block", ref=task_id, comment="waiting on staging creds", session_id="sess-1"
        )
        assert result["state"] == "blocked"
        detail = _call(app, "task_show", ref=task_id)
        assert any(
            e["kind"] == "comment" and e["body"] == "waiting on staging creds"
            for e in detail["events"]
        )

    def test_rejected_transition_rolls_back_the_comment_too(
        self, app: MCPServer, task_id: str
    ) -> None:
        """done -> blocked isn't a permitted transition (§4.5). The whole
        call fails and the comment is not left behind.
        """
        _call(app, "task_claim", ref=task_id, session_id="sess-1")
        _call(app, "task_done", ref=task_id, session_id="sess-1")

        error = _call_error(
            app, "task_block", ref=task_id, comment="should not stick", session_id="sess-1"
        )
        assert error["error"]["exit_code"] == 5

        detail = _call(app, "task_show", ref=task_id)
        assert not any(e.get("body") == "should not stick" for e in detail["events"])


class TestForceIsNotAParameterOnStateTransitionTools:
    @pytest.mark.parametrize(
        ("tool_name", "extra_kwargs"),
        [
            pytest.param("task_start", {}, id="task_start"),
            pytest.param("task_done", {}, id="task_done"),
            pytest.param("task_cancel", {}, id="task_cancel"),
            pytest.param("task_review", {}, id="task_review"),
            pytest.param("task_reopen", {}, id="task_reopen"),
            pytest.param("task_block", {"comment": "stuck"}, id="task_block"),
        ],
    )
    def test_force_is_not_a_parameter_and_cannot_steal_a_claim(
        self,
        app: MCPServer,
        task_id: str,
        tool_name: str,
        extra_kwargs: dict[str, str],
    ) -> None:
        """`force` was dropped from every state-transition tool (§10.3): a
        caller passing it anyway is silently ignored by the SDK's
        extra-argument handling, not honored -- a claim conflict still
        surfaces exactly as if `force` had never been sent.
        """
        with corvee_context(scope="local", actor="agent:other", session_id=None) as ctx:
            from corvee.db.tasks import claim_task

            claim_task(ctx.conn, int(task_id.removeprefix("TASK-")), "agent:other")

        error = _call_error(
            app, tool_name, ref=task_id, force=True, session_id="sess-1", **extra_kwargs
        )
        assert error["error"]["code"] == "claim_conflict"


class TestActorThreading:
    def test_config_actor_wins_over_the_ambient_corvee_actor_env_var(
        self, project: ProjectConfig, task_id: str
    ) -> None:
        """Every other MCP test's `ServerConfig(actor=...)` happens to
        equal `$CORVEE_ACTOR` (both "agent:test", set by the `project`
        fixture), so a regression that made a handler fall back to
        `resolve_actor()`'s ambient env-var path instead of the
        explicitly threaded `config.actor` would leave the whole suite
        green. Use a `ServerConfig.actor` that differs from
        `$CORVEE_ACTOR` and assert the written event carries THAT value,
        proving the two are genuinely different code paths (TASK-31).
        """
        config = ServerConfig(
            actor="agent:not-the-env-actor", project=project, session_id="sess-server"
        )
        server, worker = build_server(config)
        try:
            _call(server, "task_comment", ref=task_id, text="a note")
            detail = _call(server, "task_show", ref=task_id)
            comment_event = next(e for e in detail["events"] if e["body"] == "a note")
            assert comment_event["actor"] == "agent:not-the-env-actor"
        finally:
            worker.close()
