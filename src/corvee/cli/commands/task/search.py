#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click

from corvee.cli.completion import complete_task_ids
from corvee.cli.params import output_option
from corvee.cli.scope import fetch_merged, paginate_after, resolve_cursor, sort_tasks
from corvee.constants import SCOPE_FILTERS, narrow_output_format, narrow_scope_filter
from corvee.db.tasks import search_tasks
from corvee.guards.fields import validate_fields
from corvee.output import emit_tasks

EPILOG = """\
\b
Examples:
Check whether a task for this already exists:
  corvee task search "flaky auth test" -o json
Include cancelled/done tasks in the search:
  corvee task search "rate limit" --all -o json
Cap the result and trim it to a couple of fields:
  corvee task search "cache" --limit 5 --fields id,title -o json
Search only this project's tasks, not the merged global ones:
  corvee task search "cache" --scope local -o json
Also match text buried in a comment, not just title/description:
  corvee task search "root cause" --include-comments -o json
Page through a large match set, 20 rows at a time:
  corvee task search "cache" --after TASK-40 --limit 20 -o json
"""


@click.command(epilog=EPILOG)
@click.argument("text")
@click.option("--all", "-a", "include_all", is_flag=True)
@click.option(
    "--include-comments",
    "-i",
    is_flag=True,
    help="Also match comment bodies, not just title/description.",
)
@click.option("--scope", "-s", "scope_filter", type=click.Choice(SCOPE_FILTERS), default="all")
@click.option(
    "--after",
    "-k",
    "after_ref",
    help="Cursor: only tasks after this id in the fixed order.",
    shell_complete=complete_task_ids,
)
@click.option("--limit", "-n", type=click.IntRange(min=1))
@click.option("--fields", "-f", "fields_csv")
@output_option(wide=True)
def search(
    text: str,
    include_all: bool,
    include_comments: bool,
    scope_filter: str,
    after_ref: str | None,
    limit: int | None,
    fields_csv: str | None,
    output_format: str,
) -> None:
    """Tasks whose title or description contains <text>, case-insensitive."""
    fields = validate_fields(fields_csv.split(",")) if fields_csv else None
    # --limit applies after the merge, never per scope.
    tasks = sort_tasks(
        fetch_merged(
            narrow_scope_filter(scope_filter),
            lambda conn, s: search_tasks(
                conn, text, include_all=include_all, include_comments=include_comments, scope=s
            ),
        )
    )
    if after_ref is not None:
        tasks = paginate_after(tasks, resolve_cursor(after_ref))
    if limit is not None:
        tasks = tasks[:limit]
    emit_tasks(
        [t.to_dict() for t in tasks], output=narrow_output_format(output_format), fields=fields
    )
