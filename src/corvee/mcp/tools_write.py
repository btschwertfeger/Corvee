#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from corvee.cli.context import corvee_context
from corvee.constants import DEFAULT_PRIORITY, DEFAULT_TASK_TYPE, PRIORITIES, TASK_TYPES, Scope
from corvee.db.tasks import add_comment, apply_update, claim_task, insert_task, unclaim_task
from corvee.errors import UsageError
from corvee.mcp.dispatch import run_tool
from corvee.mcp.scope import require_scope_available
from corvee.mcp.server_config import ServerConfig
from corvee.mcp.tools_common import (
    IsGlobalArg,
    SessionIdArg,
    TaskRefArg,
    _enum_field,
    project_db_path,
    session_id_for,
    write_context,
)
from corvee.mcp.worker import DbWorker


def register_write_tools(app: MCPServer, config: ServerConfig, worker: DbWorker) -> None:
    """Registers the write tools: `task_claim`, `task_unclaim`,
    `task_comment`, `task_start`, `task_done`, `task_cancel`,
    `task_review`, `task_block`, `task_add` (spec §10.3). Every one of
    these writes an event; `session_id` is optional on each, defaulting to
    the server's own `ServerConfig.session_id` (§10.1) when a call omits
    it.
    """

    @app.tool(structured_output=True)
    async def task_claim(
        ref: TaskRefArg,
        session_id: SessionIdArg = None,
        force: Annotated[
            bool, Field(description="Steal a claim currently held by another actor.")
        ] = False,
    ) -> dict[str, Any]:
        """Claim a task (TASK-<n>, TASK-GLOBAL-<n>, or a bare integer).
        `force` steals a claim held by another actor. `session_id` defaults
        to this server's own session id if omitted.
        """

        def _fetch() -> dict[str, Any]:
            parsed, ctx_cm = write_context(config, ref)
            with ctx_cm as ctx:
                task = claim_task(
                    ctx.conn,
                    parsed.id,
                    config.actor,
                    force=force,
                    session_id=session_id_for(config, session_id),
                    scope=parsed.scope,
                )
                return task.to_dict()

        return await run_tool(worker, _fetch)

    @app.tool(structured_output=True)
    async def task_unclaim(
        ref: TaskRefArg,
        session_id: SessionIdArg = None,
        force: Annotated[
            bool,
            Field(
                description="Release a claim held by another actor "
                "(typically stale). Without it, only the current claimant "
                "can unclaim."
            ),
        ] = False,
    ) -> dict[str, Any]:
        """Release a claim. Only the current claimant may do this without
        `force`; `force` releases someone else's (typically stale) claim.
        `session_id` defaults to this server's own session id if omitted.
        """

        def _fetch() -> dict[str, Any]:
            parsed, ctx_cm = write_context(config, ref)
            with ctx_cm as ctx:
                task = unclaim_task(
                    ctx.conn,
                    parsed.id,
                    config.actor,
                    force=force,
                    session_id=session_id_for(config, session_id),
                    scope=parsed.scope,
                )
                return task.to_dict()

        return await run_tool(worker, _fetch)

    @app.tool(structured_output=True)
    async def task_comment(
        ref: TaskRefArg,
        text: Annotated[str, Field(description="The comment body.")],
        session_id: SessionIdArg = None,
    ) -> dict[str, Any]:
        """Leave a note on a task. Not claim-gated (§4.4): any actor can
        comment at any time. `session_id` defaults to this server's own
        session id if omitted.
        """

        def _fetch() -> dict[str, Any]:
            parsed, ctx_cm = write_context(config, ref)
            with ctx_cm as ctx:
                task = add_comment(
                    ctx.conn,
                    parsed.id,
                    text,
                    config.actor,
                    session_id_for(config, session_id),
                    scope=parsed.scope,
                )
                return task.to_dict()

        return await run_tool(worker, _fetch)

    @app.tool(structured_output=True)
    async def task_start(ref: TaskRefArg, session_id: SessionIdArg = None) -> dict[str, Any]:
        """Claim (if unclaimed) and move to in_progress in one call. To take
        over a stale claim first, call `task_claim(force=true)`.
        `session_id` defaults to this server's own session id if omitted.
        """

        def _fetch() -> dict[str, Any]:
            parsed, ctx_cm = write_context(config, ref)
            with ctx_cm as ctx:
                tasks = apply_update(
                    ctx.conn,
                    parsed.id,
                    config.actor,
                    session_id=session_id_for(config, session_id),
                    state="in_progress",
                    force=False,
                    scope=parsed.scope,
                )
                return tasks[0].to_dict()

        return await run_tool(worker, _fetch)

    @app.tool(structured_output=True)
    async def task_done(ref: TaskRefArg, session_id: SessionIdArg = None) -> dict[str, Any]:
        """Move a task to done, clearing its claim. `session_id` defaults to
        this server's own session id if omitted.
        """

        def _fetch() -> dict[str, Any]:
            parsed, ctx_cm = write_context(config, ref)
            with ctx_cm as ctx:
                tasks = apply_update(
                    ctx.conn,
                    parsed.id,
                    config.actor,
                    session_id=session_id_for(config, session_id),
                    state="done",
                    force=False,
                    scope=parsed.scope,
                )
                return tasks[0].to_dict()

        return await run_tool(worker, _fetch)

    @app.tool(structured_output=True)
    async def task_cancel(ref: TaskRefArg, session_id: SessionIdArg = None) -> dict[str, Any]:
        """Move a task to cancelled, clearing its claim. Use this for a task
        that turned out obsolete, not for one that was actually finished --
        `task_done` is `done`, this is `cancelled`. `session_id` defaults to
        this server's own session id if omitted.
        """

        def _fetch() -> dict[str, Any]:
            parsed, ctx_cm = write_context(config, ref)
            with ctx_cm as ctx:
                tasks = apply_update(
                    ctx.conn,
                    parsed.id,
                    config.actor,
                    session_id=session_id_for(config, session_id),
                    state="cancelled",
                    force=False,
                    scope=parsed.scope,
                )
                return tasks[0].to_dict()

        return await run_tool(worker, _fetch)

    @app.tool(structured_output=True)
    async def task_review(ref: TaskRefArg, session_id: SessionIdArg = None) -> dict[str, Any]:
        """Move a task to review: the work is done but needs someone else to
        check it before it counts as `done`. Keeps the current claim (§4.4:
        `review` is not a terminal state). `session_id` defaults to this
        server's own session id if omitted.
        """

        def _fetch() -> dict[str, Any]:
            parsed, ctx_cm = write_context(config, ref)
            with ctx_cm as ctx:
                tasks = apply_update(
                    ctx.conn,
                    parsed.id,
                    config.actor,
                    session_id=session_id_for(config, session_id),
                    state="review",
                    force=False,
                    scope=parsed.scope,
                )
                return tasks[0].to_dict()

        return await run_tool(worker, _fetch)

    @app.tool(structured_output=True)
    async def task_block(
        ref: TaskRefArg,
        comment: Annotated[
            str, Field(description="Non-empty explanation of why the task is blocked. Required.")
        ],
        session_id: SessionIdArg = None,
    ) -> dict[str, Any]:
        """Move a task to blocked. Requires a non-empty `comment` explaining
        why, enforced only on this MCP surface (not the CLI): `blocked` is
        not self-explanatory the way `done`/`cancelled` are, and a subagent
        cannot be relied on to leave one unless it is required. The comment
        is written before the state change, in the same transaction, so a
        rejected transition (e.g. `done` -> `blocked`) rolls the comment
        back too. `session_id` defaults to this server's own session id if
        omitted.
        """

        def _fetch() -> dict[str, Any]:
            if not comment.strip():
                raise UsageError(
                    "comment_required",
                    "task_block requires a non-empty comment explaining why the task is blocked",
                )
            resolved_session_id = session_id_for(config, session_id)
            parsed, ctx_cm = write_context(config, ref)
            with ctx_cm as ctx:
                add_comment(
                    ctx.conn,
                    parsed.id,
                    comment,
                    config.actor,
                    resolved_session_id,
                    scope=parsed.scope,
                )
                tasks = apply_update(
                    ctx.conn,
                    parsed.id,
                    config.actor,
                    session_id=resolved_session_id,
                    state="blocked",
                    force=False,
                    scope=parsed.scope,
                )
                return tasks[0].to_dict()

        return await run_tool(worker, _fetch)

    @app.tool(structured_output=True)
    async def task_add(
        title: Annotated[str, Field(description="Short task title. Must not be empty.")],
        description: Annotated[str, Field(description="Task description/body. Must not be empty.")],
        session_id: SessionIdArg = None,
        task_type: Annotated[
            str, _enum_field("The kind of work this task represents.", TASK_TYPES)
        ] = DEFAULT_TASK_TYPE,
        priority: Annotated[
            str, _enum_field("How urgently this task should be picked up.", PRIORITIES)
        ] = DEFAULT_PRIORITY,
        is_global: IsGlobalArg = False,
    ) -> dict[str, Any]:
        """File a new task. Never claims it -- filing work and starting it
        are separate acts (§4.4); claim it with task_claim or task_start
        once you're ready to work it. `title` and `description` must both
        be non-empty. `is_global` files it into the shared global database
        instead of the local project (default `false`, same as `fact_add`).
        `session_id` defaults to this server's own session id if omitted.
        """

        def _fetch() -> dict[str, Any]:
            if not title.strip():
                raise UsageError("invalid_title", "title must not be empty or whitespace-only")
            if not description.strip():
                raise UsageError(
                    "invalid_description", "description must not be empty or whitespace-only"
                )
            if task_type not in TASK_TYPES:
                raise UsageError(
                    "invalid_type", f"invalid task_type {task_type!r}: expected one of {TASK_TYPES}"
                )
            if priority not in PRIORITIES:
                raise UsageError(
                    "invalid_priority",
                    f"invalid priority {priority!r}: expected one of {PRIORITIES}",
                )
            scope: Scope = "global" if is_global else "local"
            require_scope_available(config, scope)
            db_path = project_db_path(config) if scope == "local" else None
            with corvee_context(
                write=True, scope=scope, actor=config.actor, project_db_path=db_path
            ) as ctx:
                task = insert_task(
                    ctx.conn,
                    title=title,
                    description=description,
                    type_=task_type,
                    priority=priority,
                    scope=scope,
                    actor=config.actor,
                    session_id=session_id_for(config, session_id),
                )
                return task.to_dict()

        return await run_tool(worker, _fetch)
