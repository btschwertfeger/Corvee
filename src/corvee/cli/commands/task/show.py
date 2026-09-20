#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3
from contextlib import ExitStack
from datetime import UTC, datetime

import click

from corvee.cli.completion import complete_task_ids
from corvee.cli.context import corvee_context
from corvee.constants import Scope
from corvee.db.events import get_task_events
from corvee.db.labels import list_task_labels
from corvee.db.links import get_children, get_task_links
from corvee.db.tasks import require_tasks
from corvee.models import parse_task_refs, task_ref
from corvee.output import emit_task_detail
from corvee.references import find_referenced
from corvee.timeutil import parse_duration, timestamp

EPILOG = """\
\b
Examples:
See full detail for one task, including its event timeline:
  corvee task show TASK-14
Show several tasks at once, as JSON:
  corvee task show 14 15 16 --json
Only include events from the last week:
  corvee task show TASK-14 --since 7d --json
"""


@click.command(epilog=EPILOG)
@click.argument("ids", nargs=-1, required=True, shell_complete=complete_task_ids)
@click.option("--since", "-d", "since_duration", default=None, help="Only events newer than this.")
@click.option(
    "--no-events",
    "-n",
    is_flag=True,
    help="Drop the timeline; keep description/labels/links/subtasks.",
)
@click.option("--json", "-j", "as_json", is_flag=True)
def show(ids: tuple[str, ...], since_duration: str | None, no_events: bool, as_json: bool) -> None:
    """Full detail for one or more tasks: description, labels, links, subtasks, timeline."""
    task_ids, scope = parse_task_refs(ids)
    since = (
        timestamp(datetime.now(UTC) - parse_duration(since_duration)) if since_duration else None
    )
    other_scope: Scope = "global" if scope == "local" else "local"
    results = []
    with ExitStack() as stack:
        ctx = stack.enter_context(corvee_context(write=False, scope=scope))
        other_conn_holder: list[sqlite3.Connection] = []

        def other_conn() -> sqlite3.Connection:
            if not other_conn_holder:
                other_ctx = stack.enter_context(corvee_context(write=False, scope=other_scope))
                other_conn_holder.append(other_ctx.conn)
            return other_conn_holder[0]

        tasks = require_tasks(ctx.conn, task_ids, scope=scope)
        for task in tasks:
            detail = task.to_dict()
            detail["labels"] = list_task_labels(ctx.conn, task.id)
            detail["links"] = get_task_links(ctx.conn, task.id, scope=scope)
            detail["subtasks"] = [
                task_ref(child_id, scope) for child_id in get_children(ctx.conn, task.id)
            ]
            full_events, _ = get_task_events(ctx.conn, task.id)
            if no_events:
                detail["events"] = []
                detail["events_omitted"] = len(full_events)
            else:
                events, omitted = get_task_events(ctx.conn, task.id, since=since)
                detail["events"] = events
                detail["events_omitted"] = omitted
            detail["referenced"] = find_referenced(
                [
                    task.description,
                    *(event.get("body") for event in full_events),
                    *(event.get("old_value") for event in full_events),
                    *(event.get("new_value") for event in full_events),
                ],
                own_kind="task",
                own_id=task.id,
                own_scope=scope,
                same_scope_conn=ctx.conn,
                other_scope_conn=other_conn,
            )
            results.append(detail)
    emit_task_detail(results, as_json=as_json)
