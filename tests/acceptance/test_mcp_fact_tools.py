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
from corvee.mcp.server import ServerConfig, build_server


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
