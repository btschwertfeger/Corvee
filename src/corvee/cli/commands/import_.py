#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import json
from pathlib import Path

import click

from corvee.cli.context import corvee_context
from corvee.constants import SCOPES, narrow_scope
from corvee.db.export_import import import_project
from corvee.db.tasks import TaskFilter, list_tasks
from corvee.errors import UsageError
from corvee.output import emit_tasks

EPILOG = """\
\b
Examples:
Restore a backup into a fresh project:
  corvee init && corvee import backup.json
Restore and get the result as machine-readable output:
  corvee import backup.json --json
Restore the most recent dated backup in this directory:
  corvee import "$(ls -t *-corvee-backup.json | head -1)"
Restore a backup of the machine-wide global database instead:
  corvee import global-backup.json --scope global
"""


@click.command(name="import", epilog=EPILOG)
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.option("--scope", "-s", "scope", type=click.Choice(SCOPES), default="local")
@click.option("--json", "-j", "as_json", is_flag=True)
def import_command(file: str, scope: str, as_json: bool) -> None:
    """Restore a dump into an empty project (or --scope global)."""
    try:
        data = json.loads(Path(file).read_text())
    except json.JSONDecodeError as error:
        raise UsageError("invalid_import_json", f"{file} is not valid JSON: {error}") from error
    with corvee_context(scope=narrow_scope(scope)) as ctx:
        import_project(ctx.conn, data)
        tasks = list_tasks(ctx.conn, TaskFilter(include_all=True), scope=narrow_scope(scope))
    emit_tasks([t.to_dict() for t in tasks], as_json=as_json)
