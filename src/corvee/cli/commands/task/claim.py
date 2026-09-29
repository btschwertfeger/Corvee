#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click

from corvee.cli.completion import complete_task_ids
from corvee.cli.context import corvee_context
from corvee.cli.params import output_option
from corvee.constants import narrow_output_format
from corvee.db.tasks import claim_task
from corvee.models import parse_task_refs
from corvee.output import emit_tasks

EPILOG = """\
\b
Examples:
Start working on a task:
  corvee task claim TASK-14
See who now holds it and since when, which the default table drops:
  corvee task claim 14 -o wide
Claim it and get the result as JSON:
  corvee task claim 14 -o json
Claim a batch of ready tasks in one call:
  corvee task claim 14 15 16 -o json
Take over a claim someone else is holding:
  corvee task claim 14 --force
Claim a task filed with --global the same way as a local one:
  corvee task claim TASK-GLOBAL-3 -o json
"""


@click.command(epilog=EPILOG)
@click.argument("task_refs", nargs=-1, required=True, shell_complete=complete_task_ids)
@click.option("--force", "-f", is_flag=True, help="Steal a claim held by another actor.")
@output_option(wide=True)
def claim(task_refs: tuple[str, ...], force: bool, output_format: str) -> None:
    """Claim one or more tasks for $CORVEE_ACTOR, or refresh a claim already held."""
    task_ids, scope = parse_task_refs(task_refs)
    with corvee_context(scope=scope) as ctx:
        tasks = [
            claim_task(
                ctx.conn, task_id, ctx.actor, force=force, session_id=ctx.session_id, scope=scope
            )
            for task_id in task_ids
        ]
    emit_tasks([task.to_dict() for task in tasks], output=narrow_output_format(output_format))
