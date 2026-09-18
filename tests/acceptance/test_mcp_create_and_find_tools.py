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
from corvee.db.facts import insert_fact
from corvee.db.tasks import add_comment, insert_task
from corvee.mcp.server import build_server
from corvee.mcp.server_config import ServerConfig


class TestTaskAdd:
    def test_creates_a_task_with_title_and_description(self, app: MCPServer) -> None:
        result = _call(
            app, "task_add", title="Fix the flaky auth test", description="repro: run make test"
        )
        assert result["title"] == "Fix the flaky auth test"
        assert result["description"] == "repro: run make test"
        assert result["state"] == "open"
        assert result["claimed_by"] is None
        assert result["type"] == "task"
        assert result["priority"] == "medium"

    def test_custom_type_and_priority(self, app: MCPServer) -> None:
        result = _call(
            app,
            "task_add",
            title="Investigate slow query",
            description="p99 up 3x",
            task_type="bug",
            priority="high",
        )
        assert result["type"] == "bug"
        assert result["priority"] == "high"

    def test_empty_title_is_rejected(self, app: MCPServer) -> None:
        error = _call_error(app, "task_add", title="  ", description="d")
        assert error["error"]["code"] == "invalid_title"

    def test_empty_description_is_rejected(self, app: MCPServer) -> None:
        error = _call_error(app, "task_add", title="t", description="  ")
        assert error["error"]["code"] == "invalid_description"

    def test_is_global_files_into_the_global_database(self, app: MCPServer) -> None:
        result = _call(app, "task_add", title="Renew CA cert", description="yearly", is_global=True)
        assert result["scope"] == "global"

    def test_does_not_claim_the_created_task(self, app: MCPServer) -> None:
        """Filing work and starting it are separate acts (§4.4), same as
        the CLI's own `task add`.
        """
        result = _call(app, "task_add", title="t", description="d")
        assert result["claimed_by"] is None

    def test_local_scope_in_global_only_mode_gives_no_project_error(self) -> None:
        config = ServerConfig(actor="agent:test", project=None, session_id="sess-server")
        server, worker = build_server(config)
        try:
            error = _call_error(server, "task_add", title="t", description="d")
            assert error["error"]["code"] == "no_project"
        finally:
            worker.close()

    def test_writes_a_created_event_carrying_actor_and_the_given_session_id(
        self, app: MCPServer
    ) -> None:
        """`insert_task` used to write no `created` event at all (unlike
        `insert_fact`), making `session_id` a documented-but-dead
        argument (TASK-29). It now records one, carrying the server's
        actor and this call's own `session_id`.
        """
        created = _call(
            app, "task_add", title="t", description="d", session_id="sess-from-the-call"
        )
        detail = _call(app, "task_show", ref=created["id"])
        created_events = [e for e in detail["events"] if e["kind"] == "created"]
        assert len(created_events) == 1
        assert created_events[0]["actor"] == "agent:test"
        assert created_events[0]["session_id"] == "sess-from-the-call"
        assert created_events[0]["new_value"] == "t"

    def test_omitted_session_id_falls_back_to_the_servers_own(self, app: MCPServer) -> None:
        created = _call(app, "task_add", title="t", description="d")
        detail = _call(app, "task_show", ref=created["id"])
        created_events = [e for e in detail["events"] if e["kind"] == "created"]
        assert created_events[0]["session_id"] == "sess-server"


class TestTaskSearch:
    def test_finds_a_matching_task(self, app: MCPServer, project: ProjectConfig) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            insert_task(ctx.conn, title="fix the flaky auth test", description="d")
            insert_task(ctx.conn, title="unrelated task", description="d")

        results = _call(app, "task_search", text="flaky")
        assert [t["title"] for t in results["result"]] == ["fix the flaky auth test"]

    def test_excludes_done_and_cancelled_by_default(
        self, app: MCPServer, project: ProjectConfig
    ) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            from corvee.db.tasks import apply_update

            task = insert_task(ctx.conn, title="cache invalidation bug", description="d")
            apply_update(ctx.conn, task.id, "agent:test", state="done")

        assert _call(app, "task_search", text="cache")["result"] == []
        include_all = _call(app, "task_search", text="cache", include_all=True)
        assert len(include_all["result"]) == 1

    def test_limit_applies_after_the_merge(self, app: MCPServer, project: ProjectConfig) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            for i in range(5):
                insert_task(ctx.conn, title=f"cache task {i}", description="d")

        results = _call(app, "task_search", text="cache", limit=2)
        assert len(results["result"]) == 2

    def test_reports_how_many_matches_were_omitted_by_the_limit(
        self, app: MCPServer, project: ProjectConfig
    ) -> None:
        """A search that matches more than `limit` tasks must say so
        (TASK-32) -- task_search's own stated purpose is letting a caller
        check whether a task already exists before filing a duplicate,
        and a silently-truncated result would give a false negative.
        """
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            for i in range(5):
                insert_task(ctx.conn, title=f"cache task {i}", description="d")

        capped = _call(app, "task_search", text="cache", limit=2)
        assert capped["omitted"] == 3

        uncapped = _call(app, "task_search", text="cache", limit=20)
        assert uncapped["omitted"] == 0

    def test_include_comments_matches_comment_bodies(
        self, app: MCPServer, project: ProjectConfig
    ) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            task = insert_task(ctx.conn, title="unrelated title", description="unrelated body")
            add_comment(ctx.conn, task.id, "root cause is the cache", "agent:test", None)

        assert _call(app, "task_search", text="root cause")["result"] == []
        with_comments = _call(app, "task_search", text="root cause", include_comments=True)
        assert len(with_comments["result"]) == 1

    def test_invalid_limit_gives_a_usage_error(self, app: MCPServer) -> None:
        error = _call_error(app, "task_search", text="x", limit=0)
        assert error["error"]["code"] == "invalid_limit"


class TestFactShow:
    def test_returns_claim_status_proof_and_events(
        self, app: MCPServer, project: ProjectConfig
    ) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            fact = insert_fact(ctx.conn, claim="requests is Apache-2.0", actor="agent:test")

        detail = _call(app, "fact_show", ref=f"FACT-{fact.id}")
        assert detail["claim"] == "requests is Apache-2.0"
        assert detail["status"] == "unverified"
        assert any(e["kind"] == "created" for e in detail["events"])

    def test_not_found_gives_a_clean_error(self, app: MCPServer) -> None:
        error = _call_error(app, "fact_show", ref="FACT-999999")
        assert error["error"]["code"] == "fact_not_found"

    def test_wrong_id_namespace_is_rejected(self, app: MCPServer, project: ProjectConfig) -> None:
        """A task id handed to fact_show is rejected, not silently misread
        (§4.2/§4.6) -- same guard the CLI's own id parsers already enforce.
        """
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            task = insert_task(ctx.conn, title="t", description="d")

        error = _call_error(app, "fact_show", ref=f"TASK-{task.id}")
        assert error["error"]["code"] == "wrong_id_namespace"
