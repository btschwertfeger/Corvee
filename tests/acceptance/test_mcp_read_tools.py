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
from corvee.mcp.server import build_server
from corvee.mcp.server_config import ServerConfig


class TestTaskShow:
    def test_returns_title_labels_links_subtasks_and_events(
        self, app: MCPServer, project: ProjectConfig
    ) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            from corvee.db.labels import add_label
            from corvee.db.tasks import add_comment, insert_task

            task = insert_task(ctx.conn, title="write the thing", description="details")
            add_label(ctx.conn, task.id, "backend", "agent:test", None)
            add_comment(ctx.conn, task.id, "started", "agent:test", None)

        detail = _call(app, "task_show", ref=f"TASK-{task.id}")
        assert detail["title"] == "write the thing"
        assert detail["labels"] == ["backend"]
        assert detail["subtasks"] == []
        assert any(event["kind"] == "comment" for event in detail["events"])

    def test_not_found_gives_a_clean_error(self, app: MCPServer) -> None:
        error = _call_error(app, "task_show", ref="TASK-999999")
        assert error["error"]["code"] == "task_not_found"
        assert error["error"]["exit_code"] == 3

    def test_since_drops_events_older_than_the_cutoff_and_reports_the_count(
        self, app: MCPServer, project: ProjectConfig
    ) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            from corvee.db.tasks import add_comment, insert_task

            task = insert_task(ctx.conn, title="write the thing", description="details")
            add_comment(ctx.conn, task.id, "an old note", "agent:test", None)
            ctx.conn.execute(
                "UPDATE task_events SET created_at = '2000-01-01T00:00:00.000Z' WHERE task_id = ?",
                (task.id,),
            )

        full = _call(app, "task_show", ref=f"TASK-{task.id}")
        assert any(e["body"] == "an old note" for e in full["events"])
        assert full["events_omitted"] == 0

        bounded = _call(app, "task_show", ref=f"TASK-{task.id}", since="7d")
        assert bounded["events"] == []
        assert bounded["events_omitted"] == 1

    def test_invalid_since_gives_a_usage_error(
        self, app: MCPServer, project: ProjectConfig
    ) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            from corvee.db.tasks import insert_task

            task = insert_task(ctx.conn, title="t")

        error = _call_error(app, "task_show", ref=f"TASK-{task.id}", since="not-a-duration")
        assert error["error"]["code"] == "invalid_duration"
        assert error["error"]["exit_code"] == 2

    def test_accepts_a_bare_json_integer_ref_not_just_a_string(
        self, app: MCPServer, project: ProjectConfig
    ) -> None:
        """A JSON-speaking client sends a bare id as a number, not a
        string; the tool's own description promises "a bare integer" is
        accepted, so this must succeed rather than raise a raw SDK
        validation error that bypasses corvee's clean-error contract.
        """
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            from corvee.db.tasks import insert_task

            task = insert_task(ctx.conn, title="t")

        detail = _call(app, "task_show", ref=task.id)
        assert detail["title"] == "t"

    @pytest.mark.parametrize("since", [7, 7.5])
    def test_since_as_a_json_number_is_a_clean_usage_error_not_a_raw_sdk_one(
        self, app: MCPServer, project: ProjectConfig, since: object
    ) -> None:
        """A client sending `since` as a JSON number (not the documented
        duration string) still fails inside corvee's own clean-error
        contract, rather than raising a raw SDK argument-validation error
        that never reaches `run_tool`.
        """
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            from corvee.db.tasks import insert_task

            task = insert_task(ctx.conn, title="t")

        error = _call_error(app, "task_show", ref=f"TASK-{task.id}", since=since)
        assert error["error"]["code"] == "invalid_duration"
        assert error["error"]["exit_code"] == 2

    def test_local_ref_in_global_only_mode_gives_no_project_error(self) -> None:
        config = ServerConfig(actor="agent:test", project=None, session_id="sess-server")
        server, worker = build_server(config)
        try:
            error = _call_error(server, "task_show", ref="TASK-1")
            assert error["error"]["code"] == "no_project"
            assert error["error"]["exit_code"] == 6
        finally:
            worker.close()

    def test_never_calls_resolve_project_reusing_the_cached_project_instead(
        self, app: MCPServer, project: ProjectConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`ServerConfig.project` is already a fully-resolved `ProjectConfig`
        (spec §10.1); a tool call's own `corvee_context` must reuse its
        `db_path` rather than re-deriving it via a fresh `resolve_project`
        filesystem walk + TOML re-parse (TASK-37). Proven by making
        `resolve_project` itself explode if called at all.
        """

        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            from corvee.db.tasks import insert_task

            task = insert_task(ctx.conn, title="t")

        def _must_not_be_called(*args: object, **kwargs: object) -> None:
            raise AssertionError(
                "resolve_project was called; the cached project.db_path was not reused"
            )

        monkeypatch.setattr("corvee.cli.context.resolve_project", _must_not_be_called)

        detail = _call(app, "task_show", ref=f"TASK-{task.id}")
        assert detail["title"] == "t"


class TestBrief:
    def test_reports_mine_ready_stale_and_labels(
        self, app: MCPServer, project: ProjectConfig
    ) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            from corvee.db.labels import add_label
            from corvee.db.tasks import claim_task, insert_task

            mine_task = insert_task(ctx.conn, title="mine")
            claim_task(ctx.conn, mine_task.id, "agent:test")
            ready_task = insert_task(ctx.conn, title="ready")
            add_label(ctx.conn, ready_task.id, "urgent", "agent:test", None)

        result = _call(app, "brief")
        assert [t["title"] for t in result["mine"]] == ["mine"]
        assert {t["title"] for t in result["ready"]} == {"ready"}
        assert result["stale"] == []
        assert {label["name"] for label in result["labels"]} == {"urgent"}

    def test_invalid_scope_gives_a_usage_error(self, app: MCPServer) -> None:
        error = _call_error(app, "brief", scope="bogus")
        assert error["error"]["code"] == "invalid_scope"
        assert error["error"]["exit_code"] == 2


class TestFactSearch:
    def test_finds_a_matching_fact(self, app: MCPServer) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            from corvee.db.facts import insert_fact

            insert_fact(ctx.conn, claim="requests is Apache-2.0 licensed", actor="agent:test")
            insert_fact(ctx.conn, claim="unrelated claim", actor="agent:test")

        results = _call(app, "fact_search", text="Apache")
        assert [f["claim"] for f in results["result"]] == ["requests is Apache-2.0 licensed"]

    def test_limit_applies_after_the_merge(self, app: MCPServer) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            from corvee.db.facts import insert_fact

            for i in range(5):
                insert_fact(ctx.conn, claim=f"claim number {i}", actor="agent:test")

        results = _call(app, "fact_search", text="claim", limit=2)
        assert len(results["result"]) == 2

    def test_reports_how_many_matches_were_omitted_by_the_limit(self, app: MCPServer) -> None:
        """A search that matches more than `limit` facts must say so
        (TASK-32) -- silently truncating with no signal would make a
        caller checking for an existing fact see a false negative.
        """
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            from corvee.db.facts import insert_fact

            for i in range(5):
                insert_fact(ctx.conn, claim=f"claim number {i}", actor="agent:test")

        capped = _call(app, "fact_search", text="claim", limit=2)
        assert capped["omitted"] == 3

        uncapped = _call(app, "fact_search", text="claim", limit=20)
        assert uncapped["omitted"] == 0

    def test_invalid_limit_gives_a_usage_error(self, app: MCPServer) -> None:
        error = _call_error(app, "fact_search", text="x", limit=0)
        assert error["error"]["code"] == "invalid_limit"
        assert error["error"]["exit_code"] == 2

    def test_fractional_limit_is_a_clean_usage_error_not_a_raw_sdk_one(
        self, app: MCPServer
    ) -> None:
        """The fact-group equivalent of the same check on `task_search`."""
        error = _call_error(app, "fact_search", text="x", limit=1.5)
        assert error["error"]["code"] == "invalid_limit"
        assert error["error"]["exit_code"] == 2

    def test_include_retracted_also_matches_retracted_facts(self, app: MCPServer) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            from corvee.db.facts import insert_fact, retract_fact

            fact = insert_fact(ctx.conn, claim="old cache invalidation claim", actor="agent:test")
            retract_fact(ctx.conn, fact.id, "agent:test", scope="local")

        assert _call(app, "fact_search", text="cache invalidation")["result"] == []
        with_retracted = _call(
            app, "fact_search", text="cache invalidation", include_retracted=True
        )
        assert len(with_retracted["result"]) == 1

    def test_include_proof_also_matches_proof_text(self, app: MCPServer) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            from corvee.db.facts import insert_fact

            insert_fact(
                ctx.conn,
                claim="unrelated claim",
                actor="agent:test",
                proof="see the root cause writeup",
            )

        assert _call(app, "fact_search", text="root cause")["result"] == []
        with_proof = _call(app, "fact_search", text="root cause", include_proof=True)
        assert len(with_proof["result"]) == 1

    def test_verified_by_filters_to_that_actors_verifications(self, app: MCPServer) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            from corvee.db.facts import insert_fact, verify_fact

            fact = insert_fact(ctx.conn, claim="widget count is 42", actor="agent:test")
            verify_fact(ctx.conn, fact.id, "checked the db", "agent:other", session_id=None)

        assert (
            _call(app, "fact_search", text="widget", verified_by="agent:someone-else")["result"]
            == []
        )
        results = _call(app, "fact_search", text="widget", verified_by="agent:other")
        assert len(results["result"]) == 1
