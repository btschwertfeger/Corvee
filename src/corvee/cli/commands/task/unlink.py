#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click

from corvee.cli.completion import complete_task_ids
from corvee.cli.context import corvee_context
from corvee.cli.params import output_option
from corvee.constants import RELATIONS, narrow_output_format, narrow_relation
from corvee.db.links import unlink_tasks
from corvee.db.tasks import require_tasks
from corvee.guards.scope import assert_same_scope
from corvee.models import parse_task_ref
from corvee.output import emit_tasks

EPILOG = """\
\b
Examples:
Remove a blocking relationship between two tasks:
  corvee task unlink TASK-1 TASK-2 --relation blocks
Detach a subtask from its parent, and get the result as JSON:
  corvee task unlink 1 2 --relation parent_of -o json
Mistyped links are removable, not permanent:
  corvee task unlink 1 2 --relation duplicates  # mistyped links are removable, not permanent
"""


@click.command(epilog=EPILOG)
@click.argument("source_ref", shell_complete=complete_task_ids)
@click.argument("target_ref", shell_complete=complete_task_ids)
@click.option("--relation", "-r", type=click.Choice(RELATIONS), required=True)
@output_option()
def unlink(source_ref: str, target_ref: str, relation: str, output_format: str) -> None:
    """Remove a link."""
    source = parse_task_ref(source_ref)
    target = parse_task_ref(target_ref)
    assert_same_scope(source.scope, target.scope)
    with corvee_context(scope=source.scope) as ctx:
        unlink_tasks(
            ctx.conn,
            source.id,
            target.id,
            narrow_relation(relation),
            ctx.actor,
            ctx.session_id,
            scope=source.scope,
        )
        tasks = require_tasks(ctx.conn, [source.id, target.id], scope=source.scope)
    emit_tasks([t.to_dict() for t in tasks], output=narrow_output_format(output_format))
