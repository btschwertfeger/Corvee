#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

from typing import Annotated, Any, cast

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from corvee.cli.context import corvee_context
from corvee.constants import Scope
from corvee.db.events import get_fact_events
from corvee.db.facts import insert_fact, require_fact, verify_fact
from corvee.errors import UsageError
from corvee.mcp.dispatch import run_tool
from corvee.mcp.scope import require_scope_available
from corvee.mcp.server import ServerConfig
from corvee.mcp.tools_common import (
    FactRefArg,
    IsGlobalArg,
    SessionIdArg,
    project_db_path,
    session_id_for,
)
from corvee.mcp.worker import DbWorker
from corvee.models import parse_fact_ref


def register_fact_tools(app: MCPServer, config: ServerConfig, worker: DbWorker) -> None:
    """Registers the fact tools: `fact_add`, `fact_verify`, `fact_show`
    (spec §10.3). `fact_add`/`fact_verify` write an event; `session_id` is
    optional on each, same default as the write tools above. `fact_show`
    is read-only and does not accept `session_id` at all.
    """

    @app.tool(structured_output=True)
    async def fact_add(
        claim: Annotated[str, Field(description="The fact's claim text. Must not be empty.")],
        session_id: SessionIdArg = None,
        proof: Annotated[
            str | None,
            Field(
                description="Evidence supporting the claim. If given, verifies "
                "the fact immediately."
            ),
        ] = None,
        is_global: IsGlobalArg = False,
    ) -> dict[str, Any]:
        """Record a new fact, unverified by default. `proof`, if given,
        verifies it immediately. `is_global` files it into the shared
        global database instead of the local project (default `false`,
        same as the CLI's own `--global` default) -- the one creating tool
        on this surface, so the one tool that needs an explicit scope
        choice rather than inheriting one from an existing id.
        `session_id` defaults to this server's own session id if omitted.
        """

        def _fetch() -> dict[str, Any]:
            if not claim.strip():
                raise UsageError("invalid_claim", "claim must not be empty or whitespace-only")
            scope: Scope = "global" if is_global else "local"
            require_scope_available(config, scope)
            db_path = project_db_path(config) if scope == "local" else None
            with corvee_context(
                write=True, scope=scope, actor=config.actor, project_db_path=db_path
            ) as ctx:
                fact = insert_fact(
                    ctx.conn,
                    claim=claim,
                    actor=config.actor,
                    session_id=session_id_for(config, session_id),
                    proof=proof,
                    scope=scope,
                )
                return fact.to_dict()

        return cast(dict[str, Any], await run_tool(worker, _fetch))

    @app.tool(structured_output=True)
    async def fact_verify(
        ref: FactRefArg,
        proof: Annotated[str, Field(description="Evidence supporting the claim.")],
        session_id: SessionIdArg = None,
    ) -> dict[str, Any]:
        """Mark a fact verified, with proof. Re-verifying an already-verified
        fact succeeds and refreshes both. `session_id` defaults to this
        server's own session id if omitted.
        """

        def _fetch() -> dict[str, Any]:
            parsed = parse_fact_ref(str(ref))
            require_scope_available(config, parsed.scope)
            db_path = project_db_path(config) if parsed.scope == "local" else None
            with corvee_context(
                write=True,
                scope=parsed.scope,
                actor=config.actor,
                project_db_path=db_path,
            ) as ctx:
                fact = verify_fact(
                    ctx.conn,
                    parsed.id,
                    proof,
                    config.actor,
                    session_id=session_id_for(config, session_id),
                    scope=parsed.scope,
                )
                return fact.to_dict()

        return cast(dict[str, Any], await run_tool(worker, _fetch))

    @app.tool(structured_output=True)
    async def fact_show(ref: FactRefArg) -> dict[str, Any]:
        """Read one fact by id (FACT-<n>, FACT-GLOBAL-<n>, or a bare
        integer): claim, status, current proof, and its revision timeline.
        Read-only.
        """

        def _fetch() -> dict[str, Any]:
            parsed = parse_fact_ref(str(ref))
            require_scope_available(config, parsed.scope)
            db_path = project_db_path(config) if parsed.scope == "local" else None
            with corvee_context(
                write=False,
                scope=parsed.scope,
                actor=config.actor,
                project_db_path=db_path,
            ) as ctx:
                fact = require_fact(ctx.conn, parsed.id, scope=parsed.scope)
                detail = fact.to_dict()
                detail["events"] = get_fact_events(ctx.conn, fact.id)
                return detail

        return cast(dict[str, Any], await run_tool(worker, _fetch))
