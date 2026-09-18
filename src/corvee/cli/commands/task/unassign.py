#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click

from corvee.cli.completion import complete_task_ids
from corvee.cli.context import corvee_context
from corvee.db.tasks import unassign_task
from corvee.models import parse_task_refs
from corvee.output import emit_tasks

EPILOG = """\
\b
Examples:
Clear a task's assignment:
  corvee task unassign TASK-14
Unassign and get the result as JSON:
  corvee task unassign 14 --json
Clear a batch of assignments in one call:
  corvee task unassign 14 15 16 --json
"""


@click.command(epilog=EPILOG)
@click.argument("task_refs", nargs=-1, required=True, shell_complete=complete_task_ids)
@click.option("--json", "-j", "as_json", is_flag=True)
def unassign(task_refs: tuple[str, ...], as_json: bool) -> None:
    """Clear the assignment on one or more tasks."""
    task_ids, scope = parse_task_refs(task_refs)
    with corvee_context(scope=scope) as ctx:
        tasks = [
            unassign_task(ctx.conn, task_id, ctx.actor, session_id=ctx.session_id, scope=scope)
            for task_id in task_ids
        ]
    emit_tasks([task.to_dict() for task in tasks], as_json=as_json)
