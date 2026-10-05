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
from corvee.db.facts import insert_fact, verify_fact
from corvee.mcp.server import build_server
from corvee.mcp.server_config import ServerConfig


class TestFactAdd:
    def test_creates_an_unverified_fact_by_default(self, app: MCPServer) -> None:
        result = _call(
            app, "fact_add", claim="requests is Apache-2.0 licensed", session_id="sess-1"
        )
        assert result["claim"] == "requests is Apache-2.0 licensed"
        assert result["status"] == "unverified"

    def test_proof_verifies_it_immediately(self, app: MCPServer) -> None:
        result = _call(
            app,
            "fact_add",
            claim="requests is Apache-2.0 licensed",
            proof="pip show requests",
            session_id="sess-1",
        )
        assert result["status"] == "verified"
        assert result["proof"] == "pip show requests"

    def test_is_global_files_into_the_global_database(self, app: MCPServer) -> None:
        result = _call(
            app, "fact_add", claim="renew CA cert yearly", is_global=True, session_id="sess-1"
        )
        assert result["scope"] == "global"

    def test_default_is_local(self, app: MCPServer) -> None:
        result = _call(app, "fact_add", claim="a local fact", session_id="sess-1")
        assert result["scope"] == "local"

    def test_empty_claim_is_rejected(self, app: MCPServer) -> None:
        """The CLI's own `fact add` already rejects this (`invalid_claim`,
        cli/commands/fact/add.py) -- task_add already mirrors the same
        rule for title/description, fact_add never did for claim.
        """
        error = _call_error(app, "fact_add", claim="  ")
        assert error["error"]["code"] == "invalid_claim"

    def test_local_scope_in_global_only_mode_gives_no_project_error(self) -> None:
        config = ServerConfig(actor="agent:test", project=None, session_id="sess-server")
        server, worker = build_server(config)
        try:
            error = _call_error(server, "fact_add", claim="x", session_id="sess-1")
            assert error["error"]["code"] == "no_project"
        finally:
            worker.close()

    def test_is_global_works_in_global_only_mode(self) -> None:
        config = ServerConfig(actor="agent:test", project=None, session_id="sess-server")
        server, worker = build_server(config)
        try:
            result = _call(server, "fact_add", claim="x", is_global=True, session_id="sess-1")
            assert result["scope"] == "global"
        finally:
            worker.close()


class TestFactVerify:
    def test_verifies_an_existing_unverified_fact(
        self, app: MCPServer, project: ProjectConfig
    ) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            fact = insert_fact(ctx.conn, claim="a claim", actor="agent:test")

        result = _call(
            app, "fact_verify", ref=f"FACT-{fact.id}", proof="checked it", session_id="sess-1"
        )
        assert result["status"] == "verified"
        assert result["proof"] == "checked it"
        assert result["verified_by"] == "agent:test"

    def test_not_found_gives_a_clean_error(self, app: MCPServer) -> None:
        error = _call_error(app, "fact_verify", ref="FACT-999999", proof="x", session_id="sess-1")
        assert error["error"]["code"] == "fact_not_found"


class TestFactRevise:
    def test_revises_a_facts_claim(self, app: MCPServer, project: ProjectConfig) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            fact = insert_fact(ctx.conn, claim="old claim", actor="agent:test")

        result = _call(
            app,
            "fact_revise",
            ref=f"FACT-{fact.id}",
            new_claim="corrected claim",
            session_id="sess-1",
        )
        assert result["claim"] == "corrected claim"

    def test_identical_claim_is_a_no_op(self, app: MCPServer, project: ProjectConfig) -> None:
        """A verified fact stays verified when `new_claim` matches the
        current claim exactly -- only a genuine change resets it, so
        leaving `status`/`proof` untouched here is what proves the no-op
        path ran instead of an ordinary write of identical text.
        """
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            fact = insert_fact(ctx.conn, claim="same claim", actor="agent:test")
            fact = verify_fact(ctx.conn, fact.id, "checked it", "agent:test")

        result = _call(
            app,
            "fact_revise",
            ref=f"FACT-{fact.id}",
            new_claim="same claim",
            session_id="sess-1",
        )
        assert result["claim"] == "same claim"
        assert result["status"] == "verified"
        assert result["proof"] == "checked it"

    def test_a_verified_fact_resets_to_unverified_on_a_genuine_change(
        self, app: MCPServer, project: ProjectConfig
    ) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            fact = insert_fact(ctx.conn, claim="old claim", actor="agent:test")
            fact = verify_fact(ctx.conn, fact.id, "checked it", "agent:test")

        result = _call(
            app,
            "fact_revise",
            ref=f"FACT-{fact.id}",
            new_claim="corrected claim",
            session_id="sess-1",
        )
        assert result["claim"] == "corrected claim"
        assert result["status"] == "unverified"
        assert result["proof"] is None

    def test_not_found_gives_a_clean_error(self, app: MCPServer) -> None:
        error = _call_error(
            app, "fact_revise", ref="FACT-999999", new_claim="x", session_id="sess-1"
        )
        assert error["error"]["code"] == "fact_not_found"


class TestFactRetract:
    def test_retracts_a_fact_with_a_reason(self, app: MCPServer, project: ProjectConfig) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            fact = insert_fact(ctx.conn, claim="a claim", actor="agent:test")

        result = _call(
            app,
            "fact_retract",
            ref=f"FACT-{fact.id}",
            reason="added by mistake",
            session_id="sess-1",
        )
        assert result["status"] == "retracted"

        detail = _call(app, "fact_show", ref=f"FACT-{fact.id}")
        assert detail["events"][-1]["kind"] == "retracted"
        assert detail["events"][-1]["note"] == "added by mistake"

    def test_retracts_a_fact_without_a_reason(self, app: MCPServer, project: ProjectConfig) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            fact = insert_fact(ctx.conn, claim="a claim", actor="agent:test")

        result = _call(app, "fact_retract", ref=f"FACT-{fact.id}", session_id="sess-1")
        assert result["status"] == "retracted"

    def test_clears_verification_fields(self, app: MCPServer, project: ProjectConfig) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            fact = insert_fact(ctx.conn, claim="a claim", actor="agent:test")
            fact = verify_fact(ctx.conn, fact.id, "checked it", "agent:test")

        result = _call(app, "fact_retract", ref=f"FACT-{fact.id}", session_id="sess-1")
        assert result["status"] == "retracted"
        assert result["proof"] is None
        assert result["verified_by"] is None

    def test_excluded_from_fact_search_by_default_but_included_explicitly(
        self, app: MCPServer, project: ProjectConfig
    ) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            fact = insert_fact(ctx.conn, claim="widget retraction test", actor="agent:test")

        _call(app, "fact_retract", ref=f"FACT-{fact.id}", session_id="sess-1")

        assert _call(app, "fact_search", text="widget retraction test")["result"] == []
        with_retracted = _call(
            app, "fact_search", text="widget retraction test", include_retracted=True
        )
        assert len(with_retracted["result"]) == 1
        assert with_retracted["result"][0]["status"] == "retracted"

    def test_fact_verify_still_works_on_a_retracted_fact(
        self, app: MCPServer, project: ProjectConfig
    ) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            fact = insert_fact(ctx.conn, claim="a claim", actor="agent:test")

        _call(app, "fact_retract", ref=f"FACT-{fact.id}", session_id="sess-1")
        result = _call(
            app, "fact_verify", ref=f"FACT-{fact.id}", proof="checked it", session_id="sess-1"
        )
        assert result["status"] == "verified"
        assert result["proof"] == "checked it"

    def test_not_found_gives_a_clean_error(self, app: MCPServer) -> None:
        error = _call_error(app, "fact_retract", ref="FACT-999999", session_id="sess-1")
        assert error["error"]["code"] == "fact_not_found"


class TestFactUnverify:
    def test_unverifies_a_verified_fact_with_a_note(
        self, app: MCPServer, project: ProjectConfig
    ) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            fact = insert_fact(ctx.conn, claim="a claim", actor="agent:test")
            fact = verify_fact(ctx.conn, fact.id, "checked it", "agent:test")

        result = _call(
            app,
            "fact_unverify",
            ref=f"FACT-{fact.id}",
            note="proof link is now dead",
            session_id="sess-1",
        )
        assert result["status"] == "unverified"
        assert result["proof"] is None
        assert result["verified_by"] is None

        detail = _call(app, "fact_show", ref=f"FACT-{fact.id}")
        assert detail["events"][-1]["kind"] == "unverified"
        assert detail["events"][-1]["note"] == "proof link is now dead"

    def test_unverifies_without_a_note(self, app: MCPServer, project: ProjectConfig) -> None:
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            fact = insert_fact(ctx.conn, claim="a claim", actor="agent:test")
            fact = verify_fact(ctx.conn, fact.id, "checked it", "agent:test")

        result = _call(app, "fact_unverify", ref=f"FACT-{fact.id}", session_id="sess-1")
        assert result["status"] == "unverified"
        assert result["proof"] is None

    def test_unverifying_an_already_unverified_fact_still_succeeds(
        self, app: MCPServer, project: ProjectConfig
    ) -> None:
        """`unverify_fact` runs unconditionally -- no guard checks the
        current status first, so calling it on a fact that is already
        unverified still succeeds and records another `unverified` event.
        """
        with corvee_context(scope="local", actor="agent:test", session_id=None) as ctx:
            fact = insert_fact(ctx.conn, claim="a claim", actor="agent:test")

        result = _call(app, "fact_unverify", ref=f"FACT-{fact.id}", session_id="sess-1")
        assert result["status"] == "unverified"

        detail = _call(app, "fact_show", ref=f"FACT-{fact.id}")
        assert [e["kind"] for e in detail["events"]] == ["created", "unverified"]

    def test_not_found_gives_a_clean_error(self, app: MCPServer) -> None:
        error = _call_error(app, "fact_unverify", ref="FACT-999999", session_id="sess-1")
        assert error["error"]["code"] == "fact_not_found"
