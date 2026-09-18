#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import json
from pathlib import Path
from typing import cast

import click

from corvee.cli.context import corvee_context
from corvee.constants import SCOPES, Scope
from corvee.db.export_import import export_project

EPILOG = """\
\b
Examples:
Dump the whole project to stdout:
  corvee export
Write the dump to a file instead:
  corvee export --output backup.json
Name the backup file after today's date:
  corvee export --output "$(date +%F)-corvee-backup.json"
Back up the machine-wide global database instead:
  corvee export --scope global --output global-backup.json
"""


@click.command(epilog=EPILOG)
@click.option("--output", "-o", "output_path", type=click.Path())
@click.option("--scope", "-s", "scope", type=click.Choice(SCOPES), default="local")
def export(output_path: str | None, scope: str) -> None:
    """Dump the whole project (or --scope global) as JSON."""
    with corvee_context(write=False, scope=cast(Scope, scope)) as ctx:
        data = export_project(ctx.conn)
    text = json.dumps(data)
    if output_path:
        Path(output_path).write_text(text)
    else:
        click.echo(text)
