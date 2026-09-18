#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click

from corvee.cli.completion import complete_task_ids
from corvee.cli.context import corvee_context
from corvee.db.tasks import apply_update
from corvee.models import parse_task_refs
from corvee.output import emit_tasks

EPILOG = """\
\b
Examples:
Claim a task and move it to in_progress in one call:
  corvee task start TASK-14
Start it and get the result as JSON:
  corvee task start 14 --json
Start a batch of tasks in one transaction:
  corvee task start 14 15 16 --json
Take over a claim someone else is holding, then start it:
  corvee task start 14 --force
"""


@click.command(epilog=EPILOG)
@click.argument("task_refs", nargs=-1, required=True, shell_complete=complete_task_ids)
@click.option("--force", "-f", is_flag=True, help="Steal a claim held by another actor.")
@click.option("--json", "-j", "as_json", is_flag=True)
def start(task_refs: tuple[str, ...], force: bool, as_json: bool) -> None:
    """Claim one or more tasks and move them to in_progress, in one transaction."""
    task_ids, scope = parse_task_refs(task_refs)
    with corvee_context(scope=scope) as ctx:
        results = [
            apply_update(
                ctx.conn,
                task_id,
                ctx.actor,
                session_id=ctx.session_id,
                state="in_progress",
                force=force,
                scope=scope,
            )[0]
            for task_id in task_ids
        ]
    emit_tasks([task.to_dict() for task in results], as_json=as_json)
