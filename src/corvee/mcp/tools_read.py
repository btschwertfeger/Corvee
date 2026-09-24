#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

from datetime import UTC, datetime
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from corvee.cli.commands.brief import labels_section, mine_section, ready_section, stale_section
from corvee.cli.context import corvee_context
from corvee.cli.scope import sort_facts, sort_tasks
from corvee.db.events import get_task_events
from corvee.db.facts import search_facts
from corvee.db.labels import list_task_labels
from corvee.db.links import get_children, get_task_links
from corvee.db.tasks import require_task, search_tasks
from corvee.mcp.dispatch import run_tool
from corvee.mcp.scope import fetch_merged_for_config, require_scope_available
from corvee.mcp.server_config import ServerConfig
from corvee.mcp.tools_common import (
    LimitArg,
    TaskRefArg,
    project_db_path,
    scope_filter_field,
    validate_limit,
    validate_scope_filter,
)
from corvee.mcp.worker import DbWorker
from corvee.models import parse_task_ref, task_ref
from corvee.timeutil import parse_duration, timestamp


def register_read_tools(app: MCPServer, config: ServerConfig, worker: DbWorker) -> None:
    """Registers the read-only tools: `task_show`, `brief`, `fact_search`,
    `task_search` (spec §10.3). None of these accept `session_id` -- they
    write no events.
    """

    @app.tool(structured_output=True)
    async def task_show(
        ref: TaskRefArg,
        since: Annotated[
            str | int | float | None,
            Field(
                description="Only include events newer than this duration ago "
                '(e.g. "7d", "4h"). Omit for the full timeline.'
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Read one task by id (TASK-<n>, TASK-GLOBAL-<n>, or a bare integer):
        description, labels, links, subtasks, and its event timeline.
        Read-only.
        """

        def _fetch() -> dict[str, Any]:
            since_cutoff = (
                timestamp(datetime.now(UTC) - parse_duration(str(since))) if since else None
            )
            parsed = parse_task_ref(str(ref))
            require_scope_available(config, parsed.scope)
            db_path = project_db_path(config) if parsed.scope == "local" else None
            with corvee_context(
                write=False,
                scope=parsed.scope,
                actor=config.actor,
                project_db_path=db_path,
            ) as ctx:
                task = require_task(ctx.conn, parsed.id, scope=parsed.scope)
                detail = task.to_dict()
                detail["labels"] = list_task_labels(ctx.conn, task.id)
                detail["links"] = get_task_links(ctx.conn, task.id, scope=parsed.scope)
                detail["subtasks"] = [
                    task_ref(child_id, parsed.scope) for child_id in get_children(ctx.conn, task.id)
                ]
                events, omitted = get_task_events(ctx.conn, task.id, since=since_cutoff)
                detail["events"] = events
                detail["events_omitted"] = omitted
                return detail

        return await run_tool(worker, _fetch)

    @app.tool(structured_output=True)
    async def brief(
        scope: Annotated[
            str, scope_filter_field("Which database(s) to draw the snapshot from.")
        ] = "all",
    ) -> dict[str, Any]:
        """Session-start snapshot in one call: tasks claimed by (or assigned
        and unclaimed to) this actor, up to 5 ready-to-start tasks, tasks
        whose claim has gone stale, and the project's label vocabulary.
        Read-only.
        """

        def _fetch() -> dict[str, Any]:
            scope_filter = validate_scope_filter(scope)
            if scope_filter == "local":
                require_scope_available(config, "local")
            db_path = project_db_path(config)
            local_available = config.project is not None
            return {
                "mine": mine_section(
                    scope_filter,
                    actor=config.actor,
                    project_db_path=db_path,
                    local_available=local_available,
                ),
                "ready": ready_section(
                    scope_filter,
                    actor=config.actor,
                    project_db_path=db_path,
                    local_available=local_available,
                ),
                "stale": stale_section(
                    scope_filter,
                    actor=config.actor,
                    project_db_path=db_path,
                    local_available=local_available,
                ),
                "labels": labels_section(
                    actor=config.actor, project_db_path=db_path, has_project=local_available
                ),
            }

        return await run_tool(worker, _fetch)

    @app.tool(structured_output=True)
    async def fact_search(
        text: Annotated[
            str, Field(description="Substring to match against the claim, case-insensitive.")
        ],
        scope: Annotated[str, scope_filter_field("Which database(s) to search.")] = "all",
        limit: LimitArg = 20,
        include_retracted: Annotated[
            bool, Field(description="Also match retracted facts (excluded by default).")
        ] = False,
        include_proof: Annotated[
            bool, Field(description="Also match against proof text, not just claim text.")
        ] = False,
        verified_by: Annotated[
            str | None, Field(description="Only facts verified by this actor.")
        ] = None,
    ) -> dict[str, Any]:
        """Facts whose claim contains <text>, case-insensitive. `limit`
        (default 20) applies to the merged, sorted result across every scope
        searched, never per database. `omitted` reports how many further
        matches `limit` cut off, so a capped `result` is never mistaken
        for "no more matches exist". Read-only.
        """

        def _fetch() -> dict[str, Any]:
            scope_filter = validate_scope_filter(scope)
            capped_limit = validate_limit(limit)
            facts = sort_facts(
                fetch_merged_for_config(
                    config,
                    scope_filter,
                    lambda conn, s: search_facts(
                        conn,
                        text,
                        include_all=include_retracted,
                        include_proof=include_proof,
                        verified_by=verified_by,
                        scope=s,
                    ),
                )
            )
            return {
                "result": [f.to_dict() for f in facts[:capped_limit]],
                "omitted": max(0, len(facts) - capped_limit),
            }

        return await run_tool(worker, _fetch)

    @app.tool(structured_output=True)
    async def task_search(
        text: Annotated[
            str,
            Field(
                description="Substring to match against each task's title or "
                "description, case-insensitive."
            ),
        ],
        scope: Annotated[str, scope_filter_field("Which database(s) to search.")] = "all",
        limit: LimitArg = 20,
        include_all: Annotated[
            bool, Field(description="Also match done/cancelled tasks (excluded by default).")
        ] = False,
        include_comments: Annotated[
            bool,
            Field(description="Also match against comment bodies, not just title/description."),
        ] = False,
    ) -> dict[str, Any]:
        """Tasks whose title or description contains <text>, case-insensitive.
        `include_all` also matches done/cancelled tasks (excluded by
        default). `include_comments` also matches comment bodies, not just
        title/description. `limit` (default 20) applies to the merged,
        sorted result across every scope searched, never per database.
        `omitted` reports how many further matches `limit` cut off, so a
        capped `result` is never mistaken for "no task like this exists
        yet" when checking for a duplicate before filing one. Read-only.
        """

        def _fetch() -> dict[str, Any]:
            scope_filter = validate_scope_filter(scope)
            capped_limit = validate_limit(limit)
            tasks = sort_tasks(
                fetch_merged_for_config(
                    config,
                    scope_filter,
                    lambda conn, s: search_tasks(
                        conn,
                        text,
                        include_all=include_all,
                        include_comments=include_comments,
                        scope=s,
                    ),
                )
            )
            return {
                "result": [t.to_dict() for t in tasks[:capped_limit]],
                "omitted": max(0, len(tasks) - capped_limit),
            }

        return await run_tool(worker, _fetch)
