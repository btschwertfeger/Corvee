#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from corvee.cli.context import corvee_context
from corvee.constants import (
    DEFAULT_PRIORITY,
    DEFAULT_TASK_TYPE,
    PRIORITIES,
    RELATIONS,
    STATES,
    TASK_TYPES,
    Scope,
    narrow_priority,
    narrow_relation,
    narrow_state,
    narrow_task_type,
)
from corvee.db.labels import add_label, remove_label
from corvee.db.links import link_tasks, unlink_tasks
from corvee.db.tasks import (
    add_comment,
    apply_update,
    claim_task,
    insert_task,
    require_tasks,
    unclaim_task,
)
from corvee.errors import UsageError
from corvee.guards.labels import normalize_label
from corvee.guards.scope import assert_same_scope
from corvee.mcp.dispatch import UNCLAIM_CONFLICT_HINT, run_tool
from corvee.mcp.scope import require_scope_available
from corvee.mcp.server_config import ServerConfig
from corvee.mcp.tools_common import (
    IsGlobalArg,
    SessionIdArg,
    TaskRefArg,
    TaskRefsArg,
    _enum_field,
    project_db_path,
    session_id_for,
    write_context,
    write_context_batch,
)
from corvee.mcp.worker import DbWorker
from corvee.models import parse_task_ref


def register_write_tools(app: MCPServer, config: ServerConfig, worker: DbWorker) -> None:
    """Registers the write tools: `task_claim`, `task_unclaim`,
    `task_comment`, `task_start`, `task_done`, `task_cancel`,
    `task_review`, `task_reopen`, `task_block`, `task_add`, `task_update`,
    `task_label`, `task_unlabel`, `task_link`, `task_unlink` (spec §10.3).
    Every one of these writes an event; `session_id` is optional on each,
    defaulting to the server's own `ServerConfig.session_id` (§10.1) when
    a call omits it.
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

        return await run_tool(worker, _fetch, claim_conflict_hint=UNCLAIM_CONFLICT_HINT)

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
    async def task_reopen(ref: TaskRefArg, session_id: SessionIdArg = None) -> dict[str, Any]:
        """Move a task back to open. Use this to undo a mis-cancel or a
        premature done: `task_start`/`task_review`/`task_block` refuse an
        already-`cancelled`/`done` task with `invalid_transition`, and
        `task_claim` refuses one with `task_terminal`, so before this tool
        there was no way back from either state on this surface. Fails
        with `invalid_transition` itself when called from `review`, the
        one state `open` is not reachable from directly (§4.5).
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
                    state="open",
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

    @app.tool(structured_output=True)
    async def task_update(
        refs: TaskRefsArg,
        session_id: SessionIdArg = None,
        title: Annotated[
            str | None, Field(description="New title. Omit to leave unchanged.")
        ] = None,
        description: Annotated[
            str | None, Field(description="New description. Omit to leave unchanged.")
        ] = None,
        task_type: Annotated[
            str | None, _enum_field("The kind of work this task represents.", TASK_TYPES)
        ] = None,
        priority: Annotated[
            str | None, _enum_field("How urgently this task should be picked up.", PRIORITIES)
        ] = None,
        state: Annotated[str | None, _enum_field("New state to transition to.", STATES)] = None,
        force: Annotated[
            bool, Field(description="Override a claim held by another actor.")
        ] = False,
        cascade: Annotated[
            bool, Field(description="Cancel every open descendant along with the parent.")
        ] = False,
    ) -> dict[str, Any]:
        """Mutate one or more tasks in a single transaction, mirroring
        `corvee task update` in full -- the one tool on this surface that
        exposes `force`/`cascade` directly (spec §10.4 explains why that
        does not reopen the hidden-argument problem the narrower
        state-transition tools above exist to avoid). A caller only
        wanting a plain state transition should still reach for
        task_start/task_done/task_cancel/task_review/task_reopen/
        task_block instead. Returns `{"result": [...]}`, one entry per
        updated task, including any `cascade`-cancelled descendants.
        """

        def _fetch() -> dict[str, Any]:
            if task_type is not None and task_type not in TASK_TYPES:
                raise UsageError(
                    "invalid_type",
                    f"invalid task_type {task_type!r}: expected one of {TASK_TYPES}",
                )
            if priority is not None and priority not in PRIORITIES:
                raise UsageError(
                    "invalid_priority",
                    f"invalid priority {priority!r}: expected one of {PRIORITIES}",
                )
            if state is not None and state not in STATES:
                raise UsageError(
                    "invalid_state", f"invalid state {state!r}: expected one of {STATES}"
                )
            resolved_session_id = session_id_for(config, session_id)
            task_ids, scope, ctx_cm = write_context_batch(config, refs)
            with ctx_cm as ctx:
                results = []
                for task_id in task_ids:
                    results.extend(
                        apply_update(
                            ctx.conn,
                            task_id,
                            config.actor,
                            session_id=resolved_session_id,
                            title=title,
                            description=description,
                            type_=narrow_task_type(task_type) if task_type is not None else None,
                            priority=narrow_priority(priority) if priority is not None else None,
                            state=narrow_state(state) if state is not None else None,
                            force=force,
                            cascade=cascade,
                            scope=scope,
                        )
                    )
                return {"result": [task.to_dict() for task in results]}

        return await run_tool(worker, _fetch)

    @app.tool(structured_output=True)
    async def task_label(
        refs: TaskRefsArg,
        label: Annotated[str, Field(description="Label name to attach.")],
        session_id: SessionIdArg = None,
    ) -> dict[str, Any]:
        """Attach one label to one or more tasks, mirroring `corvee task
        label --add`. `label` is normalized and pattern-validated the
        same way the CLI validates it. A no-op success if a task already
        carries the label. Returns `{"result": [...]}`, one entry per
        task. `session_id` defaults to this server's own session id if
        omitted.
        """

        def _fetch() -> dict[str, Any]:
            normalized = normalize_label(label)
            resolved_session_id = session_id_for(config, session_id)
            task_ids, scope, ctx_cm = write_context_batch(config, refs)
            with ctx_cm as ctx:
                require_tasks(ctx.conn, task_ids, scope=scope)
                for task_id in task_ids:
                    add_label(ctx.conn, task_id, normalized, config.actor, resolved_session_id)
                tasks = require_tasks(ctx.conn, task_ids, scope=scope)
                return {"result": [task.to_dict() for task in tasks]}

        return await run_tool(worker, _fetch)

    @app.tool(structured_output=True)
    async def task_unlabel(
        refs: TaskRefsArg,
        label: Annotated[str, Field(description="Label name to remove.")],
        session_id: SessionIdArg = None,
    ) -> dict[str, Any]:
        """Remove one label from one or more tasks, mirroring `corvee task
        label --remove`, as its own verb rather than folded into
        `task_label` behind a direction argument. A no-op success if a
        task does not carry the label. Returns `{"result": [...]}`, one
        entry per task. `session_id` defaults to this server's own
        session id if omitted.
        """

        def _fetch() -> dict[str, Any]:
            normalized = normalize_label(label)
            resolved_session_id = session_id_for(config, session_id)
            task_ids, scope, ctx_cm = write_context_batch(config, refs)
            with ctx_cm as ctx:
                require_tasks(ctx.conn, task_ids, scope=scope)
                for task_id in task_ids:
                    remove_label(ctx.conn, task_id, normalized, config.actor, resolved_session_id)
                tasks = require_tasks(ctx.conn, task_ids, scope=scope)
                return {"result": [task.to_dict() for task in tasks]}

        return await run_tool(worker, _fetch)

    @app.tool(structured_output=True)
    async def task_link(
        source_ref: TaskRefArg,
        target_ref: TaskRefArg,
        relation: Annotated[str, _enum_field("How the two tasks relate.", RELATIONS)],
        session_id: SessionIdArg = None,
    ) -> dict[str, Any]:
        """Relate two tasks, mirroring `corvee task link`, including the
        cycle check for `blocks`/`parent_of`. `source_ref` and
        `target_ref` must share one scope, checked the same way the CLI
        checks it, and a self-link is rejected too. For `parent_of`,
        `source_ref` is the parent and `target_ref` is the child --
        argument order matters. A `parent_of` link attaching a
        non-terminal child to an already-`done` parent still succeeds,
        with a `warnings` entry on the parent's returned object. Each
        call names two distinct refs, not a batch of the same kind, so
        this returns `{"result": [source, target]}`, always two objects.
        `session_id` defaults to this server's own session id if
        omitted.
        """

        def _fetch() -> dict[str, Any]:
            if relation not in RELATIONS:
                raise UsageError(
                    "invalid_relation",
                    f"invalid relation {relation!r}: expected one of {RELATIONS}",
                )
            target = parse_task_ref(str(target_ref))
            resolved_session_id = session_id_for(config, session_id)
            parsed, ctx_cm = write_context(config, source_ref)
            assert_same_scope(parsed.scope, target.scope)
            with ctx_cm as ctx:
                warnings = link_tasks(
                    ctx.conn,
                    parsed.id,
                    target.id,
                    narrow_relation(relation),
                    config.actor,
                    resolved_session_id,
                    scope=parsed.scope,
                )
                tasks = require_tasks(ctx.conn, [parsed.id, target.id], scope=parsed.scope)
            dicts = []
            for task in tasks:
                detail = task.to_dict()
                if task.id in warnings:
                    detail["warnings"] = [warnings[task.id]]
                dicts.append(detail)
            return {"result": dicts}

        return await run_tool(worker, _fetch)

    @app.tool(structured_output=True)
    async def task_unlink(
        source_ref: TaskRefArg,
        target_ref: TaskRefArg,
        relation: Annotated[
            str, _enum_field("The relation to remove between the two tasks.", RELATIONS)
        ],
        session_id: SessionIdArg = None,
    ) -> dict[str, Any]:
        """Remove a link between two tasks, mirroring `corvee task
        unlink`. A no-op success if the two tasks were not linked by
        that `relation`. Returns `{"result": [source, target]}`, the
        same two-object shape `task_link` uses. `session_id` defaults to
        this server's own session id if omitted.
        """

        def _fetch() -> dict[str, Any]:
            if relation not in RELATIONS:
                raise UsageError(
                    "invalid_relation",
                    f"invalid relation {relation!r}: expected one of {RELATIONS}",
                )
            target = parse_task_ref(str(target_ref))
            resolved_session_id = session_id_for(config, session_id)
            parsed, ctx_cm = write_context(config, source_ref)
            assert_same_scope(parsed.scope, target.scope)
            with ctx_cm as ctx:
                unlink_tasks(
                    ctx.conn,
                    parsed.id,
                    target.id,
                    narrow_relation(relation),
                    config.actor,
                    resolved_session_id,
                    scope=parsed.scope,
                )
                tasks = require_tasks(ctx.conn, [parsed.id, target.id], scope=parsed.scope)
            return {"result": [task.to_dict() for task in tasks]}

        return await run_tool(worker, _fetch)
