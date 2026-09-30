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
from corvee.db.tasks import purge_task
from corvee.models import parse_task_refs
from corvee.output import emit_tasks

EPILOG = """\
\b
Examples:
Cancel a duplicate task, then permanently remove it:
  corvee task update TASK-14 --state cancelled && corvee task purge TASK-14
Purge an already-cancelled task and get its last state as JSON:
  corvee task purge 14 -o json
Purge a batch of cancelled, unlinked junk tasks in one call:
  corvee task purge 14 15 16 -o json
Purging a task that isn't cancelled yet fails, on purpose:
  corvee task purge 14  # fails with task_not_cancelled unless already cancelled
"""


@click.command(epilog=EPILOG)
@click.argument("task_refs", nargs=-1, required=True, shell_complete=complete_task_ids)
@output_option()
def purge(task_refs: tuple[str, ...], output_format: str) -> None:
    """Permanently remove one or more already-cancelled, unlinked tasks and
    their event history, in one transaction.
    """
    task_ids, scope = parse_task_refs(task_refs)
    with corvee_context(scope=scope) as ctx:
        tasks = [purge_task(ctx.conn, task_id, scope=scope) for task_id in task_ids]
    emit_tasks([task.to_dict() for task in tasks], output=narrow_output_format(output_format))
