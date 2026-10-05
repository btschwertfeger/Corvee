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
from corvee.db.links import link_tasks
from corvee.db.tasks import apply_update, insert_task
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
        assert error["error"]["hint"] == (
            "call task_unclaim(force=true) on this ref to release the claim, then retry"
        )

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


class TestTaskUpdate:
    def test_updates_title_description_type_and_priority(
        self, app: MCPServer, task_id: str
    ) -> None:
        result = _call(
            app,
            "task_update",
            refs=[task_id],
            title="new title",
            description="new description",
            task_type="bug",
            priority="high",
            session_id="sess-1",
        )
        updated = result["result"][0]
        assert updated["title"] == "new title"
        assert updated["description"] == "new description"
        assert updated["type"] == "bug"
        assert updated["priority"] == "high"

    def test_batches_several_refs_into_one_transaction(
        self, app: MCPServer, project: ProjectConfig
    ) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            first = insert_task(ctx.conn, title="a")
            second = insert_task(ctx.conn, title="b")

        result = _call(
            app,
            "task_update",
            refs=[f"TASK-{first.id}", f"TASK-{second.id}"],
            priority="high",
            session_id="sess-1",
        )
        by_id = {t["id"]: t for t in result["result"]}
        assert by_id[f"TASK-{first.id}"]["priority"] == "high"
        assert by_id[f"TASK-{second.id}"]["priority"] == "high"

    def test_state_transitions_the_same_way_the_cli_does(
        self, app: MCPServer, task_id: str
    ) -> None:
        result = _call(app, "task_update", refs=[task_id], state="in_progress", session_id="sess-1")
        updated = result["result"][0]
        assert updated["state"] == "in_progress"
        assert updated["claimed_by"] == "agent:test"

    def test_claim_conflict_without_force(self, app: MCPServer, task_id: str) -> None:
        with corvee_context(scope="local", actor="agent:other", session_id=None) as ctx:
            from corvee.db.tasks import claim_task

            claim_task(ctx.conn, int(task_id.removeprefix("TASK-")), "agent:other")

        error = _call_error(app, "task_update", refs=[task_id], title="x", session_id="sess-1")
        assert error["error"]["code"] == "claim_conflict"

    def test_force_overrides_someone_elses_claim(self, app: MCPServer, task_id: str) -> None:
        with corvee_context(scope="local", actor="agent:other", session_id=None) as ctx:
            from corvee.db.tasks import claim_task

            claim_task(ctx.conn, int(task_id.removeprefix("TASK-")), "agent:other")

        result = _call(
            app, "task_update", refs=[task_id], state="done", force=True, session_id="sess-1"
        )
        assert result["result"][0]["state"] == "done"

    def test_cascade_cancels_open_descendants(self, app: MCPServer, project: ProjectConfig) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            parent = insert_task(ctx.conn, title="parent")
            child = insert_task(ctx.conn, title="child")
            link_tasks(ctx.conn, parent.id, child.id, "parent_of", "agent:test", None)

        result = _call(
            app,
            "task_update",
            refs=[f"TASK-{parent.id}"],
            state="cancelled",
            cascade=True,
            session_id="sess-1",
        )
        by_id = {t["id"]: t["state"] for t in result["result"]}
        assert by_id[f"TASK-{parent.id}"] == "cancelled"
        assert by_id[f"TASK-{child.id}"] == "cancelled"

    def test_invalid_state_is_a_usage_error(self, app: MCPServer, task_id: str) -> None:
        error = _call_error(app, "task_update", refs=[task_id], state="bogus", session_id="sess-1")
        assert error["error"]["code"] == "invalid_state"

    def test_invalid_task_type_is_a_usage_error(self, app: MCPServer, task_id: str) -> None:
        error = _call_error(
            app, "task_update", refs=[task_id], task_type="bogus", session_id="sess-1"
        )
        assert error["error"]["code"] == "invalid_type"

    def test_invalid_priority_is_a_usage_error(self, app: MCPServer, task_id: str) -> None:
        error = _call_error(
            app, "task_update", refs=[task_id], priority="bogus", session_id="sess-1"
        )
        assert error["error"]["code"] == "invalid_priority"


class TestTaskLabel:
    def test_attaches_a_label_visible_via_task_show(self, app: MCPServer, task_id: str) -> None:
        _call(app, "task_label", refs=[task_id], label="API", session_id="sess-1")
        detail = _call(app, "task_show", ref=task_id)
        assert detail["labels"] == ["api"]

    def test_no_op_if_already_attached(self, app: MCPServer, task_id: str) -> None:
        _call(app, "task_label", refs=[task_id], label="urgent", session_id="sess-1")
        result = _call(app, "task_label", refs=[task_id], label="urgent", session_id="sess-1")
        assert result["result"][0]["id"] == task_id

    def test_batches_several_refs_into_one_transaction(
        self, app: MCPServer, project: ProjectConfig
    ) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            first = insert_task(ctx.conn, title="a")
            second = insert_task(ctx.conn, title="b")

        _call(
            app,
            "task_label",
            refs=[f"TASK-{first.id}", f"TASK-{second.id}"],
            label="urgent",
            session_id="sess-1",
        )
        first_detail = _call(app, "task_show", ref=f"TASK-{first.id}")
        second_detail = _call(app, "task_show", ref=f"TASK-{second.id}")
        assert first_detail["labels"] == ["urgent"]
        assert second_detail["labels"] == ["urgent"]

    def test_batch_is_all_or_nothing(self, app: MCPServer, project: ProjectConfig) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            first = insert_task(ctx.conn, title="a")

        error = _call_error(
            app,
            "task_label",
            refs=[f"TASK-{first.id}", "TASK-999999"],
            label="urgent",
            session_id="sess-1",
        )
        assert error["error"]["exit_code"] == 3
        detail = _call(app, "task_show", ref=f"TASK-{first.id}")
        assert detail["labels"] == []

    def test_invalid_label_is_a_usage_error(self, app: MCPServer, task_id: str) -> None:
        error = _call_error(
            app, "task_label", refs=[task_id], label="has space", session_id="sess-1"
        )
        assert error["error"]["code"] == "invalid_label"


class TestTaskUnlabel:
    def test_removes_an_attached_label(self, app: MCPServer, task_id: str) -> None:
        _call(app, "task_label", refs=[task_id], label="urgent", session_id="sess-1")
        _call(app, "task_unlabel", refs=[task_id], label="urgent", session_id="sess-1")
        detail = _call(app, "task_show", ref=task_id)
        assert detail["labels"] == []

    def test_no_op_if_not_attached(self, app: MCPServer, task_id: str) -> None:
        result = _call(app, "task_unlabel", refs=[task_id], label="urgent", session_id="sess-1")
        assert result["result"][0]["id"] == task_id


class TestTaskLink:
    def test_links_two_tasks(self, app: MCPServer, project: ProjectConfig) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            first = insert_task(ctx.conn, title="a")
            second = insert_task(ctx.conn, title="b")

        result = _call(
            app,
            "task_link",
            source_ref=f"TASK-{first.id}",
            target_ref=f"TASK-{second.id}",
            relation="blocks",
            session_id="sess-1",
        )
        assert [t["id"] for t in result["result"]] == [f"TASK-{first.id}", f"TASK-{second.id}"]
        detail = _call(app, "task_show", ref=f"TASK-{first.id}")
        assert any(
            link["relation"] == "blocks" and link["task_id"] == f"TASK-{second.id}"
            for link in detail["links"]
        )

    def test_self_link_is_a_guard_violation(self, app: MCPServer, task_id: str) -> None:
        error = _call_error(
            app,
            "task_link",
            source_ref=task_id,
            target_ref=task_id,
            relation="relates_to",
            session_id="sess-1",
        )
        assert error["error"]["code"] == "self_link"
        assert error["error"]["exit_code"] == 5

    def test_result_order_is_source_then_target_even_when_target_id_is_lower(
        self, app: MCPServer, project: ProjectConfig
    ) -> None:
        """`blocks` is not id-normalized the way `relates_to` is, so
        `result` follows argument order even when the source id is
        higher.
        """
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            first = insert_task(ctx.conn, title="a")
            second = insert_task(ctx.conn, title="b")

        result = _call(
            app,
            "task_link",
            source_ref=f"TASK-{second.id}",
            target_ref=f"TASK-{first.id}",
            relation="blocks",
            session_id="sess-1",
        )
        assert [t["id"] for t in result["result"]] == [f"TASK-{second.id}", f"TASK-{first.id}"]

    def test_cross_scope_link_is_a_guard_violation(self, app: MCPServer, task_id: str) -> None:
        with corvee_context(scope="global", actor="agent:test", session_id=None) as ctx:
            global_task = insert_task(ctx.conn, title="global task", scope="global")

        error = _call_error(
            app,
            "task_link",
            source_ref=task_id,
            target_ref=f"TASK-GLOBAL-{global_task.id}",
            relation="relates_to",
            session_id="sess-1",
        )
        assert error["error"]["code"] == "cross_scope_link"

    def test_parent_of_warns_when_child_is_open_and_parent_is_done(
        self, app: MCPServer, project: ProjectConfig
    ) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            parent = insert_task(ctx.conn, title="parent")
            child = insert_task(ctx.conn, title="child")
            apply_update(ctx.conn, parent.id, "agent:test", state="in_progress")
            apply_update(ctx.conn, parent.id, "agent:test", state="done")

        result = _call(
            app,
            "task_link",
            source_ref=f"TASK-{parent.id}",
            target_ref=f"TASK-{child.id}",
            relation="parent_of",
            session_id="sess-1",
        )
        by_id = {t["id"]: t for t in result["result"]}
        assert by_id[f"TASK-{parent.id}"]["warnings"] == [
            f"child TASK-{child.id} is open while this parent is done"
        ]
        assert "warnings" not in by_id[f"TASK-{child.id}"]

    def test_invalid_relation_is_a_usage_error(self, app: MCPServer, task_id: str) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            other = insert_task(ctx.conn, title="other")

        error = _call_error(
            app,
            "task_link",
            source_ref=task_id,
            target_ref=f"TASK-{other.id}",
            relation="bogus",
            session_id="sess-1",
        )
        assert error["error"]["code"] == "invalid_relation"


class TestTaskUnlink:
    def test_unlinks_two_tasks(self, app: MCPServer, project: ProjectConfig) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            first = insert_task(ctx.conn, title="a")
            second = insert_task(ctx.conn, title="b")
            link_tasks(ctx.conn, first.id, second.id, "blocks", "agent:test", None)

        _call(
            app,
            "task_unlink",
            source_ref=f"TASK-{first.id}",
            target_ref=f"TASK-{second.id}",
            relation="blocks",
            session_id="sess-1",
        )
        detail = _call(app, "task_show", ref=f"TASK-{first.id}")
        assert detail["links"] == []

    def test_no_op_if_not_linked(self, app: MCPServer, project: ProjectConfig) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            first = insert_task(ctx.conn, title="a")
            second = insert_task(ctx.conn, title="b")

        result = _call(
            app,
            "task_unlink",
            source_ref=f"TASK-{first.id}",
            target_ref=f"TASK-{second.id}",
            relation="blocks",
            session_id="sess-1",
        )
        assert [t["id"] for t in result["result"]] == [f"TASK-{first.id}", f"TASK-{second.id}"]

    def test_invalid_relation_is_a_usage_error(self, app: MCPServer, task_id: str) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            other = insert_task(ctx.conn, title="other")

        error = _call_error(
            app,
            "task_unlink",
            source_ref=task_id,
            target_ref=f"TASK-{other.id}",
            relation="bogus",
            session_id="sess-1",
        )
        assert error["error"]["code"] == "invalid_relation"


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
