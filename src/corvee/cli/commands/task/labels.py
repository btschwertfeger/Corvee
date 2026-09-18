#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click

from corvee.cli.context import corvee_context
from corvee.db.labels import list_labels_with_counts
from corvee.output import emit_tasks

EPILOG = """\
\b
Examples:
List every label used in this project, with its task count:
  corvee task labels
Get the same list as machine-readable output:
  corvee task labels --json
Find labels that were attached and later removed from every task:
  corvee task labels --json | jq '.[] | select(.task_count == 0)'
"""


@click.command(name="labels", epilog=EPILOG)
@click.option("--json", "-j", "as_json", is_flag=True)
def labels_command(as_json: bool) -> None:
    """List every label in the project with its task count."""
    with corvee_context(write=False) as ctx:
        rows = list_labels_with_counts(ctx.conn)
    payload = [{"name": name, "task_count": count} for name, count in rows]
    emit_tasks(payload, as_json=as_json, fields=("name", "task_count"))
