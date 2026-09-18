#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click

from corvee.cli.completion import complete_task_ids
from corvee.cli.context import corvee_context
from corvee.db.tasks import assign_task
from corvee.errors import UsageError
from corvee.models import parse_task_refs
from corvee.output import emit_tasks

EPILOG = """\
\b
Examples:
Route a task to a specific actor without claiming it:
  corvee task assign TASK-14 --to agent:claude
Assign a batch of tasks in one call:
  corvee task assign 14 15 16 --to agent:claude --json
Reassign a task already assigned to someone else:
  corvee task assign 14 --to human:alice --json
"""


@click.command(epilog=EPILOG)
@click.argument("task_refs", nargs=-1, required=True, shell_complete=complete_task_ids)
@click.option("--to", "-t", "target", required=True, help="The actor this task is routed to.")
@click.option("--json", "-j", "as_json", is_flag=True)
def assign(task_refs: tuple[str, ...], target: str, as_json: bool) -> None:
    """Route one or more tasks to a specific actor, without claiming them.

    Advisory only: not gated by an existing claim, and does not itself claim
    the task. `task mine` surfaces it for the assigned actor once unclaimed.
    """
    if not target.strip():
        raise UsageError("invalid_target", "--to must not be empty or whitespace-only")
    task_ids, scope = parse_task_refs(task_refs)
    with corvee_context(scope=scope) as ctx:
        tasks = [
            assign_task(
                ctx.conn, task_id, target, ctx.actor, session_id=ctx.session_id, scope=scope
            )
            for task_id in task_ids
        ]
    emit_tasks([task.to_dict() for task in tasks], as_json=as_json)
