#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click

from corvee.cli.completion import complete_task_ids
from corvee.cli.context import corvee_context
from corvee.db.tasks import unclaim_task
from corvee.models import parse_task_refs
from corvee.output import emit_tasks

EPILOG = """\
\b
Examples:
Release a task you're done with for now, without finishing it:
  corvee task unclaim TASK-14
Unclaim and get the result as JSON:
  corvee task unclaim 14 --json
Release every claim before ending a session:
  corvee task unclaim 14 15 16 --json
Release a claim held by another actor:
  corvee task unclaim 14 --force
"""


@click.command(epilog=EPILOG)
@click.argument("task_refs", nargs=-1, required=True, shell_complete=complete_task_ids)
@click.option("--force", "-f", is_flag=True, help="Release a claim held by another actor.")
@click.option("--json", "-j", "as_json", is_flag=True)
def unclaim(task_refs: tuple[str, ...], force: bool, as_json: bool) -> None:
    """Release a claim on one or more tasks."""
    task_ids, scope = parse_task_refs(task_refs)
    with corvee_context(scope=scope) as ctx:
        tasks = [
            unclaim_task(
                ctx.conn, task_id, ctx.actor, force=force, session_id=ctx.session_id, scope=scope
            )
            for task_id in task_ids
        ]
    emit_tasks([task.to_dict() for task in tasks], as_json=as_json)
