#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click

from corvee.cli.completion import complete_task_ids
from corvee.cli.context import corvee_context
from corvee.constants import RELATIONS, narrow_relation
from corvee.db.links import link_tasks
from corvee.db.tasks import require_tasks
from corvee.guards.scope import assert_same_scope
from corvee.models import parse_task_ref
from corvee.output import emit_tasks

EPILOG = """\
\b
Examples:
Record that one task is blocked by another:
  corvee task link TASK-1 TASK-2 --relation blocks
Make one task a subtask of another, and get the result as JSON:
  corvee task link 1 2 --relation parent_of --json
For parent_of, argument order is <parent> <child>:
  corvee task link 1 2 --relation parent_of  # order matters: <parent> <child>
"""


@click.command(epilog=EPILOG)
@click.argument("source_ref", shell_complete=complete_task_ids)
@click.argument("target_ref", shell_complete=complete_task_ids)
@click.option("--relation", "-r", type=click.Choice(RELATIONS), required=True)
@click.option("--json", "-j", "as_json", is_flag=True)
def link(source_ref: str, target_ref: str, relation: str, as_json: bool) -> None:
    """Relate two tasks, including hierarchy (cycle-checked for parent_of)."""
    source = parse_task_ref(source_ref)
    target = parse_task_ref(target_ref)
    assert_same_scope(source.scope, target.scope)
    with corvee_context(scope=source.scope) as ctx:
        warnings = link_tasks(
            ctx.conn, source.id, target.id, narrow_relation(relation), ctx.actor, ctx.session_id
        )
        tasks = require_tasks(ctx.conn, [source.id, target.id], scope=source.scope)
    dicts = []
    for task in tasks:
        detail = task.to_dict()
        if task.id in warnings:
            detail["warnings"] = [warnings[task.id]]
        dicts.append(detail)
    emit_tasks(dicts, as_json=as_json)
