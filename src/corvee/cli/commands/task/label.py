#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click

from corvee.cli.completion import complete_labels, complete_task_ids
from corvee.cli.context import corvee_context
from corvee.db.labels import add_label, remove_label
from corvee.db.tasks import require_tasks
from corvee.guards.labels import normalize_label
from corvee.models import parse_task_refs
from corvee.output import emit_tasks

EPILOG = """\
\b
Examples:
Attach a label to a task, creating it if it's new:
  corvee task label TASK-14 --add api
Attach two labels at once, and get the result as JSON:
  corvee task label 14 --add api --add urgent --json
Removals apply first, so this ends with the label attached:
  corvee task label 14 --remove urgent --add urgent
Tag a whole batch of tasks with one label in one call:
  corvee task label 14 15 16 --add urgent --json
"""


@click.command(epilog=EPILOG)
@click.argument("task_refs", nargs=-1, required=True, shell_complete=complete_task_ids)
@click.option(
    "--add", "-a", "to_add", multiple=True, help="Repeatable.", shell_complete=complete_labels
)
@click.option(
    "--remove",
    "-r",
    "to_remove",
    multiple=True,
    help="Repeatable.",
    shell_complete=complete_labels,
)
@click.option("--json", "-j", "as_json", is_flag=True)
def label(
    task_refs: tuple[str, ...], to_add: tuple[str, ...], to_remove: tuple[str, ...], as_json: bool
) -> None:
    """Manage labels on one or more tasks; removals apply before additions."""
    task_ids, scope = parse_task_refs(task_refs)
    with corvee_context(scope=scope) as ctx:
        require_tasks(ctx.conn, task_ids, scope=scope)
        for task_id in task_ids:
            # Removals before additions, so `--remove x --add x` ends with x attached.
            for name in to_remove:
                remove_label(ctx.conn, task_id, normalize_label(name), ctx.actor, ctx.session_id)
            for name in to_add:
                add_label(ctx.conn, task_id, normalize_label(name), ctx.actor, ctx.session_id)
        tasks = require_tasks(ctx.conn, task_ids, scope=scope)
    emit_tasks([task.to_dict() for task in tasks], as_json=as_json)
