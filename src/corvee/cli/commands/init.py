#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import json
from pathlib import Path

import click

from corvee.config import AGENTS_BLOCK_GLOBAL, AGENTS_BLOCK_LOCAL, bootstrap_project

# `init` reports what it did/didn't do rather than returning a task array —
# it never touches a task, so the documented "array of task objects" shape
# doesn't apply, the same way `labels`/`export` step outside it.
EPILOG = """\
\b
Examples:
Set up corvee in the current project:
  corvee init
Get the paths it created as machine-readable output:
  corvee init --json
Re-run it any time; it never overwrites existing data:
  corvee init
Share a backlog with a sibling git worktree by pointing both at one file:
  corvee init --db-path ../../main/.corvee/corvee.db
"""

_STATUS_TEXT = {
    "appended": "added .corvee/ entry",
    "up_to_date": "already up to date",
    "skipped": "skipped (no .gitignore file here)",
}


@click.command(epilog=EPILOG)
@click.option(
    "--db-path",
    "-d",
    "db_path",
    help="Where to store the database, relative to .corvee/. Only used the "
    "first time a config is created.",
)
@click.option("--json", "-j", "as_json", is_flag=True, help="Emit a JSON report instead of text.")
def init(db_path: str | None, as_json: bool) -> None:
    """Create .corvee/config.toml. Appends to .gitignore if present, never creates.

    Never touches AGENTS.md. Prints two pointer blocks instead: one for this
    project's own AGENTS.md, one for a global agents config such as
    ~/.claude/CLAUDE.md to apply across every project. Paste whichever fits.
    """
    result = bootstrap_project(Path.cwd(), db_path=db_path)

    if as_json:
        click.echo(
            json.dumps(
                {
                    "config_path": str(result.config_path),
                    "db_path": str(result.db_path),
                    "config_created": result.config_created,
                    "gitignore_status": result.gitignore_status,
                    "agents_block_local": AGENTS_BLOCK_LOCAL,
                    "agents_block_global": AGENTS_BLOCK_GLOBAL,
                },
            ),
        )
        return

    click.echo(
        f"config: {'created' if result.config_created else 'already exists'} "
        f"({result.config_path})",
    )
    click.echo(f"database: {result.db_path}")
    click.echo(f".gitignore: {_STATUS_TEXT[result.gitignore_status]}")
    click.echo("\nPaste this into this project's own AGENTS.md:\n")
    click.echo(AGENTS_BLOCK_LOCAL, nl=False)
    click.echo(
        "\nOr paste this into a global agents config such as ~/.claude/CLAUDE.md, "
        "to apply it across every project:\n",
    )
    click.echo(AGENTS_BLOCK_GLOBAL, nl=False)
