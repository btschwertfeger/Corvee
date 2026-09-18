#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

from typing import cast

import click

from corvee.cli.completion import complete_task_ids
from corvee.cli.context import corvee_context
from corvee.cli.params import StdinOrValue
from corvee.constants import PRIORITIES, STATES, TASK_TYPES, Priority, State, TaskType
from corvee.db.tasks import apply_update
from corvee.models import parse_task_refs
from corvee.output import emit_tasks

EPILOG = """\
\b
Examples:
Move a task into progress:
  corvee task update TASK-14 --state in_progress
Bump the priority of several tasks at once, as JSON:
  corvee task update 14 15 16 --priority high --json
Finish a task even though someone else holds the claim:
  corvee task update 14 --state done --force
"""


@click.command(epilog=EPILOG)
@click.argument("task_refs", nargs=-1, required=True, shell_complete=complete_task_ids)
@click.option("--state", "-S", type=click.Choice(STATES))
@click.option("--type", "-t", "type_", type=click.Choice(TASK_TYPES))
@click.option("--priority", "-p", type=click.Choice(PRIORITIES))
@click.option("--title", "-T", type=StdinOrValue())
@click.option("--description", "-d", type=StdinOrValue())
@click.option("--force", "-f", is_flag=True, help="Override a claim held by another actor.")
@click.option(
    "--cascade",
    "-c",
    is_flag=True,
    help="Cancel every open descendant along with the parent.",
)
@click.option("--json", "-j", "as_json", is_flag=True)
def update(
    task_refs: tuple[str, ...],
    state: str | None,
    type_: str | None,
    priority: str | None,
    title: str | None,
    description: str | None,
    force: bool,
    cascade: bool,
    as_json: bool,
) -> None:
    """Mutate one or more tasks in a single transaction."""
    task_ids, scope = parse_task_refs(task_refs)
    results = []
    with corvee_context(scope=scope) as ctx:
        for task_id in task_ids:
            updated = apply_update(
                ctx.conn,
                task_id,
                ctx.actor,
                session_id=ctx.session_id,
                title=title,
                description=description,
                type_=cast(TaskType, type_) if type_ else None,
                priority=cast(Priority, priority) if priority else None,
                state=cast(State, state) if state else None,
                force=force,
                cascade=cascade,
                scope=scope,
            )
            results.extend(updated)
    emit_tasks([task.to_dict() for task in results], as_json=as_json)
