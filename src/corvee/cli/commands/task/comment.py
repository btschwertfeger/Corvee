#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click

from corvee.cli.completion import complete_task_ids
from corvee.cli.context import corvee_context
from corvee.cli.params import StdinOrValue
from corvee.db.tasks import add_comment
from corvee.models import parse_task_ref
from corvee.output import emit_tasks

EPILOG = """\
\b
Examples:
Leave a note for whoever picks this task up next:
  corvee task comment TASK-14 "Blocked on the staging credentials rotation"
Read a long or multi-line comment from stdin instead of an argument:
  corvee task comment 14 - <<< "multi-line handoff note read from stdin"
Comment and get the result as JSON:
  corvee task comment 14 "picking this back up" --json
"""


@click.command(epilog=EPILOG)
@click.argument("task_ref", shell_complete=complete_task_ids)
@click.argument("text", type=StdinOrValue())
@click.option("--json", "-j", "as_json", is_flag=True)
def comment(task_ref: str, text: str, as_json: bool) -> None:
    """Append a progress/handoff note (session stamped from CORVEE_SESSION_ID)."""
    ref = parse_task_ref(task_ref)
    with corvee_context(scope=ref.scope) as ctx:
        task = add_comment(ctx.conn, ref.id, text, ctx.actor, ctx.session_id, scope=ref.scope)
    emit_tasks([task.to_dict()], as_json=as_json)
